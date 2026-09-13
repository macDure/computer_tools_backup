#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cdp_login.py — 通过 CDP 接管用户 Mac 上的 Chrome, 等其登录水木 nForum, 抓取 cookie。

流程:
  1) 轮询等 CDP 端点可达 (用户需先: Cmd+Q 退 Chrome,
     open -na "Google Chrome" --args --remote-debugging-port=9222 --remote-allow-origins=*)
  2) 连接后先查现有 cookie — 若已登录(有 main[UTMPUSERID]+main[UTMPKEY])直接抓, 免滑块
  3) 未登录则新开标签页打开 nForum 登录页(用户自己屏幕上可见), 等用户输账密+拖滑块
  4) 检测到登录 cookie → 全部 newsmth.net cookie 写入 .nf_cookie (600) → exit 0

只读纪律: 只开新标签页/读 cookie; 不代用户输账密, 不代拖滑块; 不关用户浏览器。
状态: 实时写 logs/cdp_login.state (JSON, 供 agent 轮询)。
退出码: 0 成功 / 2 超时失败(状态文件含 reason)。
"""
import argparse, datetime as dt, json, os, time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "logs", "cdp_login.state")
CKF = os.path.join(HERE, ".nf_cookie")
os.makedirs(os.path.dirname(STATE), exist_ok=True)


def say(phase, **kw):
    d = {"phase": phase, "ts": dt.datetime.now(dt.timezone.utc).isoformat()}
    d.update(kw)
    json.dump(d, open(STATE, "w"), ensure_ascii=False)
    print(json.dumps(d, ensure_ascii=False), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:9222")  # host-net 容器: 宿主 Chrome 的 9222 绑在宿主 loopback = 容器 127.0.0.1
    ap.add_argument("--wait-connect", type=int, default=1800, help="等CDP可达的秒数")
    ap.add_argument("--wait-login", type=int, default=1500, help="等登录完成的秒数")
    a = ap.parse_args()

    with sync_playwright() as pw:
        # 1) 等 CDP
        t0 = time.time()
        browser = None
        while time.time() - t0 < a.wait_connect:
            try:
                browser = pw.chromium.connect_over_cdp(a.cdp, timeout=15000)
                break
            except Exception as e:
                say("waiting_cdp", last_err=str(e)[:140])
                time.sleep(10)
        if browser is None:
            say("failed_no_cdp", reason="CDP 一直连不上: 用户没带调试端口开 Chrome 或防火墙拦了")
            return 2
        say("connected", contexts=len(browser.contexts))
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()

        def cookies_now():
            return {c["name"]: c["value"] for c in ctx.cookies("https://www.newsmth.net")}

        # 2) 已登录?
        ck = cookies_now()
        if "main[UTMPUSERID]" in ck and "main[UTMPKEY]" in ck:
            say("already_logged_in", n=len(ck))
        else:
            pg = ctx.new_page()
            try:
                pg.goto("https://www.newsmth.net/nForum/", timeout=60000)
            except Exception as e:
                say("failed_page", reason=str(e)[:140])
                return 2
            say("login_page_opened", url=pg.url)

        # 3) 等登录
        t1 = time.time()
        while time.time() - t1 < a.wait_login:
            ck = cookies_now()
            if "main[UTMPUSERID]" in ck and "main[UTMPKEY]" in ck:
                break
            time.sleep(5)
        else:
            say("failed_no_login", reason="等到超时仍无登录 cookie(用户未登录或超时)")
            return 2

        # 4) 落盘
        line = "; ".join("%s=%s" % (k, v) for k, v in ck.items())
        open(CKF, "w").write(line + "\n")
        os.chmod(CKF, 0o600)
        say("cookie_saved", n=len(ck), names=sorted(ck))
        # 注意: 不 close CDP 浏览器(那可能杀掉用户的 Chrome), 进程退出即断开连接
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
