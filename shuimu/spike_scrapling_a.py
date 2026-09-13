#!/usr/bin/env python3
"""Scrapling 通道A spike: Fetcher(TLS伪装) 打 WAP API
测试: 1) 匿名 board list 不同 id 格式 2) search board 3) impersonate 对比
不登录, 纯匿名探测。
"""
import json, sys
from scrapling.fetchers import Fetcher, FetcherSession

BASE = "https://wap.newsmth.net"
UA_M = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"

def show(tag, resp, body_limit=250):
    try:
        j = resp.json()
        body = json.dumps(j, ensure_ascii=False)[:body_limit]
    except Exception:
        body = (resp.body or b'').decode('utf-8', 'replace')[:body_limit]
    print(f"--- {tag}: http={resp.status} ---")
    print(body)
    print()

# 1) board/topic/list 各种 id 格式 (匿名, 手机UA)
tests = [
    (f"{BASE}/wap/api/board/topic/list?id=Stock&isOrderByFlushTime=0&page=1", "id=Stock"),
    (f"{BASE}/wap/api/board/topic/list?id=stock&isOrderByFlushTime=0&page=1", "id=stock"),
    (f"{BASE}/wap/api/search/board?keyword=Stock", "search/board Stock"),
    (f"{BASE}/wap/api/search/board?keyword=%E8%82%A1", "search/board 股"),
    (f"{BASE}/wap/api/board/manager/list/Stock", "manager/list Stock"),
]
for url, tag in tests:
    try:
        r = Fetcher.get(url, impersonate="chrome",
                        headers={"User-Agent": UA_M, "Referer": "https://wap.newsmth.net/"},
                        timeout=20)
        show(tag, r)
    except Exception as e:
        print(f"--- {tag}: ERR {type(e).__name__} {str(e)[:150]} ---\n")
