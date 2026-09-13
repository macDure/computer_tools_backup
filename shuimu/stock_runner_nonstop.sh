#!/bin/bash
# stock_runner_nonstop.sh — 不停车补爬主循环 (09-09 用户指令: "一口气不停车的干, 不等窗口")
# 无 END 收手点 / 无 MAX_RUN: 直到队列 36 窗全部 done 才退出。
# 纪律: 主档整点 0-9 分让路(stock_runner 内 near_stop 自动收手); flock 单会话锁不变。
# 自愈: cron 看门狗 stock_runner_nonstop_wd.sh 每 30min 检查, 死了自动拉起。
export TZ=Asia/Shanghai
PY=/opt/data/venvs/shuimu/bin/python
DIR=/opt/data/scripts/shuimu_daily
LOG=$DIR/logs/stock_runner_nonstop.log
STATE=$DIR/logs/stock_runner_nonstop.state
BUDGET=300   # 单轮预算 5h, 一轮可啃 3~5 窗

wlog() { echo "[$(date '+%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

wlog "NONSTOP_START pid=$$ budget=$BUDGET"
round=0
while :; do
  # 队列状态快照
  qs=$("$PY" - <<'PYEOF'
import json
q = json.load(open('/opt/data/scripts/shuimu_daily/backfill_queue.json'))
pend = [t for t in q['tasks'] if t['status'] == 'pending']
done = sum(1 for t in q['tasks'] if t['status'] in ('done', 'done_partial'))
print("%d %d %s" % (len(pend), done, pend[0]['label'] if pend else '-'))
PYEOF
)
  read -r PENDING DONE NEXT <<< "$qs"
  echo "round=$(date '+%F %H:%M:%S') pending=$PENDING done=$DONE next=$NEXT pid=$$" > "$STATE"
  wlog "ROUND 待爬=$PENDING 已完成=$DONE 下一窗=$NEXT"
  [ "$PENDING" -eq 0 ] && { wlog "QUEUE_EMPTY 全部窗口补爬完成"; break; }

  # 已有 stock_runner 在跑(例如看门狗重启竞争)则不双开, 等它跑
  if pgrep -f "venvs/shuimu/bin/python .*stock_runner.py" >/dev/null; then
    wlog "已有 stock_runner 在跑, 本循环待命 300s"
    sleep 300
    continue
  fi

  # 主档整点 0-9 分让路 (主档 cron 目前暂停, 此分支为将来恢复时留的保险)
  hh=$(date +%H); mm=$(date +%M)
  case "$hh" in 0|8|12|16) [ "$mm" -lt 10 ] && { wlog "主档整点让路, 睡 10min"; sleep 600; continue; } ;; esac

  round=$((round+1))
  out=$("$PY" "$DIR/stock_runner.py" --budget-min "$BUDGET" 2>&1)
  echo "===== round $round $(date '+%F %H:%M:%S') =====" >> "$DIR/logs/stock_runner_cron.log"
  echo "$out" >> "$DIR/logs/stock_runner_cron.log"
  echo "$out" | grep -E "TASK|归档|ABORT|KICK|TIMEOUT|QUEUE_EMPTY|SESSION_BUSY" | tail -8 | sed "s/^/[$(date '+%m-%d %H:%M:%S')] /" >> "$LOG"
  case "$out" in *QUEUE_EMPTY*) wlog "QUEUE_EMPTY 全部完成"; break ;; esac
  sleep 120
done
wlog "NONSTOP_END pid=$$ round=$round"
exit 0
