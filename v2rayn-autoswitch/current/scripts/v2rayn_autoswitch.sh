#!/usr/bin/env bash
# v2rayN autoswitch 封装 — hermes cron 每天 0:29 UTC (北京 08:29) 触发
# no_agent 看门狗模式: 成功静默(exit 0, stdout 空); 失败→deliver_feishu.py 直发告警
# 依赖: 宿主机 /home/mac 经 runner 容器直通; runner 需 unconfined + root exec 才能给宿主 v2rayN 发信号
set -u
export TZ=Asia/Shanghai
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${PATH:+:$PATH}

RUNNER=v2rayn-switch-runner
AW=/home/mac/v2rayN-linux-64/autoswitch
DELIV=/opt/data/scripts/shuimu_daily/deliver_feishu.py
LOG=/opt/data/scripts/logs/v2rayn_autoswitch.log
NOTIFY=/opt/data/scripts/v2rayn_sub_notify.py
mkdir -p /opt/data/scripts/logs
ts() { date '+%F %T'; }
logf() { echo "$(ts) $*" >> "$LOG"; }

# 1) 自愈: 确保 runner 容器存活 (unconfined + host pid/net + /home/mac 挂载)
ensure_runner() {
  if docker ps -q --filter name="$RUNNER" 2>/dev/null | grep -q .; then return 0; fi
  if docker ps -aq --filter name="$RUNNER" 2>/dev/null | grep -q .; then
    docker start "$RUNNER" >/dev/null 2>&1
  else
    docker rm -f "$RUNNER" >/dev/null 2>&1
    docker run -d --name "$RUNNER" --restart unless-stopped \
      --pid=host --network=host --user 1000:1000 \
      --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
      -v /home/mac:/home/mac \
      --entrypoint /usr/bin/tail hermes-agent:local -f /dev/null >/dev/null 2>&1
  fi
  sleep 3
  docker ps -q --filter name="$RUNNER" 2>/dev/null | grep -q .
}

if ! ensure_runner; then
  msg="$(ts) [v2rayN autoswitch] 失败: runner 容器 $RUNNER 不可用(起/建均失败), 本次未执行。请检查 docker daemon。"
  echo "$msg" >> "$LOG"
  echo "$msg" | python3 "$DELIV" - >/dev/null 2>&1 || true
  exit 0
fi

# 2) 自愈补丁: 宿主存在按源版本还原 autoswitch.py 的行为, 每次运行前重放幂等补丁
#    (兼容整段 base64 的老式 ss 链接 c1s1/c1s2; 幂等, 已打则直接跳过)
fix=$(docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_parse_ss_fix.py "$AW/autoswitch.py" 2>&1)
logf "parse_ss_fix: $fix"
if ! echo "$fix" | grep -q "PATCHED\|ALREADY_PATCHED"; then
  msg="$(ts) [v2rayN autoswitch] 补丁应用失败($fix), 本次跳过执行避免坏库。"
  echo "$msg" | python3 "$DELIV" - >/dev/null 2>&1 || true
  exit 0
fi

# 2b) 温柔模式补丁: 检测到用户在 TTY 跑的 v2rayN GUI 时不杀不重启 (幂等, 已打则跳过)
gfix=$(docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_gentle_mode_fix.py "$AW/autoswitch.py" 2>&1)
logf "gentle_fix: $gfix"
if ! echo "$gfix" | grep -q "PATCHED\|ALREADY_PATCHED"; then
  msg="$(ts) [v2rayN autoswitch] 温柔模式补丁应用失败($gfix), 本次跳过执行避免坏库。"
  echo "$msg" | python3 "$DELIV" - >/dev/null 2>&1 || true
  exit 0
fi

# 2c) 温柔模式 V2 补丁 (09-08 事故修复: gentle 下绝不 kill 兜底 xray, 防 10808 裸奔)
#     必须在 V1 之后跑: V2 替换 V1 的 gentle 块; 已打 V2 时 V2 脚本直接 ALREADY_PATCHED
gfix2=$(docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_gentle_v2_fix.py "$AW/autoswitch.py" 2>&1)
logf "gentle_v2_fix: $gfix2"
if ! echo "$gfix2" | grep -q "PATCHED\|ALREADY_PATCHED"; then
  msg="$(ts) [v2rayN autoswitch] 温柔模式V2补丁应用失败($gfix2), 本次跳过执行避免再次弄断 10808。"
  echo "$msg" | python3 "$DELIV" - >/dev/null 2>&1 || true
  exit 0
fi

# 3) 正式执行 (run.sh 自带 flock 防重叠; root exec 才能给宿主 v2rayN 发信号)
out=$(docker exec -u 0 "$RUNNER" bash -c "cd $AW && ./run.sh" 2>&1)
code=$?
if [ "$code" -eq 75 ]; then
  # 统一守护可能恰好持有共享锁；不要把一次竞争误报成成功，短退避后重试。
  for delay in 3 5 8; do
    logf "autoswitch: 共享锁忙，${delay}s 后重试"
    sleep "$delay"
    retry_out=$(docker exec -u 0 "$RUNNER" bash -c "cd $AW && ./run.sh" 2>&1)
    retry_code=$?
    out="$out\n[retry ${delay}s exit=${retry_code}]\n${retry_out}"
    code=$retry_code
    [ "$code" -ne 75 ] && break
  done
fi
{ echo "===== $(ts) run start ====="; echo "$out"; echo "===== $(ts) exit=$code ====="; } >> "$LOG"

# 锁竞争重试仍失败时，不执行 cn-route 后处理，也不伪装成主任务成功。
if [ "$code" -eq 75 ]; then
  msg="$(ts) [v2rayN autoswitch] 共享锁连续忙，今日正式任务未执行；已跳过后处理，等待下一次任务。"
  logf "$msg"
  echo "$msg" | python3 "$DELIV" - >/dev/null 2>&1 || true
  exit 0
fi

# 3b) cn-route 自愈 (09-11): run.sh 的 fallback_xray 会用最小配置重建 config.json
#     (0 条路由 = 全流量走海外 → 国内慢+内网503)。run 之后重放幂等补丁;
#     gentle 模式下不重启任何 xray，避免触碰用户 GUI/其核心；非 gentle 才只重启 root 兜底。
cn=$(docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_cn_route_fix.py 2>&1)
logf "cn_route_fix: $cn"
gentle_now=$(docker exec -u 0 "$RUNNER" python3 -c "
import json
try:
    d = json.load(open('$AW/last_result.json'))
    print('true' if d.get('gentle') else 'false')
except Exception:
    print('false')" 2>/dev/null || true)
if [ "$gentle_now" = "true" ]; then
  logf "cn_route: gentle=true，跳过 xray 重启，保留 GUI/兜底当前进程"
else
  docker exec -u 0 "$RUNNER" bash -c '
CFG=/home/mac/v2rayN-linux-64/guiConfigs/config.json
XRAYERR=/home/mac/.hermes/logs/v2rayn_fallback_xray.log
pids=""
for p in $(pgrep -ax xray 2>/dev/null | cut -d" " -f1); do
  u=$(ps -o uid= -p "$p" 2>/dev/null | tr -d " ")
  [ "$u" = "0" ] && pids="$pids $p"
done
[ -n "$pids" ] || exit 0
for p in $pids; do kill $p 2>/dev/null; done
sleep 2
for p in $pids; do kill -9 $p 2>/dev/null; done
sleep 1
cd /home/mac/v2rayN-linux-64/bin/xray
[ -e geosite.dat ] || ln -sf ../geosite.dat geosite.dat
[ -e geoip.dat ] || ln -sf ../geoip.dat geoip.dat
mkdir -p $(dirname $XRAYERR)
nohup /home/mac/v2rayN-linux-64/bin/xray/xray run -c $CFG >> $XRAYERR 2>&1 &
' >> "$LOG" 2>&1
  logf "cn_route: 兜底 xray 已按新路由重启 (无 root xray 则跳过)"
fi

# 3) 结果处理: 0=全成功 / 75=flock 跳过 → 静默; 其余 → 直发飞书告警
if [ "$code" -eq 75 ]; then
  exit 0
fi
if [ "$code" -eq 0 ]; then
  # 成功通知: 订阅更新 diff + 当前节点 (无变化/无更新则脚本自己静默 exit 0)
  nout=$(python3 "$NOTIFY" 2>&1)
  logf "notify: $nout"
  exit 0
fi

summary=$(docker exec -u 0 "$RUNNER" python3 -c "
import json
try:
    d = json.load(open('$AW/last_result.json'))
    print('final=%s selected=%s sub_updated=%s proxy_restored=%s fallback_xray=%s' % (
        d.get('final_server'), d.get('selected'), d.get('sub_updated'),
        d.get('proxy_restored'), d.get('fallback_xray')))
except Exception as e:
    print('last_result.json 读取失败: %s' % e)" 2>/dev/null)

msg="### ⚠️ v2rayN autoswitch 异常 (北京 $(ts))
- 退出码: **$code**
- $summary
- 日志尾部:
\`\`\`
$(echo "$out" | tail -12)
\`\`\`
节点: c1s1/c1s2/c1s3/c1s4/c1s5/c1s801 (ss 老格式两节点需补丁支持)。如代理受影响请检查 10808。"
logf "ALERT exit=$code summary=$summary"
# 直发飞书 (cron auto-delivery 有静默失败缺陷 #47056, 必须直发)
if echo "$msg" | python3 "$DELIV" - 2>&1 | grep -qi "OK success"; then
  exit 0
fi
# 直发失败再试一次
sleep 3
if echo "$msg" | python3 "$DELIV" - 2>&1 | grep -qi "OK success"; then
  exit 0
fi
logf "FEISHU_DELIVERY_FAILED (已写日志, 直发未确认)"
exit 0
