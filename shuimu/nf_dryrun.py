#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nf_dryrun.py — 离线全流程演练: mock 网络层, 验证 nf_crawler 列表遍/分桶/归档/队列/git。
不触网, 归档写 /tmp, 队列用副本。"""
import importlib.util, json, os, shutil, sys, datetime as dt

HERE = "/opt/data/scripts/shuimu_daily"
spec = importlib.util.spec_from_file_location("nfc", os.path.join(HERE, "nf_crawler.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# --- 沙盒: 归档/队列改指 /tmp ---
SANDBOX = "/tmp/nf_dryrun"
shutil.rmtree(SANDBOX, ignore_errors=True)
os.makedirs(SANDBOX, exist_ok=True)
m.ARCHIVE = os.path.join(SANDBOX, "archive")
m.QUEUE = os.path.join(SANDBOX, "queue.json")
shutil.copy(os.path.join(HERE, "backfill_queue.json"), m.QUEUE)
os.makedirs(os.path.join(SANDBOX, "logs"), exist_ok=True)
m.LOGF = os.path.join(SANDBOX, "logs", "dry.log")
m._logf.close()
m._logf = open(m.LOGF, "a", encoding="utf-8")

# --- mock 数据: 构造若干串, 覆盖不同 4h 窗 ---
TZ = dt.timezone(dt.timedelta(hours=8))
def T(s): return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)

# (gid, first_post_time, last_reply_time, title) — 注意: 列表 post_time=首帖, last_reply_time=末帖
THREADS = [
    ("1001", "2026-09-09 08:23:45", "2026-09-10 20:00:00", "美国AI泡沫要破裂了吗"),
    ("1002", "2026-09-09 09:10:00", "2026-09-09 10:00:00", "电车时代整车厂只会造壳子"),
    ("1003", "2026-09-08 22:00:00", "2026-09-09 08:00:00", "恒瑞医药跌不动了"),
    ("1004", "2026-09-11 00:15:00", "2026-09-11 01:00:00", "贝森特又发推了"),
    ("1005", "2026-08-31 01:00:00", "2026-09-09 07:59:00", "道琼斯8月缩量新高"),
    ("1006", "2026-09-09 21:30:00", "2026-09-10 12:00:00", "DeepSeek要登录科创板"),
]
PAGES = {}
for p in range(1, 3):
    rows = []
    for g, ft, lt, ti in THREADS:
        rows.append({"id": g, "group_id": g, "title": ti,
                     "post_time": ft, "last_reply_time": lt,
                     "user": {"name": "mockuser"}, "reply_count": 3})
    PAGES[p] = rows  # 两页放同样数据(去重靠 gid), 第2页验证翻页+结束
# 第2页返回空以触发正常结束
PAGES[2] = []

def fake_get_json(self, path):
    self.n += 1
    if "/board/index/" in path:
        page = int(path.split("page=")[1].split("&")[0].split()[0])
        if PAGES.get(page):
            return {"data": {"article": PAGES[page]}}
        return {"data": {"article": []}}
    if "/threads/" in path:
        gid = path.split("/threads/Stock/")[1].split(".json")[0]
        ft = dict((g, ft) for g, ft, lt, ti in THREADS)
        # 构造楼层: 首帖(首帖时间) + 2 楼
        t0 = T(ft[gid])
        return {"data": {"title": dict((g, ti) for g, ft2, lt2, ti in THREADS)[gid],
                         "article": [
            {"id": str(int(gid)*10+1), "post_time": t0.strftime("%Y-%m-%d %H:%M:%S"),
             "user": {"name": "opener"}, "content": "mock 首帖内容 " + gid},
            {"id": str(int(gid)*10+2), "post_time": (t0+dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
             "user": {"name": "replier"}, "content": "mock 回复 " + gid},
        ]}}
    return None

m.NF.get_json = fake_get_json
m.NF._gap = lambda self: None  # 不 sleep
m.NF.close = lambda self: None
class FakeSess:
    def close(self): pass
m.FakeSess = FakeSess
def fake_init(self, cookie):
    self.s = FakeSess(); self.h = {}; self.n = 0; self.unauth = False
m.NF.__init__ = fake_init

rc = m.main()
print("\n=== DRY-RUN 结果 ===")
print("exit:", rc)
# 验证归档
import glob
d = m.ARCHIVE
dirs = []
for root, _, files in os.walk(d):
    if "meta.json" in files:
        meta = json.load(open(os.path.join(root, "meta.json")))
        b = meta["boards"]["Stock"]
        dirs.append((os.path.relpath(root, d), b["thread_count"], b["post_count"],
                     [t["title"][:20] for t in b["threads"]]))
for r in sorted(dirs): print(" 归档:", r)
# 验证队列
q = json.load(open(m.QUEUE))
done = [t["label"] for t in q["tasks"] if t["status"] == "done" and t.get("commit") == "nf_api"]
print("队列标 done (nf_api):", len(done))
for x in sorted(done): print("   ", x)
print("dry.log 关键行:")
for line in open(m.LOGF):
    if any(k in line for k in ("列表遍完成", "候选串", "命中桶", "命中主题", "pending 覆盖", "归档", "队列更新", "终止", "401")):
        print("  ", line.rstrip())
