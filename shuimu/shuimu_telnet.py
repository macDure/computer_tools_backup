#!/usr/bin/env python3
"""shuimu_telnet.py — 水木 telnet 客户端（raw socket + 现有脚本的屏幕渲染引擎）

已验证的交互序列 (2026-09-02 实测):
  连 23 端口 → 登录 → n 翻提示页 → S 讨论区 → 版面名 → n 翻提示
  列表:  > id  author  Mon DD  title   (光标 > 标记)
  读帖: r 读当前选中 → q 返回列表(光标保持) → j 下移一位
  编码: gb18030; ANSI 用现有 shuimu-scrape.py 的 render_terminal_screen 渲染
"""
import fcntl
import os
import random
import re
import select
import socket
import sys
import time


def human_pause(base, spread=0.0, p_long=0.0, long_range=(2.0, 5.0)):
    """2026-09-07 拟人化停顿(用户指令: 固定节奏像机器操作, 易触发限流识别).
    base ± uniform(spread) 抖动, 且 p_long 概率追加一段'走神'长停顿.
    所有按键间隔走这里, 让节奏不可被简单周期性检测命中."""
    d = base + random.uniform(-spread, spread)
    if p_long and random.random() < p_long:
        d += random.uniform(*long_range)
    time.sleep(max(0.2, d))

# 2026-09-07 用户指令: 账号处于限流期, 并发会话会互踢/激化限流.
# 全局单会话锁: 任何脚本(定时爬虫/补爬/smoke/手动)的 BBS 登录先抢此锁,
# 整个 telnet 会话期间持有, close() 释放. flock 随进程退出自动释放, 无僵尸锁.
SESSION_LOCK_PATH = "/tmp/shuimu_session.lock"


class SessionBusy(RuntimeError):
    """另一个水木 telnet 会话正在运行(持锁). 上层应跳过本次运行, 不得等待后硬抢."""

# 复用现有脚本的屏幕渲染/可见文本函数(只 import 不执行 main)
# 可移植: 优先本目录副本 legacy_shuimu_scrape.py, 回退历史备份目录
_OLD_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legacy_shuimu_scrape.py") \
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "legacy_shuimu_scrape.py")) \
    else "/host-home/macperson/computer_tools_backup/shuimu/shuimu-scrape.py"


def _load_old():
    import importlib.util
    spec = importlib.util.spec_from_file_location("shuimu_old", _OLD_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_OLD = _load_old()

LINE_RE = re.compile(
    r"^\s*(?:(>|\|)\s*)?(\d{6,7})\s+\*?\s*(\S+)\s+"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:\s+\d+)?|(?:\d{1,2}/\d{1,2}))\s{1,3}(●\s*)?(.+)$"
)
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

ART_HEADER_RE = re.compile(r"发信人: (\S+) \(([^)]*)\), 信区: (\S+)")
ART_TIME_RE = re.compile(r"发信站:.*?\((\w{3} \w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2} \d{4})\)")
ART_TITLE_RE = re.compile(r"标\s*题: (.+)")


def parse_list(screen_text, year):
    """解析版面列表屏, 返回 [{id, author, mon, day, orig, title}]"""
    rows = []
    for ln in screen_text.split("\n"):
        m = LINE_RE.match(ln)
        if not m:
            continue
        _cursor, aid, author, date_s, _dot, title = m.groups()
        mon = date_s.split()[0] if " " in date_s else None
        day = None
        if mon and mon in MONTHS:
            parts = date_s.split()
            day = int(parts[1])
            rows.append({"id": aid, "author": author, "mon": mon,
                         "day": day, "year": year, "title": title.strip(),
                         "orig": bool(_dot)})
    return rows


def parse_article(screen_text, year):
    """解析读帖屏, 返回 {author, nick, board, title, time_str, body}"""
    t = screen_text
    out = {"author": None, "nick": None, "board": None, "title": None,
           "time_str": None, "body": ""}
    m = ART_HEADER_RE.search(t)
    if m:
        out["author"], out["nick"], out["board"] = m.groups()
    mt = ART_TIME_RE.search(t)
    if mt:
        out["time_str"] = mt.group(1)
    mm = ART_TITLE_RE.search(t)
    if mm:
        out["title"] = mm.group(1).strip()
    # body: 时间行之后, 到 --  或 ※来源 或 页脚 [阅读文章]
    body_start = t.find("\n\n", (mt.end() if mt else 0))
    body = t[body_start + 2:] if body_start > 0 else t
    # 截到页脚
    for cut in ("\n--\n", "[阅读文章]", "[主题阅读]", "※ 来源"):
        idx = body.find(cut)
        if idx > 0:
            body = body[:idx]
    # 去 ANSI/多余空行
    body = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", body)
    lines = [l.rstrip() for l in body.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    out["body"] = "\n".join(lines)
    return out


def parse_time_str(ts, default_year):
    """'Thu Sep  3 00:40:35 2026' → (month, day, hour, minute, year)"""
    try:
        from datetime import datetime
        dt = datetime.strptime(ts, "%a %b %d %H:%M:%S %Y")
        return dt.month, dt.day, dt.hour, dt.minute, dt.year
    except Exception:
        return None, None, None, None, default_year


SEL_ROW_RE = re.compile(r"\s*>\s*(\d{6,7})\s+\*?\s*(.*)$")


def parse_sel_row(ln, year=2026):
    """宽容解析列表选中行 (2026-09-03 修复).
    跨页 ANSI 重绘残留会在作者栏塞入如 'Ju' 的脏字符, 严格正则失配
    导致遍历卡死. 改为: 行首 id(最稳) + 第一个合法'月份+日' 组合,
    残留片段(1-2 字符)匹配不上完整'月份+日'自然跳过.
    返回 (id, author, date, title) 或 None."""
    import datetime as _dt
    m = SEL_ROW_RE.match(ln)
    if not m:
        return None
    aid = m.group(1)
    rest = m.group(2).strip()
    dm = None
    for dm in re.finditer(r"([A-Z][a-z]{2,3})\s+(\d{1,2})", rest):
        if dm.group(1) in MONTHS:
            break
    if dm is None or dm.group(1) not in MONTHS:
        return None
    prefix = rest[:dm.start()].strip()
    toks = [t for t in prefix.split() if t not in ("*", "●", "@")]
    author = toks[0] if toks else "?"
    title = rest[dm.end():].strip()
    return aid, author, _dt.date(year, MONTHS[dm.group(1)], int(dm.group(2))), title


class BBS:
    def __init__(self, host="bbs.newsmth.net", port=23, encoding="gb18030",
                 credentials="/host-home/.config/newsmth/credentials"):
        self.host, self.port, self.encoding = host, port, encoding
        self.cred = credentials
        self.s = None
        self.stream = []

    def _recv(self, sec=2.0, deadline=None):
        end = time.time() + sec
        if deadline is not None:
            end = min(end, deadline)
        while time.time() < end:
            r, _, _ = select.select([self.s], [], [], 0.3)
            if r:
                try:
                    c = self.s.recv(8192)
                    if not c:
                        break
                    self.stream.append(c.decode(self.encoding, "replace"))
                    self._trim_stream()
                except socket.timeout:
                    break
        if deadline is not None and time.time() >= deadline:
            raise socket.timeout("server silent past deadline")

    def _trim_stream(self):
        """限制累积流长度, 根治 O(n^2) 渲染爆炸.
        BBS 每次刷新整屏重绘(以 \\x1b[H 归位开头, 单屏仅数 KB).
        小会话(单屏流)完全不裁, 零风险; 长会话(多帖遍历)流超 60KB 时,
        回退到"尾部 <=40KB 的最后一个归位点"处截断, 保留当前屏+十余屏余量,
        同时消除新旧帧 ANSI 串扰. screen() 从截断点重放即可还原当前屏."""
        s = "".join(self.stream)
        if len(s) <= 60000:
            return
        # 找尾部不超过 40KB 的最后一个 \x1b[H
        limit = len(s) - 40000
        idx = s.rfind("\x1b[H", 0, limit)
        if idx > 0:
            self.stream = [s[idx:]]

    def send(self, text):
        self.s.sendall(text.encode(self.encoding, "replace"))

    def screen(self):
        return _OLD.render_terminal_screen("".join(self.stream))

    def clear(self):
        """清空累积流, 避免新旧帧 ANSI 重绘交叉产生伪影
        (如 发信人: str**cf515** / 时间 Thu Sep**Wed 00:16** 混排).
        用于同一界面连续切换内容(主题阅读翻页)前."""
        self.stream = []

    def screen_fresh(self):
        """只重放最后一帧(以 \\x1b[H 归位为帧边界)渲染.
        BBS 主题阅读每次翻页整屏重绘, 但短行覆盖长行不清行尾,
        累积重放会串扰旧内容; 取最后一帧可消除 (2026-09-03 实测).
        列表遍历等已验证路径仍用 screen()."""
        s = "".join(self.stream)
        idx = s.rfind("\x1b[H")
        if idx > 0:
            s = s[idx:]
        return _OLD.render_terminal_screen(s)

    def visible(self):
        return _OLD.visible_terminal_text(self.screen())

    def selected_id(self):
        for ln in self.screen().split("\n"):
            m = re.match(r"\s*>\s*(\d{6,7})", ln)
            if m:
                return m.group(1)
        return None

    def login(self, username=None, password=None):
        self.s = socket.create_connection((self.host, self.port), timeout=20)
        self.s.settimeout(6)
        self.stream = []
        self._recv(3.0)
        vals = {}
        if username is None or password is None:
            for line in open(self.cred):
                k, sep, v = line.rstrip("\n").partition("=")
                if sep:
                    vals[k.strip()] = v
            username = username or vals["username"]
            password = password or vals["password"]
        self.send(username + "\r"); time.sleep(1.5)
        self.send(password + "\r"); time.sleep(2.5)
        # 2026-09-07: 静默看门狗 — 服务器 accept 后零响应(限流静默挂起,
        # 实测 17 分钟零字节)会在 recv 上永久挂死. 登录全程 90s 内必须有响应.
        dl = time.time() + 90
        # 登录成功后第一个提示是 "按 [RETURN] 继续" — 先发纯 RETURN
        self.send("\r"); self._recv(1.2, deadline=dl)
        # 按界面内容导航到主选单 (2026-09-03 实测: 登录后会随机插
        # 提示页/上站记录页/好友列表; 好友列表按 n 会选进好友资料页跑偏, 必须 q)
        for _ in range(35):
            scr = self.screen()
            if "主选单" in scr:
                return True
            if "好朋友列表" in scr:
                self.send("q"); self._recv(1.0, deadline=dl)
                continue
            if "按任何键" in scr or "按任意键" in scr or "按 [RETURN]" in scr:
                self.send("n\r"); self._recv(0.9, deadline=dl)
                continue
            # 未知页(上站记录等) — 翻页继续
            self.send("n\r"); self._recv(0.9, deadline=dl)
        raise RuntimeError("登录后未到达主选单")

    def _acquire_session_lock(self):
        """抢全局单会话锁(非阻塞). 幂等: 同实例已持锁直接返回.
        抢不到立即抛 SessionBusy — 上层跳过本次运行, 不排队不硬抢(用户要求)."""
        if getattr(self, "_lock_fd", None) is not None:
            return
        fd = os.open(SESSION_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise SessionBusy(
                "另一个水木 telnet 会话正在运行(%s 被占), 本次跳过以保账号" % SESSION_LOCK_PATH)
        # 覆盖写入持有者信息, 便于排查(锁本身靠 flock, 内容仅诊断用)
        os.ftruncate(fd, 0)
        os.write(fd, ("pid=%d started=%s\n" % (os.getpid(),
                  time.strftime("%F %T %Z", time.gmtime()))).encode())
        os.lseek(fd, 0, os.SEEK_SET)
        # 存到实例上, close 时释放; 进程被杀时内核自动释放 flock
        self._lock_fd = fd

    def _release_session_lock(self):
        fd = getattr(self, "_lock_fd", None)
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            except OSError:
                pass
            self._lock_fd = None

    def _drop_socket(self):
        """断掉 socket 保留会话锁 — 登录失败重试前用(锁是进程级会话锁,
        重试间隙释放会留互斥漏洞, 让别的进程插进来开第二个会话)."""
        try:
            if self.s is not None:
                self.s.close()
        except Exception:
            pass
        self.s = None
        self.stream = []

    def login_with_retry(self, tries=3, wait=8):
        """登录间歇性时序失步(2026-09-03 实测: 同凭据时成时败), 整体重试.
        2026-09-07: 登录前先抢全局单会话锁(非阻塞, 抢不到抛 SessionBusy);
        重试只断 socket 不释放锁, 锁跟随整个会话, 直到 close() 或彻底放弃."""
        self._acquire_session_lock()
        last = None
        try:
            for i in range(tries):
                try:
                    self._drop_socket()
                    return self.login()
                except Exception as e:
                    last = e
                    print("  login attempt %d failed: %s" % (i + 1, e), flush=True)
                    if i + 1 < tries:
                        time.sleep(wait)
            raise last
        finally:
            # 3 次全败才在此释放; 成功路径锁跟随会话由 close() 释放
            if self.s is None:
                self._release_session_lock()

    def open_board(self, board, tries=4):
        """进版面 — 高峰(40万在线)时屏幕渲染间歇变慢/连接被重置,
        2026-09-03 实测同一代码时成时败, 整体重试(重连)."""
        last = None
        for i in range(tries):
            try:
                self._open_board_once(board)
                return
            except Exception as e:
                last = e
                print("  open_board attempt %d failed: %s" % (i + 1, e), flush=True)
                time.sleep(6)
        raise last

    def _open_board_once(self, board):
        # 2026-09-07 静默看门狗: 进版面全程 60s 内必须有服务器响应
        dl = time.time() + 60
        # 2026-09-07: 进版面前清屏 — 被踢回主选单后, 渲染屏残留上一列表帧
        # (实测 RECOVER 日志: 主选单顶栏 + 列表行/帮助行混合), 残留会让
        # "离开[ 选择[ 阅读[" 判定假阳性. 清掉后判定才有意义.
        self.clear()
        self.send("S\r"); time.sleep(1.2); self._recv(2.5, deadline=dl)
        if "选择讨论区" not in self.visible():
            self.send("\r"); self._recv(2.5, deadline=dl)
        self.send(board + "\r"); time.sleep(0.8); self._recv(2.5, deadline=dl)
        # 翻过"按任何键"提示; 一旦到列表(一般模式)即停
        for _ in range(5):
            if "一般模式" in self.screen():
                break
            if "按任何键" in self.visible():
                self.send("n\r"); self._recv(1.5, deadline=dl)
            else:
                time.sleep(0.5); self._recv(0.8, deadline=dl)
        self._recv(1.0, deadline=dl)
        # 2026-09-07 修复: 主选单顶栏第一行也带 "讨论区 [当前区]", 单查该串会把
        # 仍在主选单的状态误判成已进版面(实测 RECOVER 日志). 权威标记=列表帮助行.
        head = "\n".join(self.screen().split("\n")[:6])
        if not ("离开[" in head and "阅读[" in head):
            raise RuntimeError("未能进入版面 %s" % board)

    def list_rows(self, year):
        return parse_list(self.screen(), year)

    def read_current(self):
        self.send("r"); time.sleep(0.8); self._recv(1.8)
        return parse_article(self.screen(), year=9999)

    def back(self):
        self.send("q"); human_pause(0.6, spread=0.2); self._recv(1.3)

    def move_down(self):
        self.send("j"); human_pause(0.6, spread=0.2); self._recv(1.0)

    def close(self):
        try:
            self.send("q\r")
            time.sleep(0.3)
            self.send("G\r")
        except Exception:
            pass
        try:
            self.s.close()
        except Exception:
            pass
        self._release_session_lock()


    def read_current_paged(self, max_pages=8):
        """读当前帖, 长帖自动 space 翻页, 拼接全文. 返回 parse_article 结果(含 body)."""
        self.send("r"); human_pause(0.9, spread=0.3, p_long=0.04); self._recv(1.8)
        parts = []
        first = True
        for p in range(max_pages):
            scr = self.screen()
            art = parse_article(scr, 9999)
            if first:
                meta = art
                first = False
            parts.append(art["body"])
            # 分页标记: 下面还有喔 (X%)  或  第(A-B)行
            if re.search(r"下面还有喔", scr) or re.search(r"第\(\d+-\d+\)行", scr):
                # 2026-09-07 拟人化: 读长帖翻页像"看完一段再翻", 1.0~1.9s + 5% 长停顿
                self.send(" "); human_pause(1.4, spread=0.5, p_long=0.05); self._recv(1.4)
                continue
            break
        meta["body"] = "\n".join(x for x in parts if x.strip())
        return meta


    def back_robust(self):
        """回到列表, 处理长帖需多次 q 的情况.
        2026-09-03 修复: 原实现最后兜底发 'e' — 但列表界面 'e' 是
        "离开版面"键, 时序抖动时误发会把会话踢出版面(主选单), 导致遍历卡死.
        现只用 'q', 加长确认等待."""
        for key in ("q", "q", "q"):
            self.send(key); time.sleep(0.5); self._recv(1.4)
            if "一般模式" in self.visible() or re.search(r">\s*\d{6,7}", self.screen()) \
               or re.search(r">\s*\d{6,7}", self.screen_fresh()):
                return
        self._recv(0.5)


    def move_up(self):
        # 2026-09-07 拟人化: 0.5~1.3s 抖动 + 2.5% 概率"走神"2-5s
        self.send("k"); human_pause(0.9, spread=0.4, p_long=0.025); self._recv(1.0)


    def is_hint_line(ln):
        """列表底部 [提示] 固定公告行, 非真实帖子."""
        return bool(re.match(r"\s*>?\s*\[提示\]", ln))

if __name__ == "__main__":
    from datetime import datetime
    b = BBS()
    b.login()
    b.open_board("Stock")
    now = datetime.now()
    rows = b.list_rows(now.year)
    print("board rows:", len(rows))
    for r in rows[:5]:
        print(" ", r["id"], r["author"], r["mon"], r["day"], (r["orig"] and "●") or " ", r["title"][:40])
    art = b.read_current()
    print("read current:", art["author"], art["title"], "| time:", art["time_str"])
    print("body head:", art["body"][:120].replace("\n", " / "))
    b.back()
    b.close()
    print("SELFTEST_OK")
