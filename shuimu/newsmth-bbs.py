#!/usr/bin/env python3
"""Interactive NewSMTH telnet client with GBK/GB18030 conversion and heartbeat."""

import argparse
import codecs
import getpass
import os
import pty
import re
import select
import signal
import sys
import termios
import time
import tty


DEFAULT_CREDENTIALS = os.path.expanduser(
    os.environ.get("NEWSMTH_CREDENTIALS", "~/.config/newsmth/credentials")
)
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def parse_args():
    parser = argparse.ArgumentParser(
        description="用正确的中文编码连接水木社区 telnet，并发送低干扰心跳。"
    )
    parser.add_argument("host", nargs="?", default="bbs.newsmth.net")
    parser.add_argument("port", nargs="?", type=int, default=23)
    parser.add_argument(
        "--encoding",
        default=os.environ.get("BBS_ENCODING", "gb18030"),
        help="论坛编码，默认 gb18030；也可设为 gbk",
    )
    parser.add_argument(
        "--heartbeat",
        type=float,
        default=float(os.environ.get("BBS_HEARTBEAT", "60")),
        metavar="SECONDS",
        help="空闲心跳间隔，默认 60 秒；设为 0 可关闭",
    )
    parser.add_argument(
        "--credentials",
        default=DEFAULT_CREDENTIALS,
        metavar="FILE",
        help=f"凭据文件，默认 {DEFAULT_CREDENTIALS}",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="首次运行时保存用户名和密码（密码不会显示）",
    )
    return parser.parse_args()


def save_credentials(path):
    username = input("水木用户名: ").strip()
    if not username:
        raise SystemExit("用户名不能为空")
    password = getpass.getpass("水木密码: ")
    if not password:
        raise SystemExit("密码不能为空")

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as credential_file:
            credential_file.write(f"username={username}\npassword={password}\n")
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)
    print(f"凭据已保存到：{path}")


def load_credentials(path):
    try:
        with open(path, encoding="utf-8") as credential_file:
            values = {}
            for line in credential_file:
                key, separator, value = line.rstrip("\n").partition("=")
                if separator:
                    values[key.strip().lower()] = value
    except FileNotFoundError:
        return None
    except OSError as error:
        print(f"无法读取凭据文件：{error}", file=sys.stderr)
        return None

    username = values.get("username") or values.get("user")
    password = values.get("password") or values.get("pass")
    if not username or password is None:
        print(f"凭据文件格式不完整：{path}", file=sys.stderr)
        return None
    return username, password


def main():
    args = parse_args()
    if args.setup:
        save_credentials(args.credentials)
        return 0
    if args.heartbeat < 0:
        raise SystemExit("--heartbeat 不能是负数")

    try:
        codecs.lookup(args.encoding)
    except LookupError:
        raise SystemExit(f"系统不支持编码：{args.encoding}")

    credentials = load_credentials(args.credentials)

    # -8 让 telnet 不把高位字节截成 7-bit；TERM=ansi 对老式 BBS 更稳妥。
    env = os.environ.copy()
    env["TERM"] = env.get("BBS_TERM", "ansi")

    pid, master_fd = pty.fork()
    if pid == 0:
        os.execvpe("telnet", ["telnet", "-8", args.host, str(args.port)], env)

    old_attrs = termios.tcgetattr(sys.stdin.fileno())
    decoder_in = codecs.getincrementaldecoder("utf-8")(errors="replace")
    encoder_out = codecs.getincrementalencoder(args.encoding)(errors="replace")
    decoder_out = codecs.getincrementaldecoder(args.encoding)(errors="replace")
    stdin_fd = sys.stdin.fileno()
    last_activity = time.monotonic()
    auto_username_sent = False
    auto_password_sent = False
    prompt_buffer = ""

    def send_text(text):
        os.write(master_fd, encoder_out.encode(text + "\r", final=False))

    def auto_login(text):
        nonlocal auto_username_sent, auto_password_sent, prompt_buffer
        if not credentials:
            return

        # 去掉 ANSI 控制序列后再识别提示词；提示词可能被拆在多个数据包中。
        prompt_buffer = (prompt_buffer + ANSI_RE.sub("", text))[-4096:]
        searchable = prompt_buffer.replace("\r", " ").replace("\n", " ").lower()
        username_prompt = re.search(
            r"(?:login(?:\s*(?:name|id))?|username|user\s*name|account|user|用户名|帐号|账号|登录名|请输入[^：:]{0,16}(?:名|号))\s*[：:]?\s*$",
            searchable,
        )
        password_prompt = re.search(r"(?:password|passwd|密码)\s*[：:]?\s*$", searchable)

        if not auto_username_sent and username_prompt:
            send_text(credentials[0])
            auto_username_sent = True
            prompt_buffer = ""
        elif auto_username_sent and not auto_password_sent and password_prompt:
            send_text(credentials[1])
            auto_password_sent = True
            prompt_buffer = ""

    def restore_terminal(*_):
        try:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_attrs)
        except (OSError, termios.error):
            pass

    def stop_child(*_):
        try:
            os.kill(pid, signal.SIGHUP)
        except ProcessLookupError:
            pass

    try:
        tty.setraw(stdin_fd)
        signal.signal(signal.SIGTERM, stop_child)
        signal.signal(signal.SIGINT, stop_child)
        sys.stderr.write(
            f"\033[2m[NewSMTH {args.encoding}, 心跳 {args.heartbeat:g}s；按 Ctrl-] 退出 telnet，再按 q]\033[0m\n"
        )
        sys.stderr.flush()

        while True:
            timeout = None
            if args.heartbeat:
                timeout = max(0.0, args.heartbeat - (time.monotonic() - last_activity))

            readable, _, _ = select.select([stdin_fd, master_fd], [], [], timeout)

            if not readable and args.heartbeat:
                # NUL 是 Telnet/终端中无显示效果的字节，比发送回车安全。
                try:
                    os.write(master_fd, b"\x00")
                    last_activity = time.monotonic()
                except OSError:
                    break
                continue

            if stdin_fd in readable:
                data = os.read(stdin_fd, 4096)
                if not data:
                    break
                text = decoder_in.decode(data, final=False)
                if text:
                    os.write(master_fd, encoder_out.encode(text, final=False))
                last_activity = time.monotonic()

            if master_fd in readable:
                try:
                    data = os.read(master_fd, 8192)
                except OSError:
                    break
                if not data:
                    break
                text = decoder_out.decode(data, final=False)
                if text:
                    auto_login(text)
                    sys.stdout.write(text)
                    sys.stdout.flush()

    finally:
        restore_terminal()
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            _, status = os.waitpid(pid, 0)
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
        except ChildProcessError:
            pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        # 终端属性已在 main() 的 finally 中恢复。
        raise SystemExit(130)
