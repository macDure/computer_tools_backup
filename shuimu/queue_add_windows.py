#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""queue_add_windows.py — 水木 Stock 分档增量入队 (幂等, 零 4h 延迟版)。

4 档计划 (北京时间, 09-11 用户改): 每档只爬「刚结束的那 4 小时段」, 延迟 ≤4h:
  08:00 -> 今天 w00(00-04) + w04(04-08)   [04:00 无档, w00 随 08:00 档爬]
  12:00 -> 今天 w08(08-12)
  16:00 -> 今天 w12(12-16)
  23:58 -> 今天 w16(16-20) + w20(20-24)   [w20 按 3min 宽限当已结束, 漏 23:58-24:00 两分钟,
                                            深夜帖量极小可接受]
补洞: 当天更早档的窗若缺失 (上一档爬失败) 随本档补爬; 跨天洞由次日 08:00 档补 (仅缺失才补)。
串行铁律: 同一时间只有一个爬虫进程 (看门狗 pidfile 守卫), 单账号 (同一凭据文件), 绝不并行/多登录。
--date YYYY-MM-DD: 指定某一天 (运维补洞)。
cron (UTC): 0 0,4,8 * * * (北京 08/12/16) 和 58 15 * * * (北京 23:58) no_agent 跑。
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

def slot_plan(now: dt.datetime):
    """按档声明: (本档主爬窗, 补洞窗范围)。每档只爬刚结束的 4h 段, 零额外延迟。"""
    h = now.hour
    today = now.date()
    yesterday = today - dt.timedelta(days=1)
    if h >= 8 and h < 12:    # 08:00 档
        return ([w for w in windows_for(today) if w["slot"] in ("w00", "w04")],
                [w for w in windows_for(yesterday)])
    if h >= 12 and h < 16:   # 12:00 档
        return ([w for w in windows_for(today) if w["slot"] == "w08"],
                [w for w in windows_for(today) if w["slot"] in ("w00", "w04")])
    if h >= 16 and h < 20:   # 16:00 档
        return ([w for w in windows_for(today) if w["slot"] == "w12"],
                [w for w in windows_for(today) if w["slot"] in ("w00", "w04", "w08")])
    if h >= 20:              # 23:58 档
        return ([w for w in windows_for(today) if w["slot"] in ("w16", "w20")],
                [w for w in windows_for(today) if w["slot"] in ("w00", "w04", "w08", "w12")])
    # 非 4 档时点 (手动运行): 今天全部已结束窗
    return ([w for w in windows_for(today)], [])

def main():
    ap = sys.argv[1:]
    dates, i = [], 0
    while i < len(ap):
        if ap[i] == "--date":
            dates.append(dt.date.fromisoformat(ap[i + 1])); i += 2
        else:
            i += 1

    q = json.load(open(QUEUE))
    existing = {t.get("label") for t in q["tasks"]}
    seq_max = max((t.get("seq", 0) for t in q["tasks"]), default=0)
    added, skipped = 0, 0
    now_dt = dt.datetime.now(TZ)

    if dates:
        # 运维补洞: 指定日子的全部 6 窗
        targets = [w for d in dates for w in windows_for(d)]
        note = "manual_backfill"
    else:
        primary, backfill = slot_plan(now_dt)
        targets = primary + [w for w in backfill if w not in primary]
        note = "slot_run"
    # 去重保序 (补洞窗可能已在主爬窗里)
    seen = set(); targets = [w for w in targets if not (w["label"] in seen or seen.add(w["label"]))]

    for w in targets:
        day = dt.date.fromisoformat(w["day"])
        day_dir = "%04d/%02d/%02d" % (day.year, day.month, day.day)
        # 只入队已结束的窗 (+3min 宽限: 23:58 档让 w20 也能入队, 最晚漏 2 分钟深夜帖);
        # 未结束的窗等下一档入队 (防把半窗当完整窗爬)
        we = dt.datetime.fromisoformat(w["win_end"])
        if we > now_dt + dt.timedelta(minutes=3):
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
                               attempt=0, note=note))
        added += 1
        log("入队[%s]: %s" % (note, w["label"]))
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
