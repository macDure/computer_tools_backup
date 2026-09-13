#!/bin/bash
# stock_runner_nonstop_wd.sh — 不停车补爬看门狗 (cron no_agent, 每 30min)
# 静默原则: 一切正常 → 无输出(不打扰用户); 只有"重新拉起循环"才直发飞书告警。
export TZ=Asia/Shanghai
DIR=/opt/data/scripts/shuimu_daily
PY=/opt/data/venvs/shuimu/bin/python

# 1) 队列已空 → 不需要看门狗干活
pend=$("$PY" -c "import json;q=json.load(open('$DIR/backfill_queue.json'));print(sum(1 for t in q['tasks'] if t['status']=='pending'))")
[ "$pend" -eq 0 ] && exit 0

# 2) 主循环或 stock_runner 在跑 → 正常
pgrep -f "stock_runner_nonstop.sh" >/dev/null && {
  # 2b) 09-10 升级: 进程活着也可能挂死(无 socket 超时, BBS 卡 recv,
  #     13:42-15:50 实证 76min 日志静默)。日志 >25min 没动 = 挂死, 杀 python 让循环重拉。
  #     正常运行时日志至少每 60s 一行(跳转步/收帖/让路), 25min 阈值安全。
  pid=$(pgrep -f "venvs/shuimu/bin/python .*stock_runner.py" | head -1)
  if [ -n "$pid" ] && [ -f "$DIR/logs/stock_runner.log" ]; then
    now_s=$(date +%s); log_s=$(stat -c %Y "$DIR/logs/stock_runner.log")
    if [ $((now_s - log_s)) -gt 1500 ]; then
      kill "$pid" 2>/dev/null
      sleep 5
      pgrep -f "venvs/shuimu/bin/python .*stock_runner.py" >/dev/null && kill -9 "$pid" 2>/dev/null
      "$PY" - <<EOF
import sys
sys.path.insert(0, "$DIR")
import shuimu_run as R
R.feishu_send("⚠️ 水木补爬 runner 挂死(日志静默 %d min), 看门狗已杀进程, 循环 2min 内自动重拉" % $(( (now_s - log_s) / 60 )))
EOF
      echo "WATCHDOG_STALL_KILL pid=$pid silent_min=$(( (now_s - log_s) / 60 ))"
    fi
  fi
  exit 0
}
pgrep -f "venvs/shuimu/bin/python .*stock_runner.py" >/dev/null && exit 0

# 3) 都死了且队列还有活 → 拉起 (setsid 脱离 cron shell, 进程树独立)
wlog="/tmp/nonstop_wd_$$"
setsid bash "$DIR/stock_runner_nonstop.sh" </dev/null >>"$DIR/logs/stock_runner_nonstop.log" 2>&1 &
sleep 5
if pgrep -f "stock_runner_nonstop.sh" >/dev/null; then
  # 直发飞书 (规避 #47056 静默丢消息)
  "$PY" - <<EOF
import sys
sys.path.insert(0, "$DIR")
import shuimu_run as R
ok = R.feishu_send("⚠️ 水木不停车补爬循环意外中断, 看门狗已自动拉起 (剩余 %s 窗)" % "$pend")
print("feishu:", ok)
EOF
  echo "WATCHDOG_RESTART pending=$pend"
fi
exit 0
