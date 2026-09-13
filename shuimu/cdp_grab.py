#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cdp_grab.py — CDP 完整闭环抓 water cookie:
  1) 连 CDP
  2) 读 newsmth cookie → 容器 urllib 调 ajax_session.json 判真假登录
     (服务端认 guest = 坏会话残骸, 必须重新登录; 不信任页面"欢迎xxx"字样)
  3) 未真登录 → CDP 开登录页标签, 轮询等用户输账密+滑块, 直到 ajax_session 非 guest
  4) 真登录 → 全量写 .nf_cookie(600) → 容器 urllib 验证 board/index/Stock.json 能读
  只读纪律: 不关用户浏览器; 仅自己开的验证 tab 会关。
退出码: 0 成功 / 2 CDP不可达 / 3 等待登录超时
"""
import argparse, datetime as dt, json, os, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
CKF = os.path.join(HERE, ".nf_cookie")
STATE = os.path.join(HERE, "logs", "cdp_grab.state")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
SESSION_URL = "https://www.newsmth.net/nForum/user/ajax_session.json"
BOARD_URL = "https://www.newsmth.net/nForum/api/board/index/Stock.json?mode=2&count=3"
os.makedirs(os.path.dirname(STATE), exist_ok=True)

def say(phase, **kw):
    d = {"phase": phase, "ts": dt.datetime.now(dt.timezone.utc).isoformat()}
    d.update(kw)
    json.dump(d, open(STATE, "w"), ensure_ascii=False)
    print("[%s] %s %s" % (dt.datetime.now().strftime("%H:%M:%S"), phase,
                          json.dumps(kw, ensure_ascii=False)[:160]), flush=True)

def cookie_str(cks):
    return "; ".join("%s=%s" % (c["name"], c["value"]) for c in cks)

def sess_state(ck):
    """容器 urllib 调 ajax_session, 返回 (is_guest, id, user_name)。"""
    req = urllib.request.Request(SESSION_URL, headers={
        "Cookie": ck, "User-Agent": UA,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.newsmth.net/nForum/"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
        uid = d.get("id"); un = d.get("user_name")
        return (uid == "guest", uid, un)
    except urllib.error.HTTPError as e:
        return (True, "http%d" % e.code, None)
    except Exception as e:
        return (True, "err:%s" % str(e)[:40], None)

def verify_board(ck):
    req = urllib.request.Request(BOARD_URL, headers={
        "Cookie": ck, "User-Agent": UA,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.newsmth.net/nForum/board/Stock"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
        if isinstance(d, dict) and d.get("error") in (800, None):
            arts = (d.get("data") or {}).get("article") or (d.get("data") or {}).get("posts") or []
            if d.get("error") == 800:
                return False, "error:800(需认证)"
            return True, "ok, %d articles" % len(arts)
        return (d.get("error") not in (800,), "code=%s" % d.get("error"))
    except urllib.error.HTTPError as e:
        return False, "HTTP %d" % e.code
    except Exception as e:
        return False, "err:%s" % str(e)[:40]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:9222")
    ap.add_argument("--wait-login", type=int, default=900)
    a = ap.parse_args()

    with sync_playwright() as pw:
        try:
            b = pw.chromium.connect_over_cdp(a.cdp, timeout=15000)
        except Exception as e:
            say("failed_no_cdp", reason=str(e)[:120]); return 2
        say("connected", contexts=len(b.contexts))
        ctx = b.contexts[0] if b.contexts else b.new_context()

        def utmp_present(cks):
            return all(any(c["name"] == n for c in cks) for n in
                       ("main[UTMPUSERID]", "main[UTMPKEY]"))

        # 2) 现有登录真假
        cks = [c for c in ctx.cookies() if "smth" in c["domain"]]
        guest, uid, un = (True, "no_cookie", None)
        if utmp_present(cks):
            guest, uid, un = sess_state(cookie_str(cks))
        say("state_check", guest=guest, id=uid, user=un, n_ck=len(cks))

        # 3) 未真登录 → 开登录页等
        if guest:
            pg = ctx.new_page()
            try:
                pg.goto("https://www.newsmth.net/nForum/#!login",
                        wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                say("failed_page", reason=str(e)[:120]); return 3
            say("login_page_opened", url=pg.url,
                hint="在刚开的标签页输账密+拖滑块; 若提示'账号过多'需先在别的设备退出旧会话")
            t0 = time.time()
            while time.time() - t0 < a.wait_login:
                cks = [c for c in ctx.cookies() if "smth" in c["domain"]]
                if utmp_present(cks):
                    guest, uid, un = sess_state(cookie_str(cks))
                    if not guest:
                        break
                time.sleep(8)
            else:
                say("failed_no_login", reason="等待超时, ajax_session 仍 guest"); return 3
            try: pg.close()
            except: pass
            say("login_detected", id=uid, user=un)

        # 4) 落盘 + 验证
        cks = [c for c in ctx.cookies() if "smth" in c["domain"]]
        line = cookie_str(cks)
        open(CKF, "w").write(line + "\n"); os.chmod(CKF, 0o600)
        say("cookie_saved", n=len(cks))
        ok, info = verify_board(line)
        say("board_verify", ok=ok, info=info)
        return 0 if ok else 4  # 4=cookie落盘但API仍不通(登录态可疑)

if __name__ == "__main__":
    raise SystemExit(main())
