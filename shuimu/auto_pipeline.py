#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto_pipeline.py — 水木高速爬全自动看门狗 (cron 每 2 分钟 tick 一次, no_agent 模式)。
认证方式: HTTP Basic (nForum API 不认 cookie 会话 — 源码 basic_auth.php 实证)。
状态机 (state: .auto_state.json):
  idle      -> Basic 验 API; 200 则后台起 nf_crawler, state=running; 0102 槽满则告警+重试
  running   -> 查 pidfile; 爬虫退出则汇总(log/队列/git) -> 飞书 -> state=done
  done      -> 静默退出
同类消息 15min 冷却防刷。本脚本自包含: 成功/失败都经 deliver_feishu.py 直发 (绕开 cron live-adapter 缺陷 #47056)。
"""
import json, os, re, socket, subprocess, sys, time, datetime as dt, urllib.request

HERE = os.environ.get("SHUIMU_HOME", os.path.dirname(os.path.abspath(__file__)))
COOKIE = os.path.join(HERE, ".nf_cookie")
STATE = os.path.join(HERE, ".auto_state.json")
PIDF = os.path.join(HERE, ".auto_pid")
LOG = os.path.join(HERE, "logs", "auto_pipeline.log")
PYV = os.environ.get("SHUIMU_PYTHON", "/opt/data/venvs/scrapling/bin/python")
TZ = dt.timezone(dt.timedelta(hours=8))
ARCHIVE = os.environ.get("SHUIMU_ARCHIVE",
               os.path.join(HERE, "archive") if os.path.isdir(os.path.join(HERE, "archive")) else "/opt/data/shuimu_daily")
os.makedirs(os.path.dirname(LOG), exist_ok=True)

def now():
    return dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def log(msg):
    line = f"[{now()}] {msg}"
    # no_agent 看门狗纪律: stdout 必须恒为空 (非空=给用户的消息), 只写日志文件
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"state": "idle", "notified": {}}

def save_state(st):
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)

def feishu(text, kind=None):
    """直发飞书 (deliver_feishu.py, 绕开 cron 投递缺陷 #47056)。冷却 15min 同 kind。"""
    st = load_state()
    key = kind or st.get("_kind") or "misc"
    last = st.get("notified", {}).get(key, 0)
    if time.time() - last < 900:
        log(f"feishu 冷却中, 跳过: {text[:60]}")
        return False
    p = subprocess.run([PYV, os.path.join(HERE, "deliver_feishu.py"), "-"],
                       input=text.encode(), capture_output=True, timeout=60)
    ok = p.returncode == 0
    if ok:
        st2 = load_state(); st2.setdefault("notified", {})[key] = time.time()
        save_state(st2)
    log(f"feishu {'OK' if ok else 'FAIL'}: {text[:80]}")
    return ok

def port_open(port=9222):
    s = socket.socket(); s.settimeout(2)
    try:
        s.connect(("127.0.0.1", port)); return True
    except Exception:
        return False
    finally:
        s.close()

def cdp_read_cookie():
    """connect_over_cdp 读 newsmth cookie -> 写 .nf_cookie (600)。返回 (ok, detail)。"""
    code = '''
import sys, json
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=8000)
        ck = []
        for ctx in b.contexts:
            try:
                for c in ctx.cookies("https://www.newsmth.net"):
                    ck.append(c)
            except Exception:
                pass
        out = {k: c for c in ck for k in [c["name"]] if "newsmth.net" in c.get("domain","")}
        json.dump(out, sys.stdout)
        try: b.close()
        except Exception: pass
except Exception as e:
    print(json.dumps({"error": str(e)[:120]}))
    sys.exit(3)
'''
    p = subprocess.run([PYV, "-c", code], capture_output=True, timeout=60)
    if p.returncode != 0:
        return False, f"CDP 读取失败 rc={p.returncode}: {p.stderr.decode()[:100]}"
    try:
        ck = json.loads(p.stdout.decode())
    except Exception:
        return False, "CDP 返回无法解析"
    if isinstance(ck, dict) and ck.get("error"):
        return False, ck["error"]
    if not ck:
        return False, "CDP 连上但 newsmth 无 cookie (登录态?)"
    vals = {k: v.get("value", "") for k, v in ck.items()}
    uid = vals.get("main[UTMPUSERID]", "")
    if not uid or uid == "guest":
        return False, f"cookie 是游客态 (USERID={uid[:6] or '空'})"
    lines = [f"{k}={v.get('value','')}" for k, v in sorted(ck.items())]
    with open(COOKIE, "w") as f:
        f.write("; ".join(lines) + "\n")
    os.chmod(COOKIE, 0o600)
    return True, f"{len(lines)} 条, USERID 前2字符={uid[:2]}"

def verify_api():
    """Basic 认证验登录态 (nForum API 不认 cookie 会话, 只认 Authorization: Basic)。
    返回 (ok, detail, code); code 为业务错误码 (如 0102 登录槽满) 或 None。"""
    code = '''
import base64, json, os, urllib.request
u=p=None
for ln in open(os.environ.get("SHUIMU_CREDS", "/host-home/.config/newsmth/credentials")):
    ln=ln.strip()
    if ln.startswith("username="): u=ln.split("=",1)[1].strip()
    if ln.startswith("password="): p=ln.split("=",1)[1].strip()
if not u or not p:
    print(json.dumps({"ok": False, "detail": "凭据文件缺字段", "code": None})); raise SystemExit
tok=base64.b64encode(f"{u}:{p}".encode()).decode()
req=urllib.request.Request("https://www.newsmth.net/nForum/api/board/index/Stock.json?count=5",
    headers={"Authorization":"Basic "+tok,
             "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) Chrome/150",
             "Accept":"application/json"})
try:
    r=urllib.request.urlopen(req, timeout=30)
    d=json.loads(r.read().decode("utf-8","replace"))
    if d.get("code"):
        print(json.dumps({"ok": False, "detail": "code=%s %s" % (d["code"], d.get("msg","")[:30]),
                          "code": d["code"]}, ensure_ascii=False))
    else:
        print(json.dumps({"ok": True, "detail": "board/index 200, 首页 %d 串" % len(d.get("article", [])), "code": None}))
except urllib.error.HTTPError as e:
    print(json.dumps({"ok": False, "detail": "HTTP %d" % e.code, "code": None}))
except Exception as e:
    print(json.dumps({"ok": False, "detail": "%s" % type(e).__name__, "code": None}))
'''
    p = subprocess.run([PYV, "-c", code], capture_output=True, timeout=90)
    try:
        d = json.loads(p.stdout.decode().strip().splitlines()[-1])
        return d.get("ok"), d.get("detail", ""), d.get("code")
    except Exception:
        return False, f"验证异常: {p.stderr.decode()[:100]}", None

def launch_crawler():
    env = dict(os.environ)
    # 先记录本轮日志起点 (Popen 之前, 避免漏掉爬虫开头几行)
    off = os.path.getsize(os.path.join(HERE, "logs", "nf_crawler.log"))
    lf = open(os.path.join(HERE, "logs", "nf_crawler.log"), "a")
    proc = subprocess.Popen([PYV, os.path.join(HERE, "nf_crawler.py")],
                            stdout=lf, stderr=lf, cwd=HERE, env=env,
                            start_new_session=True)
    with open(PIDF, "w") as f:
        f.write(str(proc.pid))
    st = load_state()
    st["log_offset"] = off
    save_state(st)
    return proc.pid

def pid_alive(pid):
    try:
        os.kill(pid, 0); return True
    except Exception:
        return False

def pending_count():
    """队列 pending 窗数; 读失败返回 -1 (按有待爬处理, 宁爬勿漏)"""
    try:
        q = json.load(open(os.path.join(HERE, "backfill_queue.json")))
        return sum(1 for t in q["tasks"] if t.get("status") == "pending")
    except Exception:
        return -1

def bump_fail():
    """连续失败计数 + 3 连失败 6h 冷却 (防 401/网络故障每 2 分钟空转轰炸)"""
    st = load_state()
    n = st.get("consec_fails", 0) + 1
    st["consec_fails"] = n
    if n >= 3 and not st.get("cooldown_until"):
        st["cooldown_until"] = time.time() + 6 * 3600
        st["consec_fails"] = 0
        log("连续 3 次失败, 冷却 6h")
    save_state(st)

def cleanup_cookie():
    """清空历史残留的 .nf_cookie (Basic 认证后不再使用 cookie; 凭据文件只读, 绝不删改)"""
    try:
        open(COOKIE, "w").close()
        os.chmod(COOKIE, 0o600)
        log("cookie 副本已清空")
    except Exception as e:
        log(f"cookie 清理失败: {e}")

def publish_to_stock_research():
    """归档发布到宿主机 stock_research_mac/shuimu/帖子 + git commit + push (09-11 用户指令:
    整理完的文档全部存入该目录并推送远端)。容器直写宿主走 docker bind, push 用宿主 ssh key。"""
    try:
        # 脚本经 heredoc 送进临时容器 (docker run 无交互), 再执行发布
        script = open(os.path.join(HERE, "publish_posts.sh")).read()
        r = subprocess.run(["docker", "run", "--rm",
                            "-v", "/home/mac/.hermes/shuimu_daily:/arch",
                            "-v", "/home/mac/macperson/stock_research_mac:/s",
                            "-v", "/home/mac/.ssh:/ssh:ro",
                            "ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie",
                            "bash", "-c",
                            "cat > /tmp/publish_posts.sh <<'PUBEOF'\n" + script + "\nPUBEOF\n"
                            "bash /tmp/publish_posts.sh"],
                           capture_output=True, text=True, timeout=600)
        out = (r.stdout or "").strip().splitlines()
        last = out[-1] if out else "(no output)"
        log(f"发布 stock_research_mac: {last}")
        if r.returncode != 0:
            log(f"发布失败 rc={r.returncode}: {(r.stderr or '')[-200:]}")
    except Exception as e:
        log(f"发布 stock_research_mac 异常: {type(e).__name__}: {e}")


_ARCHIVE_WINDOW_RE = re.compile(r"归档\s+(\d{4}/\d{2}/\d{2}/w\d{2})(?=[:\s])")


def count_archived_windows(log_text):
    """Count unique archive windows in one crawler log slice.

    The crawler writes each log line to both stdout and its log file while
    the watchdog redirects stdout back to that same file.  Therefore one
    logical archive event can appear twice; count the window path, not lines.
    """
    return len({match.group(1) for match in _ARCHIVE_WINDOW_RE.finditer(log_text)})


def finish_report(rc_ok):
    """汇总爬虫结果 -> 飞书。只看本轮新增日志 (log_offset 之后)。"""
    try:
        q = json.load(open(os.path.join(HERE, "backfill_queue.json")))
        done = sum(1 for t in q["tasks"] if t.get("status") == "done")
        pend = sum(1 for t in q["tasks"] if t.get("status") == "pending")
    except Exception:
        done = pend = -1
    st = load_state()
    off = st.get("log_offset", 0)
    arch_n = 0
    try:
        f = open(os.path.join(HERE, "logs", "nf_crawler.log"))
        f.seek(off)
        new = f.read()
        arch_n = count_archived_windows(new)
    except Exception:
        pass
    git = subprocess.run(["git", "log", "--oneline", "-1"], cwd=ARCHIVE,
                         capture_output=True, text=True).stdout.strip()
    # 风控信号: 爬虫连败停手 (exit 4) 会写 .rate_limited.json — 立即点名报警 (09-12 用户指令:
    # 对服务端信号响应范式, 连败到顶停手, 报警交给看门狗冷却期处理)
    rl_why = ""
    try:
        rf = os.path.join(HERE, ".rate_limited.json")
        if os.path.exists(rf):
            rl_why = json.load(open(rf)).get("reason", "")
            os.remove(rf)
    except Exception:
        rl_why = ""
    if rc_ok:
        msg = (f"✅ 水木 Stock 高速爬完成\n"
               f"- 队列: {done} 窗完成 / {pend} 窗剩余\n"
               f"- 本次归档 {arch_n} 个 4h 窗 (telnet 旧法需 2-3 天, API 路实际分钟~小时级)\n"
               f"- git 最新: {git}\n"
               f"文档已同步到 stock_research_mac/shuimu/帖子/ 并 push 远端")
    elif rl_why:
        msg = (f"🚨 水木风控信号: 爬虫连败自动停手 ({rl_why})\n"
               f"队列 {done} 完成/{pend} 剩余, 已归档 {arch_n} 窗 (本轮部分成果已落盘, 未爬窗保持 pending)\n"
               f"已进冷却 (3 次连败后 6h 内不起新爬), 冷却结束自动恢复; 若反复触发建议暂停大活检查账号")
    else:
        tail = ""
        try:
            f = open(os.path.join(HERE, "logs", "nf_crawler.log"))
            f.seek(off)
            tail = f.read().splitlines()
            tail = " ".join(x.strip() for x in tail[-8:])[-300:]
        except Exception:
            pass
        msg = f"❌ 水木高速爬异常退出\n队列 {done} 完成/{pend} 剩余\n本轮日志尾部: {tail}"
    feishu(msg)

def main():
    st = load_state()
    state = st.get("state", "idle")

    if state == "done":
        # 队列感知: 又有 pending 窗 (每日增量入队/手动加窗) -> 自动回到 idle 重新开爬;
        # 无 pending -> 静默 (每日 00:20 入队任务会重新触发)
        q = pending_count()
        if q > 0:
            log("队列出现 %d 个 pending 窗, 状态 done->idle" % q)
            save_state({"state": "idle", "notified": st.get("notified", {})})
        return 0

    if state == "running":
        try:
            pid = int(open(PIDF).read().strip())
        except Exception:
            pid = None
        if not pid or not pid_alive(pid):
            # 爬虫已退出, 判定成败: 只看本轮新增日志 (log_offset 之后)
            ok = False
            try:
                off = st.get("log_offset", 0)
                f = open(os.path.join(HERE, "logs", "nf_crawler.log"))
                f.seek(off)
                new = f.read().splitlines()
                ok = any("=== 完成" in ln for ln in new)
            except Exception:
                pass
            finish_report(ok)
            publish_to_stock_research()   # 09-11 用户指令: 整理完的文档 → stock_research_mac + commit + push
            cleanup_cookie()
            if ok:
                # 成功: 回 idle 继续值守 (每日增量靠 done->idle 队列感知 + 00:20 入队)
                save_state({"state": "idle", "notified": st.get("notified", {})})
                log("本轮完成, 回 idle 值守")
            else:
                bump_fail()
                save_state({"state": "idle", "notified": st.get("notified", {})})
        return 0

    # ---- state == idle ----
    # 大活账号保护休息期 (backfill_tick 写入 .auto_rest.json): 不起新爬, 连 API 验证探针
    # 都不发 (每 2min 一次探针本身也是账号请求量), 静默等休息结束
    try:
        if os.path.exists(os.path.join(HERE, ".auto_rest.json")):
            until = json.load(open(os.path.join(HERE, ".auto_rest.json"))).get("until", 0)
            if time.time() < until:
                return 0
    except Exception:
        pass
    # 冷却中 (3 连失败后) 静默跳过
    if st.get("cooldown_until") and time.time() < st["cooldown_until"]:
        return 0
    # 队列无 pending 且无补爬目标 -> 静默 (每日 00:20 入队脚本会加新窗)
    if pending_count() == 0:
        return 0
    # Basic 认证直连 (nForum API 不认 cookie, Chrome/CDP 已退役)
    ok, detail, code = verify_api()
    log(f"API 验证: ok={ok} {detail}")
    if not ok:
        bump_fail()
        if code == "0102":
            feishu("⏳ 水木高速爬待命中: Basic 认证通过但 BBS 登录槽满 (0102 账号过多) — 浏览器会话占着槽。请在 Chrome 点「退出登录」释放槽位, 我每 2 分钟自动重试。", kind="api")
        else:
            feishu(f"API 验证失败 ({detail}) — 我每 2 分钟自动重试。", kind="api")
        return 0

    # 开爬
    st2 = load_state(); st2["consec_fails"] = 0
    pid = launch_crawler()
    st = load_state()
    st["state"] = "running"; st["pid"] = pid
    save_state(st)
    feishu(f"✅ 认证验证通过 ({detail}) — 高速爬已自动开跑 (pid {pid}, {pending_count()} 窗, 限速防风控)。完成后我会自动汇报。", kind="start")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        # 看门狗自己不能崩死: 报错飞书 (有冷却)
        try:
            st = load_state(); st["_kind"] = "fatal"; save_state(st)
            feishu(f"⚠️ 自动看门狗自身异常: {type(e).__name__}: {str(e)[:120]}", kind="fatal")
        except Exception:
            pass
        sys.exit(1)
