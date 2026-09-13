#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""login_one.py — 只试一个端点 /nForum/login (真实浏览器环境), 单次尝试防风控。
成功落 5 条 cookie 并验证 API; 失败只报 status, 不重试。密码不进 stdout。"""
import os, sys, json, re
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
d = DynamicSession(headless=True, executable_path=EXE,
                   viewport={"width": 1280, "height": 900})
with d:
    d.fetch("https://www.newsmth.net/nForum/#!login", network_idle=True, timeout=60000)
    req = d.context.request
    data = {
        "id": cred["username"], "passwd": cred["password"], "CookieDate": "2",
        "ticket": "", "randstr": "", "lot_number": "",
        "captcha_output": "", "pass_token": "", "gen_time": "", "captcha_id": "",
    }
    r = req.post("https://www.newsmth.net/nForum/login", form=data,
                 headers={"Referer": "https://www.newsmth.net/nForum/#!login",
                          "Origin": "https://www.newsmth.net"},
                 timeout=30000)
    cks = d.context.cookies()
    names = [c.get("name", "") for c in cks]
    got = [n for n in names if any(LC in n for LC in LOGIN_COOKIES)]
    raw = r.body() if callable(getattr(r, "body", None)) else (r.body or b"")
    if raw is None: raw = b""
    if not isinstance(raw, bytes): raw = str(raw).encode()
    body = raw.decode("utf-8", "replace")
    print("POST /nForum/login -> status=%s" % r.status)
    print("cookie 命中: %s" % got)
    print("全部 cookie: %s" % names[:10])
    # 响应里的提示
    for kw in ["验证码", "LOGIN_OK", "成功", "waitDirect", "不存在", "error"]:
        i = body.find(kw)
        if i >= 0:
            print("body[%s]:" % kw, body[max(0, i-40):i+80].replace("\n", " "))
            break
    if len(got) >= 3:
        # 验证 API
        v = req.get("https://www.newsmth.net/nForum/api/board/index/Stock.json?count=5&page=1",
                    headers={"Referer": "https://www.newsmth.net/nForum/board/Stock"}, timeout=30000)
        vraw = v.body() if callable(getattr(v, "body", None)) else (v.body or b"")
        print("API 验证 -> status=%s size=%s" % (v.status, len(vraw or b"")))
        pairs = {c["name"]: c["value"] for c in cks}
        with open(COOKIE_FILE, "w") as f:
            f.write("; ".join("%s=%s" % (k, v) for k, v in pairs.items()))
        os.chmod(COOKIE_FILE, 0o600)
        print("LOGIN_SUCCESS 落盘 %d 条 cookie" % len(pairs))
    else:
        print("LOGIN_FAILED (仅 %d 条命中, 需人工登录)" % len(got))
