#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_login.py — Scrapling 浏览器引擎: 渲染 nForum 登录页 -> 填表登录 -> 抓 cookie。
只读探针: 最多输一次真实密码尝试登录; 失败不重试(防风控)。"""
import re, os, sys, json, time
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/data/.playwright-browsers")
from scrapling.fetchers import DynamicSession

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
cred = {}
for ln in open('/host-home/.config/newsmth/credentials'):
    if '=' in ln:
        k, v = ln.split('=', 1)
        cred[k.strip()] = v.strip()

def txt(p):
    b = p.body
    return b.decode('utf-8', 'replace') if isinstance(b, bytes) else (b or '')

with DynamicSession(headless=True, viewport={"width": 1280, "height": 900}) as d:
    # 1) 渲染登录页
    lp = d.fetch("https://www.newsmth.net/nForum/#!login", timeout=45000)
    html = txt(lp)
    print("登录页 status:", lp.status, "len:", len(html))
    open('/opt/data/tmp/nf_login_rendered.html', 'w').write(html)
    forms = re.findall(r'<form[^>]*action="([^"]*)"', html)
    inputs = re.findall(r'<input[^>]*name="([^"]+)"', html)
    print("form actions:", forms[:5])
    print("input names:", inputs[:15])
    # 有没有 geetest/腾讯 captcha 元素
    print("geetest 痕迹:", bool(re.search(r'geetest|gt4|gt-captcha|initGeetest', html, re.I)))
    print("tencent captcha 痕迹:", bool(re.search(r'captcha\.qq|tcaptcha|TencentCaptcha', html, re.I)))

    # 2) 找登录表单并填写 (用 JS 直接驱动, 比 element 定位稳)
    try:
        # DynamicSession 暴露 page? 查接口
        page = getattr(d, 'page', None) or getattr(d, '_page', None) or getattr(d, 'controller', None)
        print("session 内部句柄类型:", type(page).__name__ if page else None)
    except Exception as e:
        print("句柄探测:", e)

    # 3) 直接尝试 POST 登录 (真实浏览器上下文 = 真实 TLS/JS 环境, cookie 自动留存)
    import urllib.parse
    data = urllib.parse.urlencode({"id": cred["username"], "passwd": cred["password"],
                                   "CookieDate": "2", "ticket": "", "randstr": "",
                                   "lot_number": "", "captcha_output": "",
                                   "pass_token": "", "gen_time": "", "captcha_id": ""})
    try:
        r = d.fetch.__self__ if False else None
    except Exception:
        pass
print("probe done")
