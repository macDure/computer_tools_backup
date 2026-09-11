#!/usr/bin/env python3
# make_backfill_range.py — 生成日期区间的全窗回补队列 (2026-01-01~08-31 / 2025 全年)
# 用法: make_backfill_range.py --start 2026-01-01 --end 2026-08-31 [--dry-run]
# 幂等: 队列已有同 label 或归档已有 nf_api 的窗跳过。不碰现有 pending。
import json, os, sys, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, "backfill_queue.json")
ARCHIVE = os.environ.get("SHUIMU_ARCHIVE", "/opt/data/shuimu_daily")
TZ = dt.timezone(dt.timedelta(hours=8))
SLOTS = ["w00", "w04", "w08", "w12", "w16", "w20"]

def archive_has(day_dir, slot):
    p = os.path.join(ARCHIVE, day_dir, slot, "meta.json")
    if not os.path.exists(p):
        return False
    try:
        return json.load(open(p)).get("mode") == "nf_api"
    except Exception:
        return False

def main():
    start = end = None
    dry = False
    ap = sys.argv[1:]; i = 0
    while i < len(ap):
        if ap[i] == "--start": start = dt.date.fromisoformat(ap[i+1]); i += 2
        elif ap[i] == "--end": end = dt.date.fromisoformat(ap[i+1]); i += 2
        elif ap[i] == "--dry-run": dry = True; i += 1
        else: i += 1
    if not start or not end or start > end:
        print("用法: --start YYYY-MM-DD --end YYYY-MM-DD [--dry-run]"); return 1

    q = json.load(open(QUEUE))
    existing = {t.get("label") for t in q["tasks"]}
    seq_max = max((t.get("seq", 0) for t in q["tasks"]), default=0)
    added, skip_exist, skip_arch, total = 0, 0, 0, 0
    d = start
    while d <= end:
        day_dir = "%04d/%02d/%02d" % (d.year, d.month, d.day)
        for i, slot in enumerate(SLOTS):
            total += 1
            label = "%s %02d:00-%02d:00" % (d.isoformat(), i*4, i*4+4)
            if label in existing:
                skip_exist += 1; continue
            if archive_has(day_dir, slot):
                skip_arch += 1; continue
            seq_max += 1
            base = dt.datetime(d.year, d.month, d.day, 0, 0, tzinfo=TZ)
            q["tasks"].append({"day": d.isoformat(),
                               "win_start": (base + dt.timedelta(hours=i*4)).isoformat(),
                               "win_end": (base + dt.timedelta(hours=i*4+4)).isoformat(),
                               "slot": slot, "label": label, "seq": seq_max,
                               "status": "pending", "attempt": 0, "note": "range_backfill"})
            added += 1
        d += dt.timedelta(days=1)
    if not dry:
        json.dump(q, open(QUEUE, "w"), ensure_ascii=False, indent=1)
    print("区间 %s ~ %s: 总窗 %d, 新增入队 %d, 队列已有 %d, 归档已有 %d%s" %
          (start, end, total, added, skip_exist, skip_arch, " (dry-run)" if dry else ""))
    return 0

if __name__ == "__main__":
    sys.exit(main())
