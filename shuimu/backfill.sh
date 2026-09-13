#!/bin/bash
# 任务②: 补爬 08-31 ~ 09-02 (每天一个独立登录, 窗口=该天 00:00~次日 00:00 北京)
cd /opt/data/scripts/shuimu_daily
PY=/opt/data/venvs/shuimu/bin/python
for day in 2026-08-31 2026-09-01 2026-09-02; do
  echo "=== BACKFILL $day (slot 24 目录) ==="
  $PY shuimu_run.py --slot 24 --date $day 2>&1
  echo "EXIT=$?"
  sleep 10
done
echo "ALL_BACKFILL_DONE"
