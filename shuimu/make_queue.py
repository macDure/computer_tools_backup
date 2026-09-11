#!/usr/bin/env python3
"""make_queue.py — 造区间回补队列 (backfill_queue.json)

用法:
  python make_queue.py --start 2026-08-31 --end 2026-09-11 [14:00]
    --start/--end: 北京时间日期 (end 可带 HH:MM, 缺省 24:00)
    生成 [start 00:00, end) 之间每个**已结束**的 2h 窗, status=pending
  --force 覆盖已存在的 backfill_queue.json (缺省: 追加, 已存在的 label 跳过)
  --dry-run 只打印不写

队列结构与主爬虫 nf_crawler.py / 看门狗 auto_pipeline.py 约定一致:
  {"tasks": [{"label": "YYYY-MM-DD HH:00-HH:00",
              "start": "YYYY-MM-DD HH:MM:SS", "end": "YYYY-MM-DD HH:MM:SS",
              "status": "pending"}, ...]}
"""
import argparse, json, os, datetime as dt

TZ = dt.timezone(dt.timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, "backfill_queue.json")

def parse_end(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    d = dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=TZ)
    return d + dt.timedelta(days=1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="北京时间 'YYYY-MM-DD'")
    ap.add_argument("--end", required=True, help="'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--force", action="store_true", help="覆盖已有队列")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    start = dt.datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=TZ)
    end = parse_end(args.end)
    if end <= start:
        print("end 必须晚于 start"); return 1

    # 现在时刻 (北京): 只入队**已结束**的窗, 未结束的窗等它结束再入 (看门狗/增量脚本同理)
    now = dt.datetime.now(TZ)

    tasks = []
    if not args.force and os.path.exists(QUEUE):
        try:
            tasks = json.load(open(QUEUE)).get("tasks", [])
        except Exception:
            tasks = []
    seen = {t["label"] for t in tasks}

    cur = start.replace(minute=0, second=0, microsecond=0)
    added = skipped_future = 0
    while cur + dt.timedelta(hours=2) <= end:
        we = cur + dt.timedelta(hours=2)
        label = "%s %02d:00-%02d:00" % (cur.strftime("%Y-%m-%d"), cur.hour, we.hour)
        if label in seen:
            cur = we; continue
        if we > now:
            skipped_future += 1
            cur = we; continue
        tasks.append({"label": label,
                      "start": cur.strftime("%Y-%m-%d %H:%M:%S"),
                      "end": we.strftime("%Y-%m-%d %H:%M:%S"),
                      "status": "pending"})
        seen.add(label)
        added += 1
        cur = we

    print("新增 %d 窗, 跳过未结束 %d 窗, 队列总 %d 窗 -> %s" % (added, skipped_future, len(tasks), QUEUE))
    if args.dry_run:
        for t in tasks[-5:]: print("  ", t["label"])
        return 0
    with open(QUEUE, "w") as f:
        json.dump({"tasks": tasks}, f, indent=1)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
