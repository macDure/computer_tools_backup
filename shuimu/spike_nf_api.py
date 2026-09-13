#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nForum 高速 API 爬虫 spike: 用用户提供的 Cookie 验证 Stock 版三个接口。
用法: 把 Cookie 整行(或 name=value; 串)存到 /opt/data/scripts/shuimu_daily/.nf_cookie (权限600),
      然后: /opt/data/venvs/scrapling/bin/python spike_nf_api.py
只读: board/index, article/index, threads — 不碰任何写接口。
"""
import json, os, re, sys
from scrapling.fetchers import FetcherSession

COOKIE_FILE = "/opt/data/scripts/shuimu_daily/.nf_cookie"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
BASE = "https://www.newsmth.net/nForum/api"

def load_cookie():
    raw = open(COOKIE_FILE).read().strip()
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()
    return raw

def main():
    ck = load_cookie()
    if not ck:
        print("COOKIE_EMPTY"); return 1
    names = [p.split("=", 1)[0].strip() for p in ck.split(";") if "=" in p]
    print("cookie 字段:", names)
    need = ["UTMPUSERID", "UTMPKEY"]
    missing = [n for n in need if not any(n in x for x in names)]
    if missing:
        print("MISSING:", missing, "(登录态不完整, 检查是否复制全)"); return 2

    with FetcherSession(impersonate="chrome") as s:
        hdrs = {"User-Agent": UA, "Cookie": ck,
                "Referer": "https://www.newsmth.net/nForum/board/Stock"}
        # 1) 版面列表
        r = s.get(f"{BASE}/board/index/Stock.json?count=10&page=1", headers=hdrs, timeout=25)
        print("\n=== board/index/Stock.json ===", r.status, "size:", len(r.body or b""))
        try:
            d = json.loads((r.body or b"").decode("utf-8", "replace"))
            arts = d.get("data", {}).get("article", [])
            print("帖数(本页):", len(arts))
            first_aid = None
            for a in arts[:5]:
                print("  ", json.dumps(a, ensure_ascii=False)[:220])
                if first_aid is None:
                    first_aid = a.get("id") or a.get("gid")
            meta = json.dump(d, open("/opt/data/scripts/shuimu_daily/spike_board_sample.json", "w"), ensure_ascii=False, indent=1)
        except Exception as e:
            print("解析失败:", e, str((r.body or b""))[:200])
            return 3
        # 2) 单帖全文
        if first_aid:
            r2 = s.get(f"{BASE}/article/index/Stock/{first_aid}.json", headers=hdrs, timeout=25)
            print("\n=== article/index ===", r2.status, "size:", len(r2.body or b""))
            print(str(r2.body)[:300])
            json.dump(json.loads((r2.body or b"").decode("utf-8", "replace")),
                      open("/opt/data/scripts/shuimu_daily/spike_article_sample.json", "w"), ensure_ascii=False, indent=1)
        # 3) 整串回复
        r3 = s.get(f"{BASE}/threads/Stock/{first_aid}.json?count=10&page=1", headers=hdrs, timeout=25)
        print("\n=== threads ===", r3.status, "size:", len(r3.body or b""))
        print(str(r3.body)[:300])
    print("\nSpike 完成: 样例存 spike_board_sample.json / spike_article_sample.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())
