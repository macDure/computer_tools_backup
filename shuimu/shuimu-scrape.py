#!/usr/bin/env python3
"""Archive posts by an author from a NewSMTH board.

The Telnet backend follows the logged-in BBS board list and author search;
the web backend remains available for public nForum pages.  Both clients use
the same local credential-file convention as newsmth-bbs.py.
"""

from __future__ import annotations

import argparse
import codecs
import datetime as dt
import hashlib
import json
import mimetypes
import os
import pty
import re
import select
import signal
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag


DEFAULT_AUTHOR = "Icestone"
DEFAULT_BOARD = "Stock"
DEFAULT_BASE_URL = "https://www.newsmth.net"
DEFAULT_CREDENTIALS = os.path.expanduser(
    os.environ.get("NEWSMTH_CREDENTIALS", "~/.config/newsmth/credentials")
)
USER_AGENT = "shuimu-scrape/1.0 (local personal archive; contact user if needed)"
ARTICLE_PATH_RE = re.compile(r"^/nForum/article/([^/?#]+)/([0-9]+)")
DATE_RE = re.compile(
    r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4}\b"
)
AUTHOR_RE = re.compile(r"发信人\s*:\s*([^\s(（]+)")
BOARD_RE = re.compile(r"信区\s*:\s*([^\s,，)）]+)")
TITLE_RE = re.compile(r"标\s*题\s*:\s*(.*)")
SOURCE_RE = re.compile(r"发信站\s*:\s*(.*)")
FLOOR_RE = re.compile(r"第\s*(\d+)\s*楼")
PAGE_RE = re.compile(r"[?&]p=(\d+)")
MISSING_RE = re.compile(r"全站审核中|暂不能查看本文内容|文章不存在|文章已被删除")
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
CSI_RE = re.compile(r"\x1b\[([0-?]*)([ -/]*)([@-~])")
TELNET_HOST = "bbs.newsmth.net"
TELNET_ARTICLE_URL = "https://www.newsmth.net/nForum/article/{board}/{article_id}"
IMAGE_URL_RE = re.compile(r"https?://[^\s<>\"'，。；、]+", re.IGNORECASE)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}


class ScrapeError(RuntimeError):
    """An expected scrape failure with a user-facing message."""


def normalize_id(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def is_real_telnet_article_id(value: str) -> bool:
    try:
        return int(value) >= 1_000_000
    except (TypeError, ValueError):
        return False


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in value.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def looks_like_image_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    path = parsed.path.casefold()
    hostname = (parsed.hostname or "").casefold()
    return (
        Path(path).suffix in IMAGE_EXTENSIONS
        or "/att/" in path
        or hostname.startswith("att.")
        or hostname.startswith("images.")
        or "image" in hostname
    )


def extract_image_urls(value: str, base_url: str = "") -> list[str]:
    found: list[str] = []
    for raw_url in IMAGE_URL_RE.findall(value):
        url = urljoin(base_url, raw_url.rstrip(".,;:!?)]}》」』"))
        if looks_like_image_url(url) and url not in found:
            found.append(url)
    return found


def extract_dom_image_urls(container: Tag, base_url: str) -> list[str]:
    found: list[str] = []
    for element in container.find_all(["img", "source", "a"], href=True):
        candidate = element.get("href", "")
        url = urljoin(base_url, candidate)
        if looks_like_image_url(url) and url not in found:
            found.append(url)
    for element in container.find_all(["img", "source"], src=True):
        candidate = element.get("src", "")
        url = urljoin(base_url, candidate)
        if looks_like_image_url(url) and url not in found:
            found.append(url)
    return found


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return value or "archive"


def parse_cli_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"日期必须是 YYYY-MM-DD：{value}") from error


def parse_post_date(value: str) -> dt.date | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group(0), "%a %b %d %H:%M:%S %Y").date()
    except ValueError:
        return None


def load_credentials(path: str) -> tuple[str, str] | None:
    """Read the existing local credential file without printing its values."""
    try:
        with open(path, encoding="utf-8") as credential_file:
            values: dict[str, str] = {}
            for line in credential_file:
                key, separator, value = line.rstrip("\n").partition("=")
                if separator:
                    values[key.strip().lower()] = value
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ScrapeError(f"无法读取凭据文件 {path}: {error}") from error

    username = values.get("username") or values.get("user")
    password = values.get("password") or values.get("pass")
    if not username or password is None:
        raise ScrapeError(f"凭据文件格式不完整：{path}")
    return username, password


class RateLimiter:
    def __init__(self, interval: float):
        if interval < 0:
            raise ValueError("访问间隔不能是负数")
        self.interval = interval
        self.last_request = 0.0

    def wait(self) -> None:
        remaining = self.interval - (time.monotonic() - self.last_request)
        if remaining > 0:
            time.sleep(remaining)
        self.last_request = time.monotonic()


class WebClient:
    def __init__(self, base_url: str, interval: float, retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            }
        )
        self.rate_limiter = RateLimiter(interval)
        self.retries = retries

    def get(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        url = path if path.startswith("http") else urljoin(self.base_url + "/", path.lstrip("/"))
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self.rate_limiter.wait()
            try:
                response = self.session.get(url, params=params, timeout=(10, 30))
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(
                        f"HTTP {response.status_code}", response=response
                    )
                response.raise_for_status()
                return response
            except (requests.RequestException, OSError) as error:
                last_error = error
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 8))
        raise ScrapeError(f"请求失败：{url}：{last_error}") from last_error

    def login(self, credentials_path: str) -> bool:
        """Log in through the site's HTTPS form when local credentials exist.

        This deliberately does not try to solve a CAPTCHA.  A failed login is
        reported without exposing the username, password, cookies, or body.
        """
        credentials = load_credentials(credentials_path)
        if credentials is None:
            return False

        hostname = urlparse(self.base_url).hostname or ""
        if not (hostname == "newsmth.net" or hostname.endswith(".newsmth.net") or hostname == "mysmth.net" or hostname.endswith(".mysmth.net")):
            raise ScrapeError("为避免泄露凭据，网页登录只允许 newsmth.net/mysmth.net 域名")

        username, password = credentials
        # index.html is only a JavaScript frameset; the nForum shell carries
        # the actual login form and its hidden anti-bot fields.
        login_page = self.get("/nForum/s")
        soup = BeautifulSoup(login_page.content, "html.parser")
        form = soup.find("form", id="login_form") or soup.find(
            "form", action=re.compile(r"/nForum/login")
        )
        if not isinstance(form, Tag):
            raise ScrapeError("网页登录表单结构已变化，未提交凭据")

        data: dict[str, str] = {}
        for field in form.find_all("input"):
            name = field.get("name")
            if name:
                data[name] = field.get("value", "")
        data["id"] = username
        data["passwd"] = password
        if "CookieDate" in data:
            data["CookieDate"] = "2"
        # The visible form's action is a legacy HTML endpoint.  The current
        # nForum JavaScript submits the same fields to this JSON endpoint.
        # Using it avoids treating a normal 404 response as a bad password.
        action = urljoin(login_page.url, "/nForum/user/ajax_login.json")

        self.rate_limiter.wait()
        try:
            response = self.session.post(
                action,
                data=data,
                headers={
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Referer": login_page.url,
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=(10, 30),
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise ScrapeError(f"网页登录请求失败：{error}") from error

        try:
            login_result = response.json()
        except ValueError as error:
            raise ScrapeError("网页登录返回格式已变化，未确认登录状态") from error
        if not isinstance(login_result, dict) or login_result.get("ajax_st") != 1:
            message = "网页登录失败"
            if isinstance(login_result, dict):
                candidate = login_result.get("ajax_msg")
                if isinstance(candidate, str) and candidate.strip():
                    message = clean_text(candidate)
            if any(marker in message for marker in ("验证码", "验证", "captcha", "CAPTCHA")):
                message = "网页登录需要验证码；工具不绕过验证码，请先用浏览器完成一次登录"
            raise ScrapeError(message)

        # Confirm using the post-login page, but never print its contents.
        self.rate_limiter.wait()
        try:
            confirmation = self.session.get(
                urljoin(self.base_url + "/", "nForum/mainpage"),
                headers={"Referer": response.url},
                timeout=(10, 30),
            )
            confirmation.raise_for_status()
        except requests.RequestException as error:
            raise ScrapeError(f"网页登录状态确认失败：{error}") from error

        user_cookie = self.session.cookies.get("main[UTMPUSERID]", "")
        confirmation_text = confirmation.content.decode("gbk", errors="ignore")
        failed_markers = ("密码错误", "登录失败", "验证码", "人机验证")
        if user_cookie.casefold() == "guest" or any(
            marker in confirmation_text for marker in failed_markers
        ):
            raise ScrapeError(
                "网页登录未成功；可能需要在浏览器完成验证码。未绕过验证码，请先用浏览器登录或使用公开内容。"
            )
        return True


def render_terminal_screen(value: str, rows: int = 80, cols: int = 160) -> str:
    """Render the small ANSI screen updates emitted by the BBS.

    Stripping ANSI codes is insufficient for a board refresh: the server
    moves the cursor back over the previous screen and overwrites rows.  This
    renderer intentionally supports the subset used by the BBS (cursor
    movement, erase commands, CR/LF and SGR), without adding a dependency on a
    full terminal-emulation package.
    """
    grid = [[" "] * cols for _ in range(rows)]
    x = y = 0
    saved: tuple[int, int] | None = None

    def clamp() -> None:
        nonlocal x, y
        x = max(0, min(cols - 1, x))
        y = max(0, min(rows - 1, y))

    def params(value: str) -> list[int]:
        value = value.lstrip("?")
        if not value:
            return []
        result: list[int] = []
        for item in value.split(";"):
            try:
                result.append(int(item or "0"))
            except ValueError:
                result.append(0)
        return result

    index = 0
    while index < len(value):
        match = CSI_RE.match(value, index)
        if match:
            raw_params, _, command = match.groups()
            values = params(raw_params)
            amount = values[0] if values and values[0] else 1
            if command in {"H", "f"}:
                y = (values[0] if values else 1) - 1
                x = (values[1] if len(values) > 1 else 1) - 1
            elif command == "A":
                y -= amount
            elif command == "B":
                y += amount
            elif command == "C":
                x += amount
            elif command == "D":
                x -= amount
            elif command == "G":
                x = amount - 1
            elif command == "d":
                y = amount - 1
            elif command == "J":
                mode = values[0] if values else 0
                if mode in {2, 3}:
                    grid = [[" "] * cols for _ in range(rows)]
                elif mode == 0:
                    for column in range(x, cols):
                        grid[y][column] = " "
                    for line in range(y + 1, rows):
                        grid[line] = [" "] * cols
            elif command == "K":
                mode = values[0] if values else 0
                if mode == 0:
                    for column in range(x, cols):
                        grid[y][column] = " "
                elif mode == 1:
                    for column in range(0, x + 1):
                        grid[y][column] = " "
                elif mode == 2:
                    grid[y] = [" "] * cols
            elif command == "s":
                saved = (x, y)
            elif command == "u" and saved is not None:
                x, y = saved
            clamp()
            index = match.end()
            continue

        character = value[index]
        if character == "\x1b":
            # OSC and other non-CSI sequences are irrelevant to text parsing.
            index += 1
            if index < len(value) and value[index] == "]":
                index += 1
                while index < len(value) and value[index] not in {"\x07", "\x1b"}:
                    index += 1
                if index < len(value) and value[index] == "\x1b":
                    index += 1
                    if index < len(value) and value[index] == "\\":
                        index += 1
                elif index < len(value):
                    index += 1
            continue
        if character == "\r":
            x = 0
        elif character == "\n":
            x = 0
            y = min(rows - 1, y + 1)
        elif character == "\b":
            x = max(0, x - 1)
        elif character == "\t":
            x = min(cols - 1, ((x // 8) + 1) * 8)
        elif ord(character) >= 0x20:
            grid[y][x] = character
            x = min(cols - 1, x + 1)
        index += 1

    return "\n".join("".join(line).rstrip() for line in grid).rstrip()


def visible_terminal_text(value: str) -> str:
    return ANSI_RE.sub("", value).replace("\x00", "")


class TelnetArchiveSession:
    """Small PTY-driven client for the Telnet author-archive path.

    The interactive client remains the best way to browse the BBS.  This
    session only automates the same keystrokes and keeps the decoded screen
    text private; credentials and raw terminal output are never logged.
    """

    def __init__(self, host: str, port: int, encoding: str = "gb18030"):
        try:
            codecs.lookup(encoding)
        except LookupError as error:
            raise ScrapeError(f"系统不支持 Telnet 编码：{encoding}") from error
        self.host = host
        self.port = port
        self.encoding = encoding
        self.pid: int | None = None
        self.master_fd: int | None = None
        self.decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
        self.encoder = codecs.getincrementalencoder(encoding)(errors="replace")

    def start(self) -> None:
        env = os.environ.copy()
        env["TERM"] = env.get("BBS_TERM", "ansi")
        pid, master_fd = pty.fork()
        if pid == 0:
            os.execvpe("telnet", ["telnet", "-8", self.host, str(self.port)], env)
        self.pid = pid
        self.master_fd = master_fd

    def send_key(self, value: str, enter: bool = False) -> None:
        if self.master_fd is None:
            raise ScrapeError("Telnet 会话尚未启动")
        if value == "left" and not enter:
            os.write(self.master_fd, b"\x1b[D")
            return
        payload = value + ("\r" if enter else "")
        os.write(self.master_fd, self.encoder.encode(payload, final=False))

    def send_raw(self, value: bytes) -> None:
        if self.master_fd is None:
            raise ScrapeError("Telnet 会话尚未启动")
        os.write(self.master_fd, value)

    def read_for(self, seconds: float) -> str:
        if self.master_fd is None:
            raise ScrapeError("Telnet 会话尚未启动")
        deadline = time.monotonic() + seconds
        chunks: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                readable, _, _ = select.select([self.master_fd], [], [], remaining)
            except (OSError, ValueError) as error:
                raise ScrapeError(f"Telnet 读取失败：{error}") from error
            if not readable:
                break
            try:
                data = os.read(self.master_fd, 16384)
            except OSError:
                break
            if not data:
                break
            chunks.append(self.decoder.decode(data, final=False))
        return "".join(chunks)

    def wait_for(self, patterns: tuple[str, ...], timeout: float = 15.0) -> str:
        deadline = time.monotonic() + timeout
        output = ""
        while time.monotonic() < deadline:
            output += self.read_for(min(0.8, max(0.05, deadline - time.monotonic())))
            visible = visible_terminal_text(output)
            if any(pattern in visible for pattern in patterns):
                return output
        raise ScrapeError("Telnet 页面响应超时；请先用 shuimu 手动确认账号和版面可访问")

    def read_until(self, patterns: tuple[str, ...], timeout: float = 8.0) -> str:
        """Read until a prompt arrives without imposing a fixed sleep."""
        deadline = time.monotonic() + timeout
        output = ""
        while time.monotonic() < deadline:
            output += self.read_for(min(0.25, max(0.05, deadline - time.monotonic())))
            if any(pattern in visible_terminal_text(output) for pattern in patterns):
                return output
        raise ScrapeError("Telnet 页面响应超时；请先用 shuimu 手动确认账号和版面可访问")

    def read_until_raw(self, patterns: tuple[str, ...], timeout: float = 4.0) -> str:
        """Read a redraw until an ANSI marker appears in the raw stream.

        Board-list updates often overwrite only the rows and footer; the
        static ``[一般模式]`` header is not emitted again.  Waiting on the
        visible header therefore adds the full timeout on every old page.
        The footer cursor position is emitted at the end of each redraw and
        is a safe, prompt-independent completion marker.
        """
        deadline = time.monotonic() + timeout
        output = ""
        while time.monotonic() < deadline:
            output += self.read_for(min(0.12, max(0.05, deadline - time.monotonic())))
            if any(re.search(pattern, output) for pattern in patterns):
                return output
        raise ScrapeError("Telnet 页面重绘超时")

    @staticmethod
    def debug_screen(label: str, text: str) -> None:
        if os.environ.get("SHUIMU_DEBUG") != "1":
            return
        wanted_label = os.environ.get("SHUIMU_DEBUG_LABEL")
        if wanted_label and wanted_label.casefold() not in label.casefold():
            return
        lines = render_terminal_screen(text).splitlines()
        safe_lines = [
            line for line in lines
            if not re.search(r"密码|password|passwd|请输入代号|登录名", line, re.IGNORECASE)
        ]
        print(f"[debug:{label}]\n" + "\n".join(safe_lines[-40:]), file=sys.stderr)

    def login_and_open_board(self, username: str, password: str, board: str) -> None:
        self.start()
        initial = self.wait_for(("请输入代号", "登录名", "login:", "Login:"), 30)
        _ = initial
        self.send_key(username, enter=True)
        self.wait_for(("请输入密码", "密码", "password:", "Password:"), 10)
        self.send_key(password, enter=True)

        # The server may display several notices before the main menu.  The
        # observed navigation key is n + Enter; stop immediately if the
        # account-limit prompt appears rather than kicking another session.
        latest = self.read_for(2.0)
        for _ in range(60):
            visible = visible_terminal_text(latest)
            if re.search(r"同时在线|同时登录|超过.*窗口|选择.*窗口", visible):
                raise ScrapeError("水木提示账号已有其他在线窗口；未自动踢出已有会话")
            if "主选单" in visible:
                break
            if "好朋友列表" in visible[-8000:] or "好友列表" in visible[-8000:]:
                # One of the notice pages can fall through to the friend list
                # when n is sent too early; q returns safely to the main menu.
                self.send_key("q")
                latest = self.read_for(1.0)
                continue
            self.send_key("n", enter=True)
            latest = self.read_for(1.0)
        else:
            raise ScrapeError("登录后未到达水木主选单；请先用 shuimu 手动确认登录流程")

        # Main menu: S -> board prompt -> board name.
        self.send_key("S")
        board_prompt = self.read_for(1.5)
        if "选择讨论区" not in visible_terminal_text(board_prompt):
            self.send_raw(b"\r")
            board_prompt += self.read_for(1.5)
        if "选择讨论区" not in visible_terminal_text(board_prompt):
            raise ScrapeError("未能打开水木讨论区选择菜单")
        self.send_key(board, enter=True)
        board_screen = self.wait_for((f"[{board}]", "版主", "讨论区"), 15)
        if board.casefold() not in visible_terminal_text(board_screen).casefold():
            raise ScrapeError(f"未能进入讨论区 {board}")

    def open_board_from_main(self, board: str) -> None:
        """Re-enter a board after a search command returns to the main menu."""
        last_prompt = ""
        for attempt in range(3):
            self.send_key("S")
            board_prompt = self.read_for(2.0)
            if "选择讨论区" not in visible_terminal_text(board_prompt):
                self.send_raw(b"\r")
                board_prompt += self.read_for(2.0)
            last_prompt = board_prompt
            self.debug_screen("reopen board prompt", board_prompt)
            if "选择讨论区" in visible_terminal_text(board_prompt):
                break
            # A redraw can leave the menu command half-consumed.  Return to
            # the main-menu prompt and try the same normal key once more.
            self.send_key("q")
            self.read_for(1.0)
        else:
            raise ScrapeError(
                f"未能重新打开水木讨论区选择菜单（收到 {len(last_prompt)} 个终端字符）"
            )
        self.send_key(board, enter=True)
        board_screen = self.wait_for((f"[{board}]", "版主", "讨论区"), 15)
        if board.casefold() not in visible_terminal_text(board_screen).casefold():
            raise ScrapeError(f"未能重新进入讨论区 {board}")
        self.debug_screen("reopened board", board_screen + self.read_for(0.5))

    def open_author_search(self, author: str) -> str:
        """Open the BBS Ctrl-G+5 all-articles-by-author result list."""
        self.send_raw(b"\x07")  # Ctrl-G: the board's article-search menu
        menu = self.read_for(0.8)
        self.debug_screen("Ctrl-G menu", menu)
        self.send_key("5", enter=True)
        prompt = self.read_for(2.5)
        if not prompt:
            prompt = self.wait_for(("作者", "搜寻作者", "搜索作者", "请输入"), 8)
        self.debug_screen("author prompt", prompt)
        # The author field can retain the previous search value.  Backspace
        # is harmless on an empty field and makes repeated runs deterministic.
        self.send_raw(b"\x08" * 64)
        self.send_key(author, enter=True)
        try:
            page = self.read_until_raw((r"\x1b\[24;\d+H",), 2.5)
        except ScrapeError:
            page = self.read_for(0.8)
        if author.casefold() not in visible_terminal_text(page).casefold():
            try:
                page += self.read_until((author,), 2)
            except ScrapeError:
                page += self.read_for(0.5)
        self.debug_screen("author result", page)
        if not self.author_article_ids(page, author):
            raise ScrapeError(f"在 {author} 的 Ctrl-G+5 检索结果中未发现文章")
        return page

    def search_author(self, author: str) -> tuple[str, str]:
        """Find the nearest matching article in the normal board list."""
        self.send_key("A")
        prompt = self.wait_for(("搜寻作者",), 8)
        visible = visible_terminal_text(prompt).replace("\r", "\n")
        candidates = re.findall(r"搜寻作者\s*[:：]\s*([^\n]*)", visible)
        current = candidates[-1].strip().split()[-1] if candidates and candidates[-1].strip() else ""
        if current:
            self.send_raw(b"\x08" * len(current))
        self.send_key(author, enter=True)
        result = self.read_for(2.5)
        selected = self.selected_article_id(result, author)
        if not selected:
            rows = self.author_article_ids(result, author)
            selected = rows[0] if rows else ""
        if not selected:
            raise ScrapeError(f"在 {author} 的作者检索结果中未发现文章")
        return self.resolve_article_id(result, selected, author) or selected, result

    @staticmethod
    def author_article_ids(text: str, author: str) -> list[str]:
        ids: list[str] = []
        rendered = render_terminal_screen(text)
        for line in rendered.splitlines():
            if author.casefold() not in line.casefold():
                continue
            # Ctrl-G+5 displays a per-result ordinal (for example 2401),
            # while the normal board list displays the real article number
            # (for example 1263996).  Both are valid jump targets from their
            # respective list screens.
            match = re.match(r"\s*>?\s*(\d{3,})\b", line) or re.search(r"\b(\d{5,})\b", line)
            if match and match.group(1) not in ids:
                ids.append(match.group(1))
        return ids

    @staticmethod
    def selected_article_id(text: str, author: str) -> str:
        # ANSI reverse-video is the BBS cursor highlight.  Fall back to a
        # visible `>` marker used by some terminal themes.
        rendered = render_terminal_screen(text)
        for line in rendered.splitlines():
            if author.casefold() not in line.casefold():
                continue
            if re.match(r"\s*>", line):
                match = re.search(r"\b(\d+)\b", line)
                if match:
                    return match.group(1)
        return ""

    @staticmethod
    def resolve_article_id(text: str, candidate: str, author: str) -> str:
        """Recover a real article number when the BBS redraw shows a short row.

        During a screen refresh, the first digits of a row can be overwritten
        by the local row/floor number.  For example, the same page can show
        ``1263375`` next to ``79 Icestone``; the latter is the row ending
        ``1263379``, not article 79.  Nearby intact article numbers provide
        the hundred-range needed to reconstruct it.
        """
        if is_real_telnet_article_id(candidate):
            return candidate
        try:
            short_number = int(candidate)
        except ValueError:
            return ""
        if short_number < 0 or short_number > 99:
            return ""

        rendered = render_terminal_screen(text)
        lines = rendered.splitlines()
        selected_index = next(
            (
                index
                for index, line in enumerate(lines)
                if author.casefold() in line.casefold()
                and re.match(r"\s*>", line)
                and re.search(rf"\b0*{short_number}\b", line)
            ),
            None,
        )
        if selected_index is None:
            selected_index = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if author.casefold() in line.casefold()
                    and re.match(rf"\s*0*{short_number}\b", line)
                ),
                None,
            )
        if selected_index is None:
            return ""

        nearby: list[tuple[int, int, int]] = []
        start = max(0, selected_index - 30)
        end = min(len(lines), selected_index + 31)
        for index in range(start, end):
            for match in re.finditer(r"\b(\d{5,})\b", lines[index]):
                value = int(match.group(1))
                # Ignore status-bar counters such as the online-user count;
                # current NewSMTH article numbers are seven-digit values.
                if value < 1_000_000:
                    continue
                nearby.append((abs(index - selected_index), abs(value - ((value // 100) * 100 + short_number)), value))
        if not nearby:
            return ""
        _, _, reference = min(nearby)
        return str((reference // 100) * 100 + short_number)

    def read_current_article(
        self, board: str, article_id: str, target_author: str
    ) -> tuple[dict[str, Any] | None, str]:
        self.send_key("r")
        article_screen = self.read_until(("发信人", "文章不存在", "暂不能查看"), 8)
        article_screen += self.read_for(0.4)
        self.debug_screen(f"article {article_id}", article_screen)
        post = parse_telnet_article(article_screen, board, article_id, target_author)
        board_screen = ""
        # q normally leaves the article reader.  A long article can still be
        # in its paged reader when the first q arrives, however; retry the
        # leave command and use the documented e/Left fallback before giving
        # up.  This is especially common for a short local-row candidate on
        # an author-result redraw.
        for leave_key in ("q", "q", "e", "left"):
            self.send_key(leave_key)
            try:
                board_screen += self.read_until(("一般模式",), 3)
                break
            except ScrapeError:
                board_screen += self.read_for(0.4)
        board_screen += self.read_for(0.4)
        self.debug_screen(f"return after {article_id}", board_screen)
        return post, board_screen

    def read_selected_author_article(
        self, board: str, article_id: str, target_author: str
    ) -> tuple[dict[str, Any] | None, str]:
        """Open the currently selected article from an author-result screen."""
        _ = article_id
        self.send_key("r")
        article_screen = self.read_until(
            ("发信人", "文章不存在", "暂不能查看", "文章已被删除"), 8
        )
        article_screen += self.read_for(0.4)
        self.debug_screen(f"article {article_id}", article_screen)
        post = parse_telnet_article(article_screen, board, article_id, target_author)
        self.send_key("q")
        try:
            board_screen = self.read_until((target_author, article_id), 6)
        except ScrapeError:
            board_screen = self.read_for(2.0)
        board_screen += self.read_for(0.4)
        self.debug_screen(f"return after {article_id}", board_screen)
        return post, board_screen

    def move_author_cursor_up(self, author: str) -> str:
        """Move to the previous author result and return the redraw."""
        return self.previous_author_result(author)

    def page_up_author_results(self, author: str) -> str:
        """Move to an older page in the Ctrl-G+5 result list."""
        self.send_key("P")
        try:
            screen = self.read_until((author,), 6)
        except ScrapeError:
            screen = self.read_for(2.0)
        screen += self.read_for(0.5)
        return screen

    def page_up_board(self, board: str, author: str) -> str:
        """Move the normal board list to older articles."""
        # A failed author search at the oldest visible result can return all
        # the way to the main menu.  Re-enter the board before paging.
        self.send_key("P")
        first = self.read_for(0.25)
        if "主选单" in visible_terminal_text(first):
            self.open_board_from_main(board)
            self.send_key("P")
            first = ""
        # An older page need not contain the target author.  Waiting for the
        # author string here used to consume and discard the whole redraw on
        # pages without a match, which made the next A search appear stuck.
        # Read the complete redraw instead and let search_author decide
        # whether this page contains a match.
        if re.search(r"\x1b\[24;\d+H", first):
            result = first
        else:
            try:
                result = first + self.read_until_raw((r"\x1b\[24;\d+H",), 1.8)
            except ScrapeError:
                result = first + self.read_for(0.5)
        self.debug_screen("page up board", result)
        return result

    def previous_author_result(self, author: str) -> str:
        prompt = ""
        for _ in range(3):
            self.send_key("A")
            try:
                prompt = self.read_until(("搜寻作者",), 5.0)
            except ScrapeError:
                prompt = ""
            if "搜寻作者" in visible_terminal_text(prompt):
                self.send_key("", enter=True)
                # A successful search redraws the board asynchronously; drain
                # the redraw before the caller sends r, otherwise the next A
                # can be lost.
                try:
                    redraw = self.read_until((author,), 6)
                except ScrapeError:
                    redraw = self.read_for(1.5)
                result = prompt + redraw + self.read_for(0.4)
                if not self.selected_article_id(result, author):
                    # At the oldest result on the current board page the BBS
                    # leaves the author-search prompt open instead of
                    # redrawing the list.  Exit that prompt before sending P;
                    # otherwise P is swallowed and pagination stops.
                    self.send_key("q")
                    result += self.read_for(1.0)
                self.debug_screen("previous author result", result)
                return result
            time.sleep(0.5)
        raise ScrapeError(
            f"Telnet 未返回作者检索提示（收到 {len(prompt)} 个终端字符）"
        )

    def close(self) -> None:
        master_fd = self.master_fd
        pid = self.pid
        self.master_fd = None
        self.pid = None
        if master_fd is not None:
            try:
                os.write(master_fd, b"\x1d")
                time.sleep(0.1)
                os.write(master_fd, b"q\r")
            except OSError:
                pass
            try:
                os.close(master_fd)
            except OSError:
                pass
        if pid is not None:
            try:
                _, status = os.waitpid(pid, 0)
                if os.WIFSIGNALED(status) or os.WIFEXITED(status):
                    return
            except ChildProcessError:
                return
            except OSError:
                pass
            try:
                os.kill(pid, signal.SIGHUP)
            except OSError:
                pass


def parse_telnet_article(
    text: str, board: str, article_id: str, target_author: str
) -> dict[str, Any] | None:
    visible = visible_terminal_text(text).replace("\r", "\n")
    lines = clean_text(visible).splitlines()
    author_index = next(
        (index for index, line in enumerate(lines) if AUTHOR_RE.search(line)), None
    )
    if author_index is None:
        return None
    author_match = AUTHOR_RE.search(lines[author_index])
    if not author_match:
        return None
    author = author_match.group(1).strip()
    board_match = BOARD_RE.search(lines[author_index])
    actual_board = board_match.group(1).strip() if board_match else board
    title = next(
        (match.group(1).strip() for line in lines if (match := TITLE_RE.search(line))),
        "",
    )
    source = next(
        (match.group(1).strip() for line in lines if (match := SOURCE_RE.search(line))),
        "",
    )
    source_index = next(
        (index for index, line in enumerate(lines) if SOURCE_RE.search(line)), None
    )
    content_lines: list[str] = []
    if source_index is not None:
        for line in lines[source_index + 1 :]:
            if re.search(r"阅读文章|回信|主题阅读|结束|上一封|下一封", line):
                break
            if line.strip().startswith(("※", "--发自")):
                break
            if re.fullmatch(r"[-─═_]{5,}", line.strip()):
                break
            content_lines.append(line)
    content = clean_text("\n".join(content_lines))
    return {
        "floor": None,
        "author": author,
        "board": actual_board,
        "time": source,
        "date": parse_post_date(source).isoformat() if parse_post_date(source) else None,
        "title": title,
        "content": content,
        "image_urls": extract_image_urls(
            content, TELNET_ARTICLE_URL.format(board=board, article_id=article_id)
        ),
        "images": [],
        "url": TELNET_ARTICLE_URL.format(board=board, article_id=article_id),
        "is_target": normalize_id(author) == normalize_id(target_author),
        "missing_reason": None if content or title else "文章正文未读取到",
    }


def article_key(board: str, thread_id: str) -> str:
    return f"{board}/{thread_id}"


def parse_article_url(href: str, base_url: str) -> tuple[str, str, str] | None:
    absolute = urljoin(base_url + "/", href)
    parsed = urlparse(absolute)
    match = ARTICLE_PATH_RE.match(parsed.path)
    if not match:
        return None
    board, thread_id = match.groups()
    canonical = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return board, thread_id, canonical


def find_page_number(href: str) -> int | None:
    match = PAGE_RE.search(href)
    return int(match.group(1)) if match else None


def discover_threads(
    client: WebClient,
    author: str,
    board: str,
    since: dt.date | None,
    until: dt.date | None,
    max_pages: int = 10000,
) -> dict[str, dict[str, str]]:
    """Find all unique topic URLs returned by nForum's author search."""
    found: dict[str, dict[str, str]] = {}
    previous_signature: tuple[str, ...] | None = None
    page = 1
    while page <= max_pages:
        response = client.get(
            "/nForum/s/article",
            params={"au": author, "b": board, "p": page},
        )
        soup = BeautifulSoup(response.content, "html.parser")
        page_items: list[str] = []
        for link in soup.find_all("a", href=True):
            parsed = parse_article_url(link["href"], client.base_url)
            if not parsed:
                continue
            link_board, thread_id, canonical = parsed
            if link_board.casefold() != board.casefold():
                continue
            key = article_key(link_board, thread_id)
            title = clean_text(link.get_text(" ", strip=True))
            found.setdefault(key, {"board": link_board, "thread_id": thread_id, "url": canonical})
            if title and title not in {"查看", "阅读"}:
                found[key]["search_title"] = title
            page_items.append(key)

        signature = tuple(dict.fromkeys(page_items))
        max_link_page = max(
            [find_page_number(link.get("href", "")) or 1 for link in soup.find_all("a", href=True)]
            or [1]
        )
        if not signature or signature == previous_signature:
            break
        previous_signature = signature
        if page >= max_link_page and not any(
            find_page_number(link.get("href", "")) == page + 1
            for link in soup.find_all("a", href=True)
        ):
            break
        page += 1

    # Date filtering belongs after article parsing because search-result dates
    # are not consistently marked up across nForum versions.
    _ = since, until
    return found


def nearest_post_containers(soup: BeautifulSoup) -> list[Tag]:
    """Return the smallest useful DOM containers containing one post."""
    candidates: list[Tag] = []
    markers = soup.find_all(string=re.compile(r"发信人\s*:"))
    for marker in markers:
        node = marker.parent if isinstance(marker.parent, Tag) else None
        chosen: Tag | None = None
        while node is not None and node.name not in {"body", "html"}:
            text = clean_text(node.get_text("\n", strip=False))
            if "发信站" in text and ("楼主" in text or FLOOR_RE.search(text)):
                chosen = node
                # A useful card is usually a div/table row; stop before the
                # page-level wrapper that contains adjacent floors.
                if node.name in {"article", "tr", "td", "li", "section"}:
                    break
            node = node.parent if isinstance(node.parent, Tag) else None
        if chosen is not None:
            candidates.append(chosen)

    unique: list[Tag] = []
    seen: set[int] = set()
    for candidate in candidates:
        marker_count = len(candidate.find_all(string=re.compile(r"发信人\s*:")))
        identity = id(candidate)
        if identity in seen:
            continue
        # If the candidate contains several post markers, walk down to a
        # smaller child that contains the current marker where possible.
        if marker_count > 1:
            descendants = candidate.find_all(["article", "tr", "td", "li", "section", "div"])
            smaller = next(
                (
                    child
                    for child in descendants
                    if len(child.find_all(string=re.compile(r"发信人\s*:"))) == 1
                    and "发信站" in child.get_text(" ", strip=False)
                ),
                None,
            )
            if smaller is not None:
                candidate = smaller
                identity = id(candidate)
        if identity not in seen:
            seen.add(identity)
            unique.append(candidate)
    return unique


def extract_body(container: Tag) -> tuple[str, str, str, str]:
    lines = clean_text(container.get_text("\n", strip=False)).split("\n")
    while lines and not re.search(r"发信人\s*:", lines[0]):
        lines.pop(0)
    author_line = next((line for line in lines if re.search(r"发信人\s*:", line)), "")
    source_index = next(
        (index for index, line in enumerate(lines) if re.search(r"发信站\s*:", line)),
        None,
    )
    if source_index is None:
        return "", author_line, "", ""

    content_lines: list[str] = []
    for line in lines[source_index + 1 :]:
        if re.match(r"^第\s*\d+\s*楼$", line):
            break
        if line.strip().startswith("※"):
            break
        if line.strip() == "--":
            break
        content_lines.append(line)

    title = next(
        (match.group(1).strip() for line in lines if (match := TITLE_RE.search(line))),
        "",
    )
    source = next(
        (match.group(1).strip() for line in lines if (match := SOURCE_RE.search(line))),
        "",
    )
    return clean_text("\n".join(content_lines)), author_line, title, source


def parse_post(container: Tag, thread_url: str, target_author: str) -> dict[str, Any] | None:
    body, author_line, title, source = extract_body(container)
    author_match = AUTHOR_RE.search(author_line)
    if not author_match:
        return None
    author_id = author_match.group(1).strip()
    board_match = BOARD_RE.search(author_line)
    board = board_match.group(1).strip() if board_match else ""
    text = clean_text(container.get_text("\n", strip=False))
    floor_match = FLOOR_RE.search(text)
    floor = int(floor_match.group(1)) if floor_match else 0 if "楼主" in text else None
    timestamp = source
    return {
        "floor": floor,
        "author": author_id,
        "board": board,
        "time": timestamp,
        "date": parse_post_date(timestamp).isoformat() if parse_post_date(timestamp) else None,
        "title": title,
        "content": body,
        "image_urls": extract_dom_image_urls(container, thread_url),
        "images": [],
        "url": thread_url,
        "is_target": normalize_id(author_id) == normalize_id(target_author),
        "missing_reason": None,
    }


def parse_article_page(
    response: requests.Response,
    thread_url: str,
    target_author: str,
) -> tuple[str, list[dict[str, Any]], int]:
    soup = BeautifulSoup(response.content, "html.parser")
    page_text = clean_text(soup.get_text("\n", strip=False))
    title = ""
    page_title = soup.find("title")
    if page_title:
        title = clean_text(page_title.get_text(" ", strip=True))
    posts = [post for container in nearest_post_containers(soup) if (post := parse_post(container, thread_url, target_author))]
    max_page = max(
        [find_page_number(link.get("href", "")) or 1 for link in soup.find_all("a", href=True)]
        or [1]
    )
    if not posts and MISSING_RE.search(page_text):
        posts = [
            {
                "floor": None,
                "author": None,
                "board": "",
                "time": "",
                "date": None,
                "title": title,
                "content": "",
                "url": thread_url,
                "is_target": False,
                "missing_reason": next(
                    (line.strip() for line in page_text.splitlines() if MISSING_RE.search(line)),
                    "页面内容不可见",
                ),
            }
        ]
    return title, posts, max_page


def in_date_range(post: dict[str, Any], since: dt.date | None, until: dt.date | None) -> bool:
    if not post.get("is_target"):
        return False
    if not since and not until:
        return True
    if not post.get("date"):
        return True
    value = dt.date.fromisoformat(post["date"])
    return (since is None or value >= since) and (until is None or value <= until)


def post_fingerprint(post: dict[str, Any]) -> tuple[str, str, str, str] | None:
    """Build a stable identity for a Telnet post despite redraw ID noise."""
    author = normalize_id(str(post.get("author") or ""))
    timestamp = clean_text(str(post.get("time") or ""))
    title = clean_text(str(post.get("title") or ""))
    content = clean_text(str(post.get("content") or ""))
    if not author or not timestamp or not (title or content):
        return None
    return author, timestamp, title, content


class ImageDownloader:
    """Download explicitly discovered public image URLs at a low rate."""

    def __init__(self, output_dir: Path, interval: float, max_images: int, max_bytes: int):
        self.output_dir = output_dir
        self.image_dir = output_dir / "images"
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limiter = RateLimiter(interval)
        self.max_images = max_images
        self.max_bytes = max_bytes
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"}
        )

    def download(self, urls: list[str], stem: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, url in enumerate(urls[: self.max_images], start=1):
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
            existing = next(self.image_dir.glob(f"{safe_filename(stem)}-{index}-{digest}.*"), None)
            if existing is not None:
                records.append({"url": url, "downloaded": True, "local_path": str(existing.relative_to(self.output_dir)), "error": None})
                continue
            self.rate_limiter.wait()
            try:
                response = self.session.get(url, timeout=(10, 30), stream=True)
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].casefold()
                suffix = Path(urlparse(url).path).suffix.casefold()
                if content_type.startswith("image/"):
                    suffix = suffix if suffix in IMAGE_EXTENSIONS else mimetypes.guess_extension(content_type) or ".img"
                elif suffix not in IMAGE_EXTENSIONS:
                    raise ScrapeError("响应不是图片")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ScrapeError(f"图片超过 {self.max_bytes} 字节上限")
                    chunks.append(chunk)
                if not chunks:
                    raise ScrapeError("图片响应为空")
                filename = f"{safe_filename(stem)}-{index}-{digest}{suffix}"
                path = self.image_dir / filename
                path.write_bytes(b"".join(chunks))
                records.append({"url": url, "downloaded": True, "local_path": str(path.relative_to(self.output_dir)), "error": None})
            except (requests.RequestException, OSError, ScrapeError) as error:
                records.append({"url": url, "downloaded": False, "local_path": None, "error": str(error)})
        if len(urls) > self.max_images:
            records.append({"url": None, "downloaded": False, "local_path": None, "error": f"图片超过单篇上限 {self.max_images}，其余未请求"})
        return records


def attach_images(post: dict[str, Any], downloader: ImageDownloader | None, stem: str) -> None:
    urls = post.get("image_urls") or []
    post["images"] = downloader.download(urls, stem) if downloader and urls else [
        {"url": url, "downloaded": False, "local_path": None, "error": "未启用图片下载"}
        for url in urls
    ]


def fetch_thread(
    client: WebClient,
    metadata: dict[str, str],
    target_author: str,
    since: dt.date | None,
    until: dt.date | None,
) -> dict[str, Any]:
    thread_url = metadata["url"]
    title = metadata.get("search_title", "")
    all_posts: list[dict[str, Any]] = []
    max_page = 1
    for page in range(1, 10001):
        page_url = thread_url
        if page > 1:
            page_url = f"{thread_url}?{urlencode({'p': page})}"
        response = client.get(page_url)
        parsed_title, posts, discovered_max_page = parse_article_page(
            response, page_url, target_author
        )
        title = title or parsed_title
        max_page = max(max_page, discovered_max_page)
        if posts:
            all_posts.extend(posts)
        if page >= max_page:
            break
        if not posts and page > 1:
            break

    unique_posts: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for post in all_posts:
        key = (post.get("floor"), post.get("author"), post.get("time"))
        if key not in seen:
            seen.add(key)
            unique_posts.append(post)
    target_posts = [post for post in unique_posts if in_date_range(post, since, until)]
    return {
        "board": metadata["board"],
        "thread_id": metadata["thread_id"],
        "title": title,
        "url": thread_url,
        "posts": unique_posts,
        "target_posts": len(target_posts),
        "missing": any(post.get("missing_reason") for post in unique_posts),
    }


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary:
        json.dump(value, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def markdown_escape(value: str) -> str:
    return value.replace("\r", "").strip()


def render_markdown(report: dict[str, Any]) -> str:
    query = report["query"]
    lines = [
        f"# {query['board']} 版：{query['author']} 发帖归档",
        "",
        f"- 抓取时间：{report['fetched_at']}",
        f"- 主题数：{len(report['threads'])}",
        f"- 目标作者楼层数：{report['stats']['target_posts']}",
        "",
        "> 本文件由 shuimu-scrape 生成；楼层正文按网页可见内容保存。",
        "",
    ]
    for thread in report["threads"]:
        lines.extend(
            [
                f"## {markdown_escape(thread.get('title') or '(无标题)')}",
                "",
                f"- 主题：[{thread['board']}/{thread['thread_id']}]({thread['url']})",
                f"- 目标作者楼层：{thread['target_posts']}",
                "",
            ]
        )
        for post in thread["posts"]:
            floor_value = post.get("floor")
            floor = (
                "楼主"
                if floor_value == 0
                else f"第 {floor_value} 楼" if floor_value is not None else "楼层未标记"
            )
            author = post.get("author") or "未知"
            marker = " **目标作者**" if post.get("is_target") else ""
            lines.extend([f"### {floor} · {author}{marker}", ""])
            if post.get("time"):
                lines.extend([f"时间：{post['time']}", ""])
            if post.get("missing_reason"):
                lines.extend([f"**正文不可见：** {post['missing_reason']}", ""])
            else:
                lines.extend([post.get("content") or "（正文为空）", ""])
            images = post.get("images", [])
            if images:
                lines.extend(["图片：", ""])
                for image in images:
                    local_path = image.get("local_path")
                    image_url = image.get("url") or ""
                    if local_path and image.get("downloaded"):
                        lines.extend([f"![图片]({local_path})", ""])
                    elif image_url:
                        error = image.get("error") or "未下载"
                        lines.extend([f"图片链接：{image_url}（{error}）", ""])
            lines.append("---")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report(output_dir: Path, stem: str, report: dict[str, Any], state: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / f"{stem}.json", report)
    (output_dir / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
    atomic_write_json(output_dir / f"{stem}.state.json", state)
    atomic_write_json(output_dir / f"{stem}.errors.json", {"errors": errors})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取水木社区指定版面和作者的帖子，并保存 Markdown/JSON 归档。"
    )
    parser.add_argument("--author", default=os.environ.get("SHUIMU_AUTHOR", DEFAULT_AUTHOR))
    parser.add_argument("--board", default=os.environ.get("SHUIMU_BOARD", DEFAULT_BOARD))
    parser.add_argument("--since", type=parse_cli_date)
    parser.add_argument("--until", type=parse_cli_date)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--base-url", default=os.environ.get("SHUIMU_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--backend", choices=("auto", "web", "telnet"), default="auto")
    parser.add_argument("--rate", type=float, default=1.0, metavar="SECONDS")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, metavar="N")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-login", action="store_true", help="不读取本地凭据，使用访客网页")
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS, metavar="FILE")
    parser.add_argument("--telnet-host", default=TELNET_HOST)
    parser.add_argument("--telnet-port", type=int, default=23)
    parser.add_argument("--telnet-encoding", default=os.environ.get("BBS_ENCODING", "gb18030"))
    parser.add_argument("--no-images", action="store_true", help="只保存图片链接，不下载图片")
    parser.add_argument("--max-images", type=int, default=20, metavar="N")
    parser.add_argument("--max-image-bytes", type=int, default=20 * 1024 * 1024, metavar="BYTES")
    parser.add_argument("--dry-run", action="store_true", help="只发现主题，不抓取正文")
    return parser.parse_args()


def run_telnet(args: argparse.Namespace, output_dir: Path, stem: str) -> int:
    if args.rate < 0 or args.retries < 0 or args.limit < 0 or args.max_images < 0 or args.max_image_bytes <= 0:
        raise ScrapeError("--rate、--retries、--limit、--max-images、--max-image-bytes 参数无效")
    if args.since and args.until and args.since > args.until:
        raise ScrapeError("--since 不能晚于 --until")
    if args.no_login:
        raise ScrapeError("Telnet 抓取需要读取本地凭据；如需访客网页请使用 --backend web --no-login")
    credentials = load_credentials(args.credentials)
    if credentials is None:
        raise ScrapeError(f"未找到 Telnet 凭据文件：{args.credentials}")

    print("[1/3] 通过 Telnet 登录并进入版面…", file=sys.stderr)
    session = TelnetArchiveSession(args.telnet_host, args.telnet_port, args.telnet_encoding)
    telnet_rate = RateLimiter(args.rate)
    image_downloader = None if args.no_images else ImageDownloader(output_dir, args.rate, args.max_images, args.max_image_bytes)
    threads: list[dict[str, Any]] = []
    seen_article_ids: set[str] = set()
    query = {
        "author": args.author,
        "board": args.board,
        "since": args.since.isoformat() if args.since else None,
        "until": args.until.isoformat() if args.until else None,
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "query": query,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "threads": threads,
        "stats": {"discovered": 0, "completed": 0, "target_posts": 0, "missing": 0, "images": 0, "image_failures": 0},
    }
    state: dict[str, Any] = {
        "version": 1,
        "backend": "telnet",
        "query": query,
        "discovered": [],
        "completed": [],
        "errors": [],
        "page_depth": 0,
    }
    resume_page_depth = 0
    state_path = output_dir / f"{stem}.state.json"
    report_path = output_dir / f"{stem}.json"
    if args.resume and state_path.exists() and report_path.exists():
        try:
            previous_state = json.loads(state_path.read_text(encoding="utf-8"))
            previous_report = json.loads(report_path.read_text(encoding="utf-8"))
            if previous_state.get("query") == query and previous_state.get("backend") == "telnet":
                report["threads"] = previous_report.get("threads", [])
                threads = report["threads"]
                seen_article_ids.update(str(thread.get("thread_id")) for thread in threads)
                try:
                    resume_page_depth = max(0, int(previous_state.get("page_depth", 0)))
                except (TypeError, ValueError):
                    resume_page_depth = 0
                print(f"恢复 Telnet 进度：已有 {len(threads)} 篇，继续向更早文章遍历。", file=sys.stderr)
        except (OSError, json.JSONDecodeError) as error:
            print(f"Telnet 断点文件不可用，将从头检查：{error}", file=sys.stderr)

    def persist() -> None:
        # A Telnet screen refresh can temporarily turn a real article number
        # into the adjacent local row number.  If a resumed run reaches the
        # same post again, retain the already archived (usually higher,
        # intact) article number instead of writing a duplicate record.
        threads[:] = [
            thread for thread in threads
            if is_real_telnet_article_id(str(thread.get("thread_id", "")))
        ]
        deduplicated: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        without_identity: list[dict[str, Any]] = []
        for thread in threads:
            posts = thread.get("posts", [])
            identity = post_fingerprint(posts[0]) if len(posts) == 1 else None
            if identity is None:
                without_identity.append(thread)
                continue
            previous = deduplicated.get(identity)
            if previous is None or int(thread["thread_id"]) > int(previous["thread_id"]):
                deduplicated[identity] = thread
        threads[:] = list(deduplicated.values()) + without_identity
        threads.sort(key=lambda value: int(value["thread_id"]))
        report["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        report["stats"] = {
            "discovered": len(threads),
            "completed": len(threads),
            "target_posts": sum(thread["target_posts"] for thread in threads),
            "missing": sum(1 for thread in threads if thread["missing"]),
            "images": sum(
                1
                for thread in threads
                for post in thread.get("posts", [])
                for image in post.get("images", [])
                if image.get("downloaded")
            ),
            "image_failures": sum(
                1
                for thread in threads
                for post in thread.get("posts", [])
                for image in post.get("images", [])
                if not image.get("downloaded")
            ),
        }
        state["discovered"] = [article_key(args.board, thread["thread_id"]) for thread in threads]
        state["completed"] = list(state["discovered"])
        state["page_depth"] = page_depth
        write_report(output_dir, stem, report, state, [])

    try:
        session.login_and_open_board(credentials[0], credentials[1], args.board)
        print(f"[2/3] 使用作者检索并自动翻页：{args.author}…", file=sys.stderr)
        if resume_page_depth:
            print(f"恢复版面位置：跳过最新 {resume_page_depth} 页…", file=sys.stderr)
            for _ in range(resume_page_depth):
                session.page_up_board(args.board, args.author)
        current_id, screen = session.search_author(args.author)
        print("已找到作者文章，开始从当前文章向更早文章遍历…", file=sys.stderr)
        traversed_ids: set[str] = set()
        known_article_ids = set(seen_article_ids)
        page_signatures: set[tuple[str, ...]] = set()
        page_depth = resume_page_depth
        processed = 0
        for _ in range(10000):
            if not current_id or current_id in traversed_ids:
                break
            article_id = current_id
            traversed_ids.add(article_id)
            processed += 1
            if article_id in known_article_ids:
                # --resume starts at the newest author result again.  Walk
                # over already persisted IDs without downloading them twice;
                # navigation still continues until it reaches new history.
                pass
            elif args.dry_run:
                threads.append(
                    {
                        "board": args.board,
                        "thread_id": article_id,
                        "title": "",
                        "url": TELNET_ARTICLE_URL.format(board=args.board, article_id=article_id),
                        "posts": [],
                        "target_posts": 0,
                        "missing": False,
                    }
                )
                persist()
            else:
                post: dict[str, Any] | None = None
                stop_before_since = False
                board_screen = ""
                last_error: ScrapeError | None = None
                for attempt in range(2):
                    telnet_rate.wait()
                    try:
                        post, board_screen = session.read_current_article(
                            args.board, article_id, args.author
                        )
                        last_error = None
                        break
                    except ScrapeError as error:
                        last_error = error
                        if attempt == 0:
                            print(
                                f"读取文章 {article_id} 超时，正在恢复后重试…",
                                file=sys.stderr,
                            )
                            try:
                                session.send_key("q")
                                session.read_for(1.5)
                            except ScrapeError:
                                pass
                if last_error is not None:
                    print(
                        f"读取文章 {article_id} 失败，已保留之前结果：{last_error}",
                        file=sys.stderr,
                    )
                    break
                # The ID resolved from the author-result row is the article
                # just opened.  After q, the BBS cursor may already point at
                # the next row, so never let that redraw replace a complete
                # ID with an adjacent one.
                confirmed_id = article_id if is_real_telnet_article_id(article_id) else ""
                if not confirmed_id:
                    confirmed_candidate = session.selected_article_id(board_screen, args.author)
                    confirmed_id = session.resolve_article_id(
                        board_screen, confirmed_candidate, args.author
                    ) if confirmed_candidate else ""
                if not confirmed_id:
                    confirmed_id = session.resolve_article_id(screen, article_id, args.author)
                if not confirmed_id and post:
                    identity = post_fingerprint(post)
                    matching_thread = next(
                        (
                            thread for thread in threads
                            if len(thread.get("posts", [])) == 1
                            and post_fingerprint(thread["posts"][0]) == identity
                        ),
                        None,
                    ) if identity else None
                    if matching_thread is not None:
                        confirmed_id = str(matching_thread["thread_id"])
                if not confirmed_id:
                    TelnetArchiveSession.debug_screen(
                        f"unresolved candidate {article_id}",
                        screen + board_screen,
                    )
                    print(
                        f"跳过文章：无法从 Telnet 刷新画面确认真实文章号（候选 {article_id}）",
                        file=sys.stderr,
                    )
                    continue
                if post:
                    if (
                        args.since
                        and post.get("date")
                        and dt.date.fromisoformat(post["date"]) < args.since
                    ):
                        # The normal board and author-result navigation are
                        # strictly newest-to-oldest.  Once a matching author
                        # post is older than --since, no later traversal can
                        # produce an in-range post.
                        stop_before_since = True
                    post["result_number"] = confirmed_id
                    post["url"] = TELNET_ARTICLE_URL.format(
                        board=args.board, article_id=confirmed_id
                    )
                    attach_images(post, image_downloader, f"{args.board}-{confirmed_id}")
                    existing_thread = next(
                        (thread for thread in threads if thread["thread_id"] == confirmed_id),
                        None,
                    )
                    if existing_thread is not None:
                        existing_thread["title"] = post.get("title", existing_thread.get("title", ""))
                        existing_thread["url"] = post["url"]
                        existing_thread["posts"] = [post]
                        existing_thread["target_posts"] = int(in_date_range(post, args.since, args.until))
                        existing_thread["missing"] = bool(post.get("missing_reason"))
                    elif in_date_range(post, args.since, args.until):
                        print(f"  已读取 {confirmed_id}：{post.get('title', '')}", file=sys.stderr)
                        threads.append(
                            {
                                "board": args.board,
                                "thread_id": confirmed_id,
                                "title": post.get("title", ""),
                                "url": post["url"],
                                "posts": [post],
                                "target_posts": 1,
                                "missing": bool(post.get("missing_reason")),
                            }
                        )
                    persist()
                    known_article_ids.add(confirmed_id)
                    if stop_before_since:
                        print(
                            f"已到达 --since {args.since.isoformat()} 之前，停止继续翻页。",
                            file=sys.stderr,
                        )
                        break

            if args.limit and processed >= args.limit:
                break

            # A/a searches within the current board-list window.  When it
            # returns an already-read article, move one normal board page up
            # and start the author search again.  This is the key difference
            # from the old implementation, which stopped at the first page.
            next_id = ""
            try:
                next_screen = session.previous_author_result(args.author)
                next_id = session.selected_article_id(next_screen, args.author)
            except ScrapeError:
                next_screen = ""
            if next_screen and "主选单" in visible_terminal_text(next_screen):
                session.open_board_from_main(args.board)
                # Re-entering from the main menu resets the board list to its
                # newest page.  Fast-forward over pages already traversed in
                # this run before asking P for the next older page below.
                for _ in range(page_depth):
                    session.page_up_board(args.board, args.author)
            if next_id and next_id not in traversed_ids:
                current_id, screen = next_id, next_screen
                continue

            found_next_page = False
            for _ in range(1000):
                page_screen = session.page_up_board(args.board, args.author)
                page_signature = tuple(
                    line.strip()
                    for line in render_terminal_screen(page_screen).splitlines()
                    if line.strip() and "时间[" not in line and "总人数[" not in line
                )
                if not page_signature or page_signature in page_signatures:
                    break
                page_signatures.add(page_signature)
                page_depth += 1
                try:
                    candidate_id, candidate_screen = session.search_author(args.author)
                except ScrapeError:
                    continue
                if candidate_id not in traversed_ids:
                    current_id, screen = candidate_id, candidate_screen
                    found_next_page = True
                    break
            if not found_next_page:
                break
    finally:
        session.close()

    persist()
    print(f"发现并保存 {len(threads)} 篇 {args.author} 的文章。", file=sys.stderr)
    print(f"Markdown：{output_dir / (stem + '.md')}", file=sys.stderr)
    print(f"JSON：{output_dir / (stem + '.json')}", file=sys.stderr)
    return 0


def run_web(args: argparse.Namespace, output_dir: Path, stem: str) -> int:
    if args.rate < 0 or args.retries < 0 or args.limit < 0 or args.max_images < 0 or args.max_image_bytes <= 0:
        raise ScrapeError("--rate、--retries、--limit、--max-images、--max-image-bytes 参数无效")
    if args.since and args.until and args.since > args.until:
        raise ScrapeError("--since 不能晚于 --until")

    print("[1/3] 准备网页端会话…", file=sys.stderr)
    base_urls = [args.base_url.rstrip("/")]
    if args.base_url.rstrip("/") == DEFAULT_BASE_URL:
        # 水木页面会提示使用新域名；保留多个只读入口，避免单个域名
        # 故障时整个归档任务失败。
        base_urls.extend(
            [
                "https://www.mysmth.net",
                "https://images.newsmth.net",
                "https://att.newsmth.net",
            ]
        )
    client: WebClient | None = None
    discovery_errors: list[str] = []
    for base_url in dict.fromkeys(base_urls):
        candidate = WebClient(base_url, args.rate, args.retries)
        try:
            if not args.no_login:
                if candidate.login(args.credentials):
                    print("已使用本地凭据登录网页端。", file=sys.stderr)
                elif Path(args.credentials).exists():
                    raise ScrapeError("凭据文件存在但未能完成网页登录")
                else:
                    print("未找到本地凭据文件，使用访客网页。", file=sys.stderr)
            client = candidate
            break
        except ScrapeError as error:
            discovery_errors.append(f"{base_url}: {error}")
    if client is None:
        raise ScrapeError("所有网页入口均不可用：\n" + "\n".join(discovery_errors))
    print(f"[2/3] 搜索版面 {args.board} 中作者 {args.author} 的主题…", file=sys.stderr)
    discovered = discover_threads(client, args.author, args.board, args.since, args.until)
    if args.limit:
        discovered = dict(list(discovered.items())[: args.limit])
    print(f"发现 {len(discovered)} 个主题。", file=sys.stderr)

    state_path = output_dir / f"{stem}.state.json"
    state: dict[str, Any] = {
        "version": 1,
        "query": {"author": args.author, "board": args.board, "since": args.since.isoformat() if args.since else None, "until": args.until.isoformat() if args.until else None},
        "discovered": list(discovered),
        "completed": [],
        "errors": [],
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "query": state["query"],
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "threads": [],
        "stats": {"discovered": len(discovered), "completed": 0, "target_posts": 0, "missing": 0, "images": 0, "image_failures": 0},
    }
    errors: list[dict[str, Any]] = []
    image_downloader = None if args.no_images else ImageDownloader(output_dir, args.rate, args.max_images, args.max_image_bytes)

    if args.resume and state_path.exists():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            if previous.get("query") == state["query"]:
                state["completed"] = previous.get("completed", [])
                errors = previous.get("errors", [])
                report_path = output_dir / f"{stem}.json"
                if report_path.exists():
                    previous_report = json.loads(report_path.read_text(encoding="utf-8"))
                    report["threads"] = previous_report.get("threads", [])
                    report["stats"] = previous_report.get("stats", report["stats"])
                print(f"恢复进度：已完成 {len(state['completed'])} 个主题。", file=sys.stderr)
        except (OSError, json.JSONDecodeError) as error:
            print(f"断点文件不可用，将从头检查：{error}", file=sys.stderr)

    completed = set(state["completed"])
    if args.dry_run:
        write_report(output_dir, stem, report, state, errors)
        return 0

    print("[3/3] 抓取主题正文…", file=sys.stderr)
    for index, (key, metadata) in enumerate(discovered.items(), start=1):
        if key in completed:
            continue
        print(f"  [{index}/{len(discovered)}] {metadata['url']}", file=sys.stderr)
        try:
            thread = fetch_thread(client, metadata, args.author, args.since, args.until)
            for post in thread["posts"]:
                attach_images(
                    post,
                    image_downloader,
                    f"{thread['board']}-{thread['thread_id']}-{post.get('floor') or 'post'}",
                )
            report["threads"] = [
                old for old in report["threads"] if article_key(old["board"], old["thread_id"]) != key
            ]
            report["threads"].append(thread)
            report["threads"].sort(key=lambda value: (value["board"], int(value["thread_id"])))
            state["completed"].append(key)
            completed.add(key)
            report["stats"]["completed"] = len(completed)
            report["stats"]["target_posts"] = sum(thread["target_posts"] for thread in report["threads"])
            report["stats"]["missing"] = sum(1 for thread in report["threads"] if thread["missing"])
            all_images = [image for item in report["threads"] for post in item["posts"] for image in post.get("images", [])]
            report["stats"]["images"] = sum(1 for image in all_images if image.get("downloaded"))
            report["stats"]["image_failures"] = sum(1 for image in all_images if not image.get("downloaded"))
            write_report(output_dir, stem, report, state, errors)
        except Exception as error:  # keep the batch moving and report the exact URL
            entry = {"thread": key, "url": metadata["url"], "error": str(error)}
            errors.append(entry)
            state["errors"] = errors
            write_report(output_dir, stem, report, state, errors)
            print(f"    跳过：{error}", file=sys.stderr)

    state["errors"] = errors
    report["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    write_report(output_dir, stem, report, state, errors)
    print(f"[4/4] 完成：{output_dir / (stem + '.md')}", file=sys.stderr)
    print(f"JSON：{output_dir / (stem + '.json')}", file=sys.stderr)
    if errors:
        print(f"有 {len(errors)} 个主题失败，详见 {output_dir / (stem + '.errors.json')}", file=sys.stderr)
    return 0


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir or Path(__file__).resolve().parent / "data")
    stem = f"{safe_filename(args.board)}_{safe_filename(args.author)}"
    try:
        if args.backend == "telnet":
            return run_telnet(args, output_dir, stem)
        if args.backend == "web":
            return run_web(args, output_dir, stem)
        try:
            return run_web(args, output_dir, stem)
        except ScrapeError as web_error:
            print(f"网页端不可用：{web_error}", file=sys.stderr)
            print("自动切换到已实测的 Telnet 作者检索路径…", file=sys.stderr)
            return run_telnet(args, output_dir, stem)
    except ScrapeError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断；再次加 --resume 可继续。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
