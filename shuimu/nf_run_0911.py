#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nf_run_0911.py — 09-11 09:00 一键: 等登录 → 高速爬 38 个缺口窗 → 队列汇总。

阶段:
  1) wait_login : 轮询 logs/cdp_login.state, 等 cookie_saved (或已有 .nf_cookie 内容)
  2) crawl      : 后台起 nf_crawler.py (列表遍+全文遍), 轮询日志
  3) summary    : 打印最终队列状态 + 日志尾部, 供 agent 出报告

用法: python3 nf_run_0911.py [--login-wait 2100] [--crawl-timeout 10000]
退出码: 0=爬完  2=登录超时  3=爬虫失败/超时
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "logs", "cdp_login.state")
CKF = os.path.join(HERE, ".nf_cookie")
LOGF = os.path.join(HERE, "logs", "nf_crawler.log")
CRAWL_LOG = os.path.join(HERE, "logs", "nf_crawl_0911.out")
PY = "/opt/data/venvs/scrapling/bin/python"


def cookie_ready():
    try:
        raw = open(CKF).read().strip()
        return bool(raw) and "UTMPUSERID" in raw and "UTMPKEY" in raw
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login-wait", type=int, default=2100)
    ap.add_argument("--crawl-timeout", type=int, default=10000)
    a = ap.parse_args()

    # ---- 1) 等登录 cookie ----
    if cookie_ready():
        print("PHASE=login cookie 已就绪, 跳过等待", flush=True)
    else:
        t0 = time.time()
        while time.time() - t0 < a.login_wait:
            if cookie_ready():
                break
            try:
                st = json.load(open(STATE))
                print("LOGIN_WAIT phase=%s %s" % (st.get("phase"),
                      st.get("last_err") or st.get("reason") or ""), flush=True)
            except Exception:
                print("LOGIN_WAIT (state 未写)", flush=True)
            time.sleep(15)
    if not cookie_ready():
        print("PHASE=login FAILED 登录超时/未完成", flush=True)
        return 2
    print("PHASE=login OK (%d bytes cookie)" % os.path.getsize(CKF), flush=True)

    # ---- 2) 爬虫 ----
    if os.path.exists(CRAWL_LOG):
        os.remove(CRAWL_LOG)
    p = subprocess.Popen([PY, os.path.join(HERE, "nf_crawler.py")],
                         stdout=open(CRAWL_LOG, "a"), stderr=subprocess.STDOUT,
                         cwd=HERE)
    t0 = time.time()
    last_line = -1
    while p.poll() is None:
        if time.time() - t0 > a.crawl_timeout:
            print("PHASE=crawl TIMEOUT, kill", flush=True)
            p.kill()
            break
        time.sleep(60)
        # 心跳: 打印日志新增行数
        try:
            n = sum(1 for _ in open(LOGF))
            if n != last_line:
                tail = open(LOGF).readlines()[-1].strip()
                print("CRAWL_TICK +lines tail=%s" % tail[:160], flush=True)
                last_line = n
        except Exception:
            pass
    rc = p.returncode
    print("PHASE=crawl exit=%s" % rc, flush=True)
    if rc not in (0,):
        # 打印尾部便于诊断
        try:
            print("TAIL:\n" + "".join(open(LOGF).readlines()[-15:]), flush=True)
        except Exception:
            pass
        return 3

    # ---- 3) 汇总 ----
    q = json.load(open(os.path.join(HERE, "backfill_queue.json")))
    c = {}
    for t in q["tasks"]:
        c[t.get("status", "pending")] = c.get(t.get("status", "pending"), 0) + 1
    print("SUMMARY queue=%s" % json.dumps(c), flush=True)
    print("SUMMARY log_tail:", flush=True)
    print("".join(open(LOGF).readlines()[-12:]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
