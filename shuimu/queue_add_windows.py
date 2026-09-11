#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""queue_add_windows.py — 水木 Stock 每日增量入队 (幂等)。

默认把"昨天"(北京时间) 的 6 个 4h 窗加入 backfill_queue.json (已存在的 label 跳过)。
--days-back N: 补最近 N 天 (含昨天)。--date YYYY-MM-DD: 指定某一天。
跳过规则 (双保险, 幂等):
  1) 队列里已有同 label 且 status=done
  2) 归档仓已有该窗 nf_api 模式 meta.json
cron 00:20 北京 (=16:20 UTC) no_agent 跑; stdout 恒空 (诊断只落日志)。
"""
import json, os, sys, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, "backfill_queue.json")
ARCHIVE = os.environ.get("SHUIMU_ARCHIVE",
             os.path.join(HERE, "archive") if os.path.isdir(os.path.join(HERE, "archive")) else "/opt/data/shuimu_daily")
LOGF = os.path.join(HERE, "logs", "queue_add.log")
TZ = dt.timezone(dt.timedelta(hours=8))
SLOTS = ["w00", "w04", "w08", "w12", "w16", "w20"]

def log(msg):
    line = "[%s] %s" % (dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"), msg)
    os.makedirs(os.path.dirname(LOGF), exist_ok=True)
    with open(LOGF, "a") as f:
        f.write(line + "\n")

def archive_has_nf_api(day_dir, slot):
    p = os.path.join(ARCHIVE, day_dir, slot, "meta.json")
    if not os.path.exists(p):
        return False
    try:
        return json.load(open(p)).get("mode") == "nf_api"
    except Exception:
        return False

def windows_for(day: dt.date):
    out = []
    for i, slot in enumerate(SLOTS):
        s = dt.datetime(day.year, day.month, day.day, i * 4, tzinfo=TZ)
        e = s + dt.timedelta(hours=4)
        out.append({
            "day": day.isoformat(),
            "win_start": s.isoformat(),
            "win_end": e.isoformat(),
            "slot": slot,
            "label": "%s %02d:00-%02d:00" % (day.isoformat(), i * 4, i * 4 + 4),
        })
    return out

def main():
    ap = sys.argv[1:]
    days_back, dates = 1, []
    i = 0
    while i < len(ap):
        if ap[i] == "--days-back":
            days_back = int(ap[i + 1]); i += 2
        elif ap[i] == "--date":
            dates.append(dt.date.fromisoformat(ap[i + 1])); i += 2
        else:
            i += 1
    if not dates:
        today = dt.datetime.now(TZ).date()
        for k in range(1, days_back + 1):
            dates.append(today - dt.timedelta(days=k))

    q = json.load(open(QUEUE))
    existing = {t.get("label") for t in q["tasks"]}
    seq_max = max((t.get("seq", 0) for t in q["tasks"]), default=0)
    added, skipped = 0, 0
    now_dt = dt.datetime.now(TZ)
    for day in dates:
        day_dir = "%04d/%02d/%02d" % (day.year, day.month, day.day)
        for w in windows_for(day):
            # 只入队已结束的窗: 进行中的窗等下一天 00:20 任务补入 (防把半窗当完整窗爬)
            we = dt.datetime.fromisoformat(w["win_end"])
            if we > now_dt:
                log("跳过(窗未结束): %s" % w["label"])
                continue
            if w["label"] in existing:
                skipped += 1
                continue
            if archive_has_nf_api(day_dir, w["slot"]):
                # 归档已有 nf_api 数据 -> 直接标 done (不重复爬)
                seq_max += 1
                q["tasks"].append(dict(w, seq=seq_max, status="done",
                                       commit="nf_api", note="archive_exists_skip"))
                added += 1
                log("跳过(归档已有 nf_api): %s" % w["label"])
                continue
            seq_max += 1
            q["tasks"].append(dict(w, seq=seq_max, status="pending",
                                   attempt=0, note="daily_incremental"))
            added += 1
            log("入队: %s" % w["label"])
    q["created"] = q.get("created") or dt.datetime.now(TZ).isoformat()
    json.dump(q, open(QUEUE, "w"), ensure_ascii=False, indent=1)
    log("完成: 新增 %d, 已存在跳过 %d" % (added, skipped))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log("FATAL: %s: %s" % (type(e).__name__, e))
        sys.exit(1)
