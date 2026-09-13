#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""login_nforum.py — 用 Scrapling 真实浏览器环境 POST 登录 nForum (服务端不校验 captcha)。
尝试多个候选端点, 成功则落 5 条 cookie 到 .nf_cookie 并验证 API。密码不进 stdout。"""
import re, os, sys, json, time
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/data/.playwright-browsers")
from scrapling.fetchers import DynamicSession
EXE = "/opt/data/.playwright-browsers/chromium-1234/chrome-linux64/chrome"
COOKIE_FILE = "/opt/data/scripts/shuimu_daily/.nf_cookie"
cred = {}
for ln in open('/host-home/.config/newsmth/credentials'):
    if '=' in ln:
        k, v = ln.split('=', 1)
        cred[k.strip()] = v.strip()

LOGIN_COOKIES = ["UTMPUSERID", "UTMPKEY", "UTMPNUM", "LOGINTIME", "PASSWORD"]
endpoints = [
    "/nForum/login",
    "/login",
    "/nForum/user/login",
    "/user/login",
    "/nForum/#!login",
]

d = DynamicSession(headless=True, executable_path=EXE,
                   viewport={"width": 1280, "height": 900})
with d:
    # 建立会话 (真实浏览器指纹)
    d.fetch("https://www.newsmth.net/nForum/#!login", network_idle=True, timeout=60000)
    ctx = d.context  # BrowserContext, 有 .request (APIRequestContext)
    req = ctx.request
    data = {
        "id": cred["username"], "passwd": cred["password"], "CookieDate": "2",
        "ticket": "", "randstr": "", "lot_number": "",
        "captcha_output": "", "pass_token": "", "gen_time": "", "captcha_id": "",
    }
    winner = None
    for ep in endpoints:
        try:
            r = req.post("https://www.newsmth.net" + ep, form=data,
                         headers={"Referer": "https://www.newsmth.net/nForum/#!login"},
                         timeout=30000)
            # 取 cookie
            try:
                cks = ctx.cookies()
            except Exception:
                cks = []
            names = [c.get("name", "").replace("main[", "") for c in cks]
            got = [c for c in names if any(LC in c for LC in LOGIN_COOKIES)]
            print("POST %s -> status=%s set-cookie命中=%s 全部=%s" %
                  (ep, r.status, got, names[:8]))
            if len(got) >= 3 or (r.status == 200 and len(names) >= 4):
                winner = ep
                break
        except Exception as e:
            print("POST %s ERR: %s" % (ep, str(e)[:100]))
    if not winner:
        print("NO_LOGIN (所有端点都没拿到登录态)"); sys.exit(1)
    # 验证 API
    v = req.get("https://www.newsmth.net/nForum/api/board/index/Stock.json?count=5&page=1",
                headers={"Referer": "https://www.newsmth.net/nForum/board/Stock"}, timeout=30000)
    print("验证 API /board/index/Stock.json -> status=%s size=%s" % (v.status, len(v.body or b"")))
    # 落 cookie
    cks = ctx.cookies()
    pairs = {c["name"]: c["value"] for c in cks}
    with open(COOKIE_FILE, "w") as f:
        f.write("; ".join("%s=%s" % (k, v) for k, v in pairs.items()))
    os.chmod(COOKIE_FILE, 0o600)
    print("OK 登录成功, %d 条 cookie 落盘. 字段: %s" % (len(pairs), list(pairs.keys())))
    # 打印 API 样例 (只结构, 不敏感)
    try:
        d2 = json.loads((v.body or b"").decode("utf-8", "replace"))
        arts = (d2.get("data") or {}).get("article") or []
        print("API 返回 %d 帖, 首帖结构: %s" % (len(arts), json.dumps(arts[0], ensure_ascii=False)[:200] if arts else "无"))
    except Exception as e:
        print("API 解析:", str(e)[:80])
