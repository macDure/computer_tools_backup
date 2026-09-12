#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nf_crawler.py — 水木 Stock 版高速爬虫 (nForum JSON API, HTTP Basic 认证)。

取代 telnet 方案。一次全量遍历:
  1) 列表遍: board/index/Stock.json (mode=2 按最后回复时间倒序, 翻页到 STOP_TIME 为止)
  2) 全文遍: 对命中缺口窗的每个串 threads/Stock/<gid>.json 拉全部楼层
  3) 按首帖时间 4h 分桶, 写入归档仓 /opt/data/shuimu_daily/年/月/日/wHH/
     (meta.json + 原帖_Stock.md, 与 telnet 归档格式兼容)
  4) 更新 backfill_queue.json 状态 + git 提交

只读纪律: 只调用 board/index, threads 两个只读端点。
认证: HTTP Basic (nForum API 不认 cookie 会话, 只认 Authorization: Basic —
     源码 basic_auth.php)。凭据: /host-home/.config/newsmth/credentials (只读, 值不落日志)
     服务端会话槽满时返回 code=0102 "账号过多", 自动退避重试。
限速: 请求间 0.6~1.6s 随机 (API 快, 保守低频防风控)。
风控: 09-12 用户指令切 Scrapling 式"对服务端信号响应"范式 —
     429 读 Retry-After (缺省 300s, 上限 1800s) 后退避; 5xx/异常按 2^n 指数退避
     (base 30s, 上限 600s); 连续 5 次硬失败 -> 写 .rate_limited.json + exit 4 停手
     (看门狗 bump_fail, 3 次进 6h 冷却并飞书报警); 200 成功即清零退避与连败计数。
     401 凭据错=终止 (非风控, 硬扛无意义)。
"""
import base64, json, os, random, re, subprocess, sys, time, datetime as dt
from email.utils import parsedate_to_datetime
from scrapling.fetchers import FetcherSession

HERE = os.path.dirname(os.path.abspath(__file__))
# 可移植: 路径解析顺序 = 环境变量 > 本目录惯例 > 本机生产默认值 (生产行为不变, 换机开箱即用)
def _resolve_creds():
    if os.environ.get("SHUIMU_CREDS"):
        return os.environ["SHUIMU_CREDS"]
    for c in (os.path.join(HERE, "credentials"),
              os.path.expanduser("~/.config/newsmth/credentials"),
              "/host-home/.config/newsmth/credentials"):
        if os.path.exists(c):
            return c
    return os.path.expanduser("~/.config/newsmth/credentials")

def _resolve_archive():
    if os.environ.get("SHUIMU_ARCHIVE"):
        return os.environ["SHUIMU_ARCHIVE"]
    local = os.path.join(HERE, "archive")
    if os.path.isdir(local):
        return local
    return "/opt/data/shuimu_daily" if os.path.isdir("/opt/data/shuimu_daily") else local

CREDS = _resolve_creds()
QUEUE = os.path.join(HERE, "backfill_queue.json")
ARCHIVE = _resolve_archive()
LOGF = os.path.join(HERE, "logs", "nf_crawler.log")
BASE = "https://www.newsmth.net/nForum/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
BOARD = "Stock"
STOP_TIME = "2026-08-31 00:00:00"   # 列表遍历截止 (按 last_reply_time 倒序, 早于它即停)
                                          # = 队列 pending 最早窗 08-31 00:00 (w00 复核轮)
PAGE_COUNT = 50                       # 每页主题数 (page_item_limit 未知, 50 稳)

os.makedirs(os.path.dirname(LOGF), exist_ok=True)
_logf = open(LOGF, "a", encoding="utf-8")
def log(msg, flush=True):
    line = "[%s] %s" % (dt.datetime.now().strftime("%m-%d %H:%M:%S"), msg)
    print(line, flush=flush)
    _logf.write(line + "\n"); _logf.flush()

TZ = dt.timezone(dt.timedelta(hours=8))

def load_auth():
    """读凭据文件 -> base64 basic token; 失败返回 None (值不落日志)"""
    try:
        u = p = None
        for ln in open(CREDS):
            ln = ln.strip()
            if ln.startswith("username="): u = ln.split("=", 1)[1].strip()
            elif ln.startswith("password="): p = ln.split("=", 1)[1].strip()
        if not u or not p: return None
        return base64.b64encode(f"{u}:{p}".encode()).decode()
    except Exception:
        return None

def bucket_of(t):
    """首帖时间 -> (归档目录, slot标签, 窗起止str)"""
    d = t.strftime("%Y/%m/%d")
    h = t.hour
    slot = "w%02d" % (h - (h % 4))
    ws = "%s %02d:00-%02d:00" % (t.strftime("%Y-%m-%d"), h - (h % 4), h - (h % 4) + 4)
    return d, slot, ws

class NF:
    # 风控信号响应参数 (Scrapling AutoThrottle 范式: 被动响应服务端信号)
    RL_MAX = 5            # 连续硬失败 N 次 -> 放弃本轮 (exit 4), 交给看门狗冷却
    BASE_BACKOFF = 30     # 5xx/异常指数退避基数 (秒)
    MAX_BACKOFF = 600     # 指数退避上限
    def __init__(self, token):
        self._sess = FetcherSession(impersonate="chrome")
        self.s = self._sess.__enter__()   # 返回 _SyncSessionLogic, 才有 .get
        self.h = {"User-Agent": UA, "Authorization": "Basic " + token,
                  "Referer": f"https://www.newsmth.net/nForum/board/{BOARD}"}
        self.n = 0
        self.unauth = False
        self.slot_full = False
        self.consec_hard = 0   # 连续硬失败 (429/5xx/异常) 计数; 200 成功清零
    def _gap(self):
        time.sleep(random.uniform(0.6, 1.6))
    def _parse_retry_after(self, r):
        """读 Retry-After 头 (秒数或 HTTP 日期); 读不到返回 None (Scrapling 同款实现)
        实测: scrapling 静态引擎的 r.headers 是小写键 dict"""
        try:
            val = None
            try:
                val = (r.headers.get("retry-after") or "").strip()
            except Exception:
                pass
            if not val:
                return None
            try:
                return max(float(val), 0.0)
            except ValueError:
                try:
                    return max((parsedate_to_datetime(val) - dt.datetime.now(dt.timezone.utc)).total_seconds(), 0.0)
                except (TypeError, ValueError):
                    return None
        except Exception:
            return None
    def _rate_limited_stop(self, why):
        """连败到顶: 写风控信号文件, 退出码 4 (看门狗 bump_fail -> 3 次进 6h 冷却+报警)"""
        try:
            with open(os.path.join(HERE, ".rate_limited.json"), "w") as f:
                json.dump({"until": time.time(), "reason": why,
                           "ts": dt.datetime.now(dt.timezone.utc).isoformat()}, f)
        except Exception:
            pass
        log("=== 风控信号停手: %s (连续硬失败 %d 次, 交给看门狗冷却) ===" % (why, self.consec_hard))
        self.close()
        sys.exit(4)
    def get_json(self, path):
        self.n += 1
        for attempt in range(3):
            try:
                r = self.s.get(BASE + path, headers=self.h, timeout=30)
                if r.status == 401:
                    if not self.unauth:
                        self.unauth = True
                        log("401 未授权! 凭据错误 — 终止 (非风控信号, 硬扛无意义)")
                    return None
                if r.status == 429:
                    # 风控信号: 服务端明确限速 — 优先服从 Retry-After, 否则 300s
                    ra = self._parse_retry_after(r)
                    wait = ra if (ra is not None and 0 < ra <= 1800) else 300
                    self.consec_hard += 1
                    log("429 限流! %s — 退避 %gs (Retry-After=%s), 第 %d 次硬失败"
                        % (path, wait, ra, self.consec_hard))
                    if self.consec_hard >= self.RL_MAX:
                        self._rate_limited_stop("429 限流, 最后一次 Retry-After=%.0fs" % wait)
                    time.sleep(wait)
                    continue
                if r.status != 200:
                    # 5xx = 服务端受阻信号: 指数退避 2^attempt * 30s (Scrapling block_backoff 式翻倍)
                    wait = min(self.BASE_BACKOFF * (2 ** attempt), self.MAX_BACKOFF)
                    self.consec_hard += 1
                    log("HTTP %s on %s (attempt %d) — 指数退避 %ds, 第 %d 次硬失败"
                        % (r.status, path, attempt, wait, self.consec_hard))
                    if self.consec_hard >= self.RL_MAX:
                        self._rate_limited_stop("HTTP %s 连败" % r.status)
                    time.sleep(wait)
                    continue
                b = r.body
                if isinstance(b, bytes): b = b.decode("utf-8", "replace")
                d = json.loads(b)
                # 业务错误码 (HTTP 200 但 code!=None 表示服务端拒绝)
                if isinstance(d, dict) and d.get("code"):
                    if d["code"] == "0102":
                        # 登录槽满: 浏览器会话占槽。退避 30s 重试; 3 次仍满则终止
                        if not self.slot_full:
                            self.slot_full = True
                            log("0102 登录槽满 (浏览器会话占位?) — 退避 30s 重试")
                        time.sleep(30 + attempt * 30)
                        continue
                    log("API 错误码 %s: %s — 终止" % (d["code"], d.get("msg", "")[:50]))
                    return None
                self.consec_hard = 0   # 200 成功: 风控压力解除, 清零退避与连败计数
                self._gap()
                return d
            except Exception as e:
                wait = min(self.BASE_BACKOFF * (2 ** attempt), self.MAX_BACKOFF)
                self.consec_hard += 1
                log("ERR %s on %s (attempt %d): %s — 退避 %ds, 第 %d 次硬失败"
                    % (type(e).__name__, path, attempt, str(e)[:100], wait, self.consec_hard))
                if self.consec_hard >= self.RL_MAX:
                    self._rate_limited_stop("网络/异常连败: %s" % str(e)[:60])
                time.sleep(wait)
        log("放弃 %s" % path); return None
    def board_page(self, page):
        return self.get_json(f"/board/index/{BOARD}.json?count={PAGE_COUNT}&page={page}")
    def threads(self, gid, page=1, count=50):
        return self.get_json(f"/threads/{BOARD}/{gid}.json?count={count}&page={page}")
    def close(self):
        try: self._sess.__exit__(None, None, None)
        except Exception: pass

def parse_time(s):
    """API 时间 '2026-09-09 08:23:45' -> aware dt (北京时间); 兼容 epoch 秒/毫秒"""
    if not s: return None
    if isinstance(s, (int, float)):
        ts = s / 1000 if s > 1e12 else s  # 毫秒兼容
        try: return dt.datetime.fromtimestamp(ts, TZ)
        except Exception: return None
    s = str(s)
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try: return dt.datetime.strptime(s, f).replace(tzinfo=TZ)
        except ValueError: pass
    return None


def load_pending_windows():
    """队列 pending 窗 -> {label: (start_dt, end_dt)}; 失败则返回 None (退回全桶行为)"""
    try:
        q = json.load(open(QUEUE))
        pw = {}
        for t in q["tasks"]:
            if t.get("status") != "pending": continue
            lab = t.get("label", "")
            m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})-(\d{2}):(\d{2})$", lab)
            if not m:
                log("队列 label 无法解析, 跳过: %r" % lab); continue
            d, h1, m1, h2, m2 = m.groups()
            base = dt.datetime.strptime(d + " 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
            pw[lab] = (base + dt.timedelta(hours=int(h1), minutes=int(m1)),
                       base + dt.timedelta(hours=int(h2), minutes=int(m2)))
        log("队列 pending 窗: %d" % len(pw))
        return pw
    except Exception as e:
        log("读队列失败(%s): 退回全桶行为(只写不碰队列状态)" % e)
        return None

def clean_content(c):
    """API content 可能带 HTML/引用块, 保留原样 (与 telnet 归档同源格式)"""
    return c or ""

def posts_from_api(posts, fallback):
    """API article[] -> 归档帖 dict 列表 (含附件信息)。
    附件下载路由 (源码 wrapper.php + api/attachment_controller.php):
      API 返回的 file.url 是 web 路由 (/attachment/Stock/<aid>/<pos>, 需 XWJOKE cookie, 匿名 404)
      API 路由 = BASE + /attachment/Stock/<aid>/<pos> (Basic 认证即可, controller 无 cookie 检查)
      aid/pos 直接取 file.url 末两段 (url 段是 article_id, 回复楼 != 主题 gid!)
    """
    out = []
    for p in posts:
        atts = []
        for f in ((p.get("attachment") or {}).get("file") or []):
            u = (f.get("url") or "").rstrip("/")
            parts = u.split("/")
            api_url = (BASE + "/attachment/" + "/".join(parts[-3:])) \
                if len(parts) >= 3 and parts[-1].isdigit() else None
            raw = f.get("name") or "attachment"
            safe = re.sub(r'[\\/:*?"<>|\r\n\t ]+', "_", raw)[:80] or "attachment"
            ext = os.path.splitext(raw)[1].lower()
            atts.append({
                "name": raw, "size": f.get("size"),
                "api_url": api_url,
                "fname": "%s_%s" % (p.get("id") or 0, safe),
                "is_img": ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"),
            })
        out.append({
            "time": parse_time(p.get("post_time")) or fallback,
            "author": ((p.get("user") or {}).get("user_name") or (p.get("user") or {}).get("id")) if isinstance(p.get("user"), dict) else str(p.get("user") or "?"),
            "content": p.get("content") or "",
            "attachments": atts,
        })
    return out

def download_attachment(nf, url, dest):
    """API 路由 + Basic 下载附件; 校验非 HTML; 返回成功与否"""
    try:
        r = nf.s.get(url, headers=nf.h, timeout=60)
        if r.status != 200 or not r.body:
            log("附件 HTTP %s: %s" % (r.status, url.split("/")[-1])); return False
        data = r.body if isinstance(r.body, bytes) else r.body.encode("utf-8", "replace")
        if data.lstrip()[:1] == b"<":
            log("附件返回 HTML (非文件): %s" % url.split("/")[-1]); return False
        open(dest, "wb").write(data)
        return True
    except Exception as e:
        log("附件下载异常 %s: %s" % (type(e).__name__, str(e)[:80])); return False

def download_bucket_attachments(nf, win_dir, tinfo):
    """下载一个窗内所有帖的附件 -> win_dir/attachments/ (幂等: 已存在非空跳过)。
    返回 (ok, fail)"""
    adir = os.path.join(win_dir, "attachments")
    n_ok = n_fail = 0
    for t in tinfo:
        for p in t["posts"]:
            for f in p.get("attachments") or []:
                if not f.get("api_url"):
                    n_fail += 1; continue
                dest = os.path.join(adir, f["fname"])
                if os.path.exists(dest) and os.path.getsize(dest) > 0:
                    n_ok += 1; continue   # 幂等重跑
                os.makedirs(adir, exist_ok=True)
                nf._gap()
                if download_attachment(nf, f["api_url"], dest):
                    n_ok += 1
                else:
                    n_fail += 1
    if n_ok or n_fail:
        log("附件下载: 成功 %d / 失败 %d" % (n_ok, n_fail))
    return n_ok, n_fail

def write_archive(day_dir, slot, win_label, threads_info, arch_root=ARCHIVE):
    """threads_info: [{title, gid, first_time, posts:[{time, author, content, attachments}]}]
    数据安全: 目标目录已存在(旧 telnet 残留)时先移动到 .bak_nf 备份, 绝不静默覆盖。
    meta.json 完整结构 (09-12 用户指令: 主题/发帖人/时间/正文/图片信息齐全, 深度挖掘直接读 meta):
      threads[]: {title, gid, is_new_today, first_time_bj, last_time_bj, post_count,
                  authors, posts:[{seq, time, author, content, attachments:[{name,size,fname,is_img}]}]}"""
    d = os.path.join(arch_root, day_dir, slot)
    if os.path.isdir(d) and any(os.listdir(d)):
        # 同模式 (nf_api) 重跑 = 增量覆盖, 不备份; 异模式 (telnet 旧档) 才 .bak_nf 备份
        same_mode = False
        if os.path.exists(os.path.join(d, "meta.json")):
            try:
                same_mode = json.load(open(os.path.join(d, "meta.json"))).get("mode") == "nf_api"
            except Exception:
                pass
        if same_mode:
            log("覆盖同模式归档 %s/%s" % (day_dir, slot))
        else:
            bak = d + ".bak_nf_%d" % int(time.time())
            os.rename(d, bak)
            log("⚠ 已有归档目录(旧模式), 备份到 %s" % bak)
    os.makedirs(d, exist_ok=True)
    post_count = sum(len(t["posts"]) for t in threads_info)
    att_count = sum(len(p.get("attachments") or []) for t in threads_info for p in t["posts"])
    # meta.json (兼容 telnet 格式)
    meta = {
        "slot": slot, "mode": "nf_api", "complete": True,
        "generated_bj": dt.datetime.now(TZ).isoformat(),
        "target_day": day_dir.replace("/", "-"),
        "window_bj": win_label,
        "boards": {BOARD: {
            "thread_count": len(threads_info), "post_count": post_count,
            "attachment_count": att_count,
            "threads": [{
                "title": t["title"], "gid": str(t.get("gid") or "") or None,
                "is_new_today": True,
                "first_time_bj": t["first_time"].isoformat(),
                "last_time_bj": t["posts"][-1]["time"].isoformat() if t["posts"] else None,
                "post_count": len(t["posts"]),
                "authors": list({p["author"] for p in t["posts"]}),
                "posts": [{
                    "seq": i + 1,
                    "time": p["time"].isoformat(),
                    "author": p["author"],
                    "content": p["content"],
                    "attachments": [{
                        "name": f["name"], "size": f.get("size"),
                        "fname": f["fname"], "is_img": f.get("is_img", False),
                    } for f in (p.get("attachments") or [])],
                } for i, p in enumerate(t["posts"])],
            } for t in threads_info],
        }},
    }
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False, indent=1)
    # 原帖_Stock.md
    lines = ["# 水木 Stock 版 原帖归档", "",
             f"- 生成时间 (北京): {dt.datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 时段: {slot} ({win_label})",
             f"- 主题数: {len(threads_info)} | 帖子数: {post_count} | 附件数: {att_count}", ""]
    for i, t in enumerate(sorted(threads_info, key=lambda x: x["first_time"]), 1):
        lines.append(f"## {i}. {t['title']}")
        lines.append("")
        lines.append(f"> 类型: 主题 | 首帖: {t['first_time'].strftime('%m-%d %H:%M')} | 楼层数: {len(t['posts'])}")
        lines.append("")
        for p in t["posts"]:
            lines.append(f"### [{p['time'].strftime('%m-%d %H:%M:%S')}] {p['author']}")
            lines.append("")
            lines.append(p["content"].strip())
            for f in p.get("attachments") or []:
                lines.append("")
                lines.append(f"📎 附件: {f['name']} ({f.get('size') or '?'}) -> `attachments/{f['fname']}`")
            lines.append("")
        lines.append("---")
        lines.append("")
    open(os.path.join(d, f"原帖_{BOARD}.md"), "w").write("\n".join(lines))
    log("归档 %s/%s: %d 主题 / %d 帖" % (day_dir, slot, len(threads_info), post_count))

def update_queue(tasks_done):
    try:
        q = json.load(open(QUEUE))
        done_set = set(tasks_done)
        for t in q["tasks"]:
            key = t.get("label", "")
            if key in done_set:
                t["status"] = "done"
                t["commit"] = "nf_api"
        json.dump(q, open(QUEUE, "w"), ensure_ascii=False, indent=1)
        log("队列更新: %d 窗标 done" % len(done_set))
    except Exception as e:
        log("队列更新失败: %s" % e)

def mark_empty(labels):
    """空窗复核: 无命中且已完整覆盖的窗标 done, note 记复核原因 (任务内容保留)"""
    try:
        q = json.load(open(QUEUE))
        done_set = set(labels)
        n = 0
        for t in q["tasks"]:
            if t.get("label") in done_set and t.get("status") != "done":
                t["status"] = "done"
                t["commit"] = "nf_api"
                t["note"] = "empty_window_verified"
                n += 1
        json.dump(q, open(QUEUE, "w"), ensure_ascii=False, indent=1)
        log("空窗标 done: %d" % n)
    except Exception as e:
        log("空窗标 done 失败: %s" % e)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-only", action="store_true", help="只跑列表遍(调试)")
    ap.add_argument("--dry-run", action="store_true", help="不写归档不提交, 只统计")
    ap.add_argument("--stop-time", default=None,
                    help="列表截止 'YYYY-MM-DD HH:MM:SS' (默认自动: 队列 pending 最早窗起点, 无 pending 则今天 00:00)")
    args = ap.parse_args()

    # ---- 动态截止: 队列感知, 补爬=最早 pending 窗, 日增量=当天 00:00 ----
    if args.stop_time:
        stop_str = args.stop_time
    else:
        try:
            q = json.load(open(QUEUE))
            starts = [t for t in q["tasks"] if t.get("status") == "pending"]
            if starts:
                m0 = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})", min(t.get("label", "") for t in starts))
                stop_str = "%s %s:%s:00" % (m0.group(1), m0.group(2), m0.group(3)) if m0 else None
            else:
                stop_str = None
        except Exception:
            stop_str = None
        if not stop_str:
            stop_str = dt.datetime.now(TZ).strftime("%Y-%m-%d 00:00:00")
    stop_dt = dt.datetime.strptime(stop_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)

    ck = load_auth()
    if not ck:
        log(f"凭据文件不可读: {CREDS}"); return 1
    log("Basic 认证就绪 (凭据文件读取成功)")
    nf = NF(ck)

    # ---- 列表遍 ----
    log("=== 列表遍开始 (count=%d/页, 截止 %s) ===" % (PAGE_COUNT, stop_str))
    page = 1
    all_threads = []   # (gid, flush_time)
    stop_flag = False
    first_page = True
    scan_floor = None  # 列表遍实际翻到的最深(最老) flush 时间 — 空窗复核下界 (防未扫区误标空窗)
    aborted = False
    while not stop_flag:
        d = nf.board_page(page)
        if nf.unauth:
            log("=== 终止: 登录态失效 (exit 2) ==="); return 2
        if d is None:
            log("=== 终止: 列表遍异常 (连续重试失败), 未扫区不标空窗 (exit 3) ===")
            aborted = True
            break
        # 响应是扁平结构: 顶层直接有 article[] (实测, 非 data.article)
        arts = d.get("article") or []
        if not arts:
            if first_page:
                log("=== 终止: 第 1 页就是空, 异常 (exit 2) ==="); return 2
            # 空页重试: 实测 API 偶发瞬时空页(同一页重试即恢复), 误判到底会截断扫描
            recovered = False
            for r in range(1, 6):
                log("第 %d 页空, 第 %d 次重试..." % (page, r))
                time.sleep(5 * r)
                d2 = nf.board_page(page)
                if d2 is not None and (d2.get("article") or []):
                    log("第 %d 页重试恢复: %d 串" % (page, len(d2["article"])))
                    d = d2; arts = d2["article"]; recovered = True; break
            if not recovered:
                log("第 %d 页连续 5 次空, 列表遍结束" % page); break
        first_page = False
        pg_min = None
        for a in arts:
            # 置顶/认证帖 last_reply_time 恒为 2026-06-12 且 post_time 极旧,
            # 不参与截止判定 (否则第 1 页就假停)
            if a.get("is_top"):
                continue
            gid = str(a.get("group_id") or a.get("id"))
            ft = parse_time(a.get("post_time"))
            lt = parse_time(a.get("last_reply_time")) or ft
            if ft is None:
                continue
            all_threads.append((gid, ft, lt, a.get("title")))
            if pg_min is None or lt < pg_min: pg_min = lt
        if pg_min is not None:
            log("page %d: %d 串, 最旧 flush=%s" % (page, len(arts), pg_min))
            if scan_floor is None or pg_min < scan_floor:
                scan_floor = pg_min
            if pg_min <= stop_dt:
                stop_flag = True
        page += 1
        if page > 5000: log("安全上限 5000 页, 停 (scan_floor 保护: 未扫区不误标空窗)"); break
    log("列表遍完成: %d 串, 共 %d 页, 请求 %d 次, 扫描下界 %s" %
        (len(all_threads), page - 1, nf.n, scan_floor and scan_floor.strftime("%Y-%m-%d %H:%M")))
    if aborted:
        nf.close()
        return 3

    if args.list_only: return 0

    # ---- 分桶筛选 (只拉命中 pending 窗的串全文) ----
    pending_win = load_pending_windows()

    def window_of(t):
        """首帖时间 -> (label, day_dir, slot) 命中 pending 窗则返回, 否则 None"""
        d, slot, ws = bucket_of(t)
        lab = "%s %s-%s" % (t.strftime("%Y-%m-%d"),
                       "%02d:00" % (t.hour - (t.hour % 4)),
                       "%02d:00" % (t.hour - (t.hour % 4) + 4))
        if pending_win is None:
            return lab, d, slot
        if lab not in pending_win:
            return None
        s, e = pending_win[lab]
        if not (s <= t < e):
            return None
        return lab, d, slot

    # 列表级预筛: 列表 post_time 就是首帖时间, 只有它落在 pending 窗里的串才值得拉全文
    # (日增量场景 1254 -> 个位数请求; 复核场景同理)
    if pending_win is None:
        cands = [(g, ft, t) for g, ft, lt, t in all_threads if ft >= stop_dt]
    else:
        cands = [(g, ft, t) for g, ft, lt, t in all_threads if window_of(ft) is not None]
    log("候选串 (命中 pending 窗): %d" % len(cands))

    buckets = {}  # (day_dir, slot, label) -> [thread_info]
    for i, (gid, ft, title) in enumerate(cands):
        if (i + 1) % 50 == 0:
            log("全文遍 %d/%d" % (i+1, len(cands)))
        td = nf.threads(gid)
        if td is None: continue
        posts = td.get("article") or []   # 扁平: 顶层 article[] = 全部楼层
        if not posts: continue
        # 首帖 = 第一楼 (threads 返回按楼层序)
        first = posts[0]
        ftime = parse_time(first.get("post_time"))
        if ftime is None or ftime < stop_dt: continue
        w = window_of(ftime)
        if w is None: continue
        lab, day_dir, slot = w
        key = (day_dir, slot, lab)
        buckets.setdefault(key, []).append({
            "title": first.get("title") or td.get("title") or title or "(无题)",
            "first_time": ftime,
            "gid": gid,
            "posts": posts_from_api(posts, ftime),
        })

    log("命中桶: %d 个 4h 窗" % len(buckets))
    total_t = sum(len(v) for v in buckets.values())
    log("命中主题总数: %d" % total_t)
    if pending_win is not None:
        hit = {k[2] for k in buckets}
        log("pending 覆盖: %d/%d" % (len(hit), len(pending_win)))
        missing = sorted(set(pending_win) - hit)
        for m in missing[:10]:
            log("  (无命中: %s)" % m)
        # 空窗复核: 窗内任何帖的 flush 时间 >= 窗起点 s; 列表遍已扫区 = [scan_floor, now]
        # (按 flush 新->旧翻页)。当 s >= scan_floor 时, 窗内所有帖必然在已扫区 -> 零命中才可标空窗;
        # 未翻到的老区 (s < scan_floor, 列表异常/触顶中断) 保持 pending 待下轮补爬, 绝不标空。
        # 日常场景 scan_floor 翻到 stop_dt 附近, s>=stop_dt>=scan_floor 恒成立, 行为与旧逻辑一致。
        now_dt = dt.datetime.now(TZ)
        empty_done = [lab for lab, (s, e) in pending_win.items()
                      if scan_floor and s >= scan_floor and e <= now_dt and lab not in hit]
        if empty_done:
            for lab in empty_done:
                log("空窗复核通过: %s 无首帖, 标 done" % lab)
            if not args.dry_run:
                mark_empty(empty_done)

    if not args.dry_run:
        done_labels = []
        n_att_ok = n_att_fail = 0
        for (day_dir, slot, label), tinfo in sorted(buckets.items()):
            write_archive(day_dir, slot, label, tinfo)
            n_ok, n_fail = download_bucket_attachments(nf, os.path.join(ARCHIVE, day_dir, slot), tinfo)
            n_att_ok += n_ok; n_att_fail += n_fail
            done_labels.append(label)
        update_queue(done_labels)
        # git 提交
        r = subprocess.run(["git", "add", "-A"], cwd=ARCHIVE, capture_output=True, text=True)
        r = subprocess.run(["git", "commit", "-m", "shuimu nf_api %d windows (att ok=%d fail=%d)" % (len(buckets), n_att_ok, n_att_fail)],
                           cwd=ARCHIVE, capture_output=True, text=True)
        log("git: %s" % (r.stdout.strip()[:80] or r.stderr.strip()[:80]))
    nf.close()
    log("=== 完成: 请求 %d 次 ===" % nf.n)
    return 0

if __name__ == "__main__":
    sys.exit(main())
