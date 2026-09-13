#!/bin/bash
# stock_runner_cron.sh — 空档长会话补爬 (no_agent: 有数据=直发摘要, 无=静默)
# 用法: stock_runner_cron.sh <budget_min> <END_HH:MM>
# 逻辑: 整空档持续爬 — 每轮跑一个窗(或续跳), 成功→下一窗, 0帖→断点续, Busy→等
#       主档整点 0-9 分让路; 到 END 收手(留 10 分钟给下一档主档)
export TZ=Asia/Shanghai
PY=/opt/data/venvs/shuimu/bin/python
DIR=/opt/data/scripts/shuimu_daily
BUDGET="${1:-210}"
END="${2:-}"
start=$(date +%s)
end_epoch=""
if [ -n "$END" ]; then
  end_epoch=$(date -d "today $END" +%s)
  [ "$end_epoch" -le "$start" ] && end_epoch=$((end_epoch + 86400))
fi
emit() { [ -n "$1" ] && printf '%s\n' "$1"; }
while :; do
  nows=$(date +%s)
  [ -n "$end_epoch" ] && [ "$nows" -ge "$end_epoch" ] && { emit "SLOT_END 到($END), 收手"; break; }
  [ $((nows - start)) -gt $((430 * 60)) ] && { emit "MAX_RUN 到, 收手"; break; }
  hh=$(date +%H); mm=$(date +%M)
  case "$hh" in
    0|8|12|16) [ "$mm" -lt 10 ] && { sleep 660; continue; } ;;
  esac
  out=$("$PY" "$DIR/stock_runner.py" --budget-min "$BUDGET" 2>&1)
  echo "$out" >> "$DIR/logs/stock_runner_cron.log"
  case "$out" in *QUEUE_EMPTY*) emit "QUEUE_EMPTY 全部完成, 收手"; break ;; esac
  dl=$(echo "$out" | grep -E 'TASK_DONE posts=[1-9]' | tail -1 | sed 's/^[^]]*\] //')
  [ -n "$dl" ] && emit "✅ 水木Stock补爬: $dl"
  # 无论 0帖(续跳中) / Busy / 完成, 歇 2 分钟开下一轮 (断点已存队列)
  sleep 120
done
exit 0
