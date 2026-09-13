#!/bin/bash
# 水木 7 天缺口补爬 — 单天串行模式 (2026-09-07)
# 每天一个独立 telnet 会话, 失败不影响其他天; 天间隔 90s 错峰防限流
PY=/opt/data/venvs/shuimu/bin/python
SCRIPT=/opt/data/scripts/shuimu_daily/backfill_range.py
LOG=/tmp/backfill_seq.log
: > "$LOG"
for d in 2026-08-31 2026-09-01 2026-09-02 2026-09-03 2026-09-04 2026-09-05 2026-09-06; do
  echo "===== DAY $d start $(TZ=Asia/Shanghai date '+%H:%M:%S') =====" >> "$LOG"
  $PY -u $SCRIPT --start $d --end $d >> "$LOG" 2>&1
  echo "===== DAY $d done exit=$? $(TZ=Asia/Shanghai date '+%H:%M:%S') =====" >> "$LOG"
  sleep 90
done
echo "ALL_DAYS_DONE $(TZ=Asia/Shanghai date '+%H:%M:%S')" >> "$LOG"
