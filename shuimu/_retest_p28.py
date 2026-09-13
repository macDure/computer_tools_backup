#!/usr/bin/env python3
# 复测: page 28 现在是否为空 (判断是否风控/瞬态)
import sys, datetime as dt
sys.path.insert(0, "/opt/data/scripts/shuimu_daily")
import nf_crawler as C

ck = C.load_auth()
nf = C.NF(ck)
for pg in (27, 28, 29, 30):
    d = nf.board_page(pg)
    if d is None:
        print("page %d: None (请求失败)" % pg); continue
    arts = d.get("article") or []
    if not arts:
        print("page %d: 空 (article=[])" % pg)
    else:
        lts = [C.parse_time(a.get("last_reply_time")) for a in arts if not a.get("is_top")]
        lts = [x for x in lts if x]
        print("page %d: %d 串, 最老 flush=%s" % (pg, len(arts), min(lts) if lts else "?"))
print("总请求:", nf.n, "unauth:", nf.unauth)
nf.close()
