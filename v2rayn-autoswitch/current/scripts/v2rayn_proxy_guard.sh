#!/usr/bin/env bash
# v2rayN 10808 代理看门狗 v3 — GUI 感知端口状态机 (hermes cron, no_agent)
# 用户 2 原则: ① 10808 任何时刻最多一个持有者, 绝不抢端口
#             ② GUI 运行时助手只做"定时更新订阅 + 保活", 不管理 GUI
# 状态机 (每 tick, v3 起 1 分钟):
#   S1 端口UP+gui 持有        → 静默
#   S2 端口UP+fallback 持有+GUI 在 → 交接: kill 兜底 → 等 GUI 核心绑 10808(15s)
#                                    没绑上立即拉回兜底 (窗口期≤20s, 绝不裸奔)
#   S3 端口DOWN+GUI 在         → 拉兜底(若未拉)→ 等 15s: 接管→ok / 没接管→保持兜底+告警
#   S4 端口DOWN+GUI 不在       → 拉兜底 / 两次失败→完整 run.sh (v2 原逻辑)
# 09-08 事故修复: 兜底 xray stderr 落盘 + 启动前 JSON 校验; 交接/拉取前按 PID 精确
#   kill (不用 pkill), 防重入 (PULLED 标记), 60 分钟告警冷却
set -u
export TZ=Asia/Shanghai
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${PATH:+:$PATH}

RUNNER=v2rayn-switch-runner
VDIR=/home/mac/v2rayN-linux-64
AW=$VDIR/autoswitch
CFG=$VDIR/guiConfigs/config.json
XRAY=$VDIR/bin/xray/xray
DELIV=/opt/data/scripts/shuimu_daily/deliver_feishu.py
LOG=/opt/data/scripts/logs/v2rayn_guard.log
STATE=/opt/data/scripts/logs/v2rayn_guard.state
XRAYERR=/home/mac/.hermes/logs/v2rayn_fallback_xray.log
mkdir -p /opt/data/scripts/logs
ts() { date '+%F %T'; }
logf() { echo "$(ts) $*" >> "$LOG"; }

# 09-08 修复: /dev/tcp 在 cron 环境下可能永久挂起 (无超时), 改用 python socket 3s 超时
port_up() { timeout 8 python3 -c '
import socket, sys
s = socket.socket()
s.settimeout(3)
try:
    s.connect(("127.0.0.1", 10808))
    sys.exit(0)
except Exception:
    sys.exit(1)
' 2>/dev/null; }
gui_running() { docker exec "$RUNNER" pgrep -f '\./v2rayN([[:space:]]|$)' >/dev/null 2>&1; }

state_get() { sed -n "s/^$1=//p" "$STATE" 2>/dev/null | head -1; }
state_set() { # 多行 state 文件: 替换或追加
  local tmp; tmp=$(mktemp)
  grep -v "^$1=" "$STATE" 2>/dev/null > "$tmp" || true
  echo "$1=$2" >> "$tmp"
  mv "$tmp" "$STATE"
}

feishu() {
  local out
  out=$(echo "$1" | python3 "$DELIV" - 2>&1) || return 1
  echo "$out" | grep -qi "OK success"
}
alert() { # $1=正文; 60 分钟冷却
  local last now
  now=$(date +%s); last=$(state_get ALERT_TS || echo 0)
  if [ "$last" = "" ]; then last=0; fi
  if [ $((now - last)) -lt 3600 ]; then logf "ALERT_COOLDOWN $1"; return 0; fi
  if feishu "### ⚠️ v2rayN 代理异常 (北京 $(ts))
$1
每 1 分钟重试, 连续异常 60 分钟内仅提醒一次。"; then state_set ALERT_TS "$now"; else logf "FEISHU_FAIL"; fi
}

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

# 启动兜底 xray (root, stderr 落盘, 启动前 JSON 校验); 已有 root xray 在跑则跳过
# 注意: 只认 uid=0 的 xray (我们自己的); GUI 核心 (uid=1000) 也叫 xray, 不能误判
pull_fallback() {
  local have_root
  have_root=$(docker exec -u 0 "$RUNNER" bash -c '
for p in $(pgrep -ax xray 2>/dev/null | cut -d" " -f1); do
  u=$(awk "/^Uid:/{print \$2}" /proc/$p/status 2>/dev/null)
  [ "$u" = "0" ] && { echo yes; exit 0; }
done')
  [ -n "$have_root" ] && return 0
  docker exec -u 0 "$RUNNER" bash -c \
    "test -f $CFG && python3 -c 'import json,sys; json.load(open(sys.argv[1]))' \"$CFG\" 2>/dev/null && grep -q 10808 $CFG" || return 1
  # 09-08 根因修复: xray 按可执行文件所在目录找 geosite.dat (bin/xray/), .dat 实际在 bin/
  # 必须: cd bin/xray (cwd 无关, exe 目录才是关键) + 符号链接兜底 (防 EDR 还原/重装丢失)
  docker exec -u 0 "$RUNNER" bash -c \
    "cd /home/mac/v2rayN-linux-64/bin/xray && [ -e geosite.dat ] || ln -sf ../geosite.dat geosite.dat; [ -e geoip.dat ] || ln -sf ../geoip.dat geoip.dat" 2>/dev/null
  apply_cn_route
  docker exec -u 0 "$RUNNER" bash -c \
    "mkdir -p $(dirname $XRAYERR) && cd /home/mac/v2rayN-linux-64/bin/xray && nohup $XRAY run -c $CFG >> $XRAYERR 2>&1 &" >/dev/null 2>&1
  sleep 5
  port_up
}

# cn-route 自愈 (09-11): config.json 被重建/还原后, 兜底 xray 会失去"国内/内网直连"规则
# → 全部流量走海外节点 (国内慢+内网503 的根因)。每次拉兜底前重放幂等补丁
# (脚本路径 = 宿主 /home/mac/.hermes/scripts/v2rayn_cn_route_fix.py, runner 内同路径)
apply_cn_route() {
  docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_cn_route_fix.py >/dev/null 2>&1 || \
    logf "cn_route_fix 应用失败 (本次兜底将全走海外, 下 tick 再试)"
}

# 精确 kill 兜底 (root 的 xray; 按 pgrep -ax 匹配 xray 可执行文件, 不碰 GUI uid1000 核心)
kill_fallback() {
  local pids
  pids=$(docker exec -u 0 "$RUNNER" bash -c '
for p in $(pgrep -ax xray 2>/dev/null | cut -d" " -f1); do
  u=$(awk "/^Uid:/{print \$2}" /proc/$p/status 2>/dev/null)
  [ "$u" = "0" ] && echo $p
done')
  [ -n "$pids" ] || return 0
  for p in $pids; do docker exec -u 0 "$RUNNER" kill "$p" 2>/dev/null; done
  sleep 2
  for p in $pids; do docker exec -u 0 "$RUNNER" kill -9 "$p" 2>/dev/null; done
}

# ---- 1) 端口 UP 分支
if port_up; then
  if ! ensure_runner; then
    alert "- 10808 正常但 runner 容器 $RUNNER 不可用, 无法继续保活/交接。请检查 docker daemon。"
    exit 0
  fi
  own=$(docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_owner.py 10808 2>/dev/null)
  owner=${own%% *}; owner=${owner#OWNER=}
  gui=$(gui_running && echo 1 || echo 0)
  case "$owner" in
    gui)
      # S1: GUI 独占 → 理想状态, 静默
      if [ "$(state_get STATE)" = "free_window" ]; then
        # 空窗期结束, GUI 核心绑上 10808 → 交接成功
        state_set STATE ok; state_set PREV ok
        state_set HANDOFF_FREE_SINCE ""
        state_set HANDOFF_FAILS 0
        feishu "### ✅ v2rayN 代理已交接给你的 GUI 核心 (北京 $(ts))
- 10808 现在由你的 GUI 独占, 助手兜底已退出
- 助手不再碰端口, 只做保活检查 + 定时订阅更新" || logf "交接通知未确认"
        logf "HANDOFF_DONE: GUI 接管 10808"
        exit 0
      fi
      if [ "$(state_get STATE)" != "ok" ]; then
        state_set STATE ok
        if [ "$(state_get PREV)" = "down" ]; then
          feishu "### ✅ v2rayN 代理已恢复正常 (北京 $(ts))
- 10808 由你的 GUI 核心独占, 之前异常已消除" || logf "恢复通知未确认"
        fi
      fi
      state_set PREV ok
      exit 0
      ;;
    fallback)
      if [ "$gui" = 1 ]; then
        # S2: 交接 —— 兜底让位给 GUI 核心 (用户原则: 绝不抢端口)
        # 09-08 教训: GUI 核心绑不上 10808 后不会自动重试 → 不能立即拉回兜底(会永久堵死 GUI)
        # 策略: 让位后 120s 空窗期, 期间 GUI 核心(重)启动即可绑上; 超期未绑 → 拉回兜底
        # 熔断: 连续 3 个空窗周期都空 → 停止让位 (防反复断口)
        if [ -n "$(state_get HANDOFF_FREE_SINCE)" ]; then
          logf "S2: 已在空窗等待 GUI 绑 10808 (自 $(state_get HANDOFF_FREE_SINCE)), 不动"
          exit 0
        fi
        hf=$(state_get HANDOFF_FAILS); [ -z "$hf" ] && hf=0
        if [ "$hf" -ge 3 ]; then
          logf "HANDOFF_CIRCUIT: 已连续 3 个空窗周期 GUI 未绑上, 保持兜底持有, 等 GUI 关闭后复位"
          # 09-08 补: 仅在熔断触发的当刻 (hf 恰好=3) 通知一次, 之后保持静默持有
          if [ "$hf" = "3" ]; then
            feishu "### ⚠️ v2rayN: 你的 GUI 核心连续未接管 10808, 助手兜底已接管持有 (北京 $(ts))
- 现象: 让位后你的 GUI 核心始终没绑上 10808 (界面里核心大概率未运行或启动失败)
- 当前: 代理由助手兜底 xray 维持, 可用
- 想切回 GUI: 在 v2rayN 界面点『重启核心』(或重选节点), 接管成功助手会自动让位; 或先关 GUI 完全交给助手" || logf "熔断通知未确认"
          fi
          exit 0
        fi
        logf "HANDOFF: 10808=兜底, GUI 在跑 → 让位 (120s 空窗期)"
        kill_fallback
        state_set HANDOFF_FREE_SINCE "$(date +%s)"
        state_set STATE free_window
        state_set PREV down
        exit 0
      fi
      # GUI 不在, 兜底持有 → 正常, 静默
      if [ "$(state_get STATE)" != "ok" ]; then
        state_set STATE ok
        if [ "$(state_get PREV)" = "down" ]; then
          feishu "### ✅ v2rayN 代理已自动恢复 (北京 $(ts))
- 10808 由助手兜底 xray 维持, 之前异常已消除" || logf "恢复通知未确认"
        fi
      fi
      state_set PREV ok
      exit 0
      ;;
    none|other)
      logf "10808 UP 但持有者无法判定 (owner=$owner), 下轮重试"
      exit 0
      ;;
  esac
fi

# ---- 端口 DOWN 分支
if ! ensure_runner; then
  alert "- 现象: 10808 未监听
- 原因: runner 容器 $RUNNER 起/建均失败
- 动作: 请检查 docker daemon (dockerd 状态)"
  exit 0
fi

# autoswitch 持锁 (08:29 正在跑, 会自己收尾拉代理) → 让路
if ! docker exec -u 0 "$RUNNER" python3 -c "
import fcntl, sys
f = open('$AW/autoswitch.lock', 'a')
try:
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(1)
" 2>/dev/null; then
  logf "autoswitch 持锁运行中, 跳过本 tick"
  exit 0
fi

if [ "$(state_get STATE)" != "down" ]; then
  state_set STATE down
  logf "10808 DOWN, 开始恢复"
fi

gui=$(gui_running && echo 1 || echo 0)
if [ "$gui" = 0 ]; then
  # GUI 不在 → 复位交接状态, 走 S4 (兜底接管)
  if [ -n "$(state_get HANDOFF_FREE_SINCE)" ]; then
    state_set HANDOFF_FREE_SINCE ""
    state_set HANDOFF_FAILS 0
    logf "GUI 已关闭, 复位交接状态 (FREE_SINCE/FAILS)"
  fi
else
  # S3: GUI 在跑, 10808 down
  fs=$(state_get HANDOFF_FREE_SINCE)
  if [ -n "$fs" ]; then
    # 我们自己让出的空窗期: 等 GUI 核心(重)启动后自行绑上
    now=$(date +%s)
    if [ $((now - fs)) -lt 120 ]; then
      logf "空窗进行中 ($((now - fs))s/120s), 等 GUI 核心绑 10808, 不动"
      exit 0
    fi
    # 空窗超期: GUI 核心没起来 → 拉回兜底保代理 + 记一次失败
    state_set HANDOFF_FREE_SINCE ""
    hf=$(state_get HANDOFF_FAILS); [ -z "$hf" ] && hf=0
    hf2=$((hf + 1)); state_set HANDOFF_FAILS "$hf2"
    if pull_fallback; then
      logf "空窗超期, GUI 核心未绑上, 已拉回兜底 (第 $hf2 次)"
    else
      logf "空窗超期, 拉回兜底失败, stderr 尾部:"
      docker exec -u 0 "$RUNNER" bash -c "tail -5 $XRAYERR 2>/dev/null" 2>/dev/null | sed 's/^/    | /' >> "$LOG"
    fi
    alert "- 现象: 让出 10808 给你的 GUI 后 120 秒, 你的 GUI 核心仍未绑上
- 当前: 助手兜底 xray 已接管保代理 (如已恢复请忽略本条)
- 处理: 在 v2rayN 界面点『重启核心』(或重新选节点) 让核心起来, 起来后助手会自动让位
- 若反复无效: 可先关 GUI, 完全交给助手兜底"
    exit 0
  fi
  # 非空窗 (核心刚崩 / GUI 刚启动): 先拉兜底保代理, 下一 tick 由 S2 让位给 GUI
  if [ "$(state_get PULLED)" != 1 ]; then
    if pull_fallback; then
      state_set PULLED 1
      logf "PULLED fallback (GUI 在跑, 10808 空窗) — 下 tick S2 让位"
    else
      logf "PULL_FAILED (GUI 在跑), stderr 尾部:"
      docker exec -u 0 "$RUNNER" bash -c "tail -5 $XRAYERR 2>/dev/null" 2>/dev/null | sed 's/^/    | /' >> "$LOG"
    fi
  fi
  alert "- 现象: 10808 掉线, 你的 GUI 在跑
- 当前: 助手兜底 xray 临时维持代理, 下一分钟内会自动让位给你的 GUI
- 若 GUI 界面核心未运行: 请点一次『重启核心』(或重选节点), 核心起来后助手让位"
  exit 0
fi

# S4: GUI 不在 —— 原 v2 恢复逻辑 (兜底 ×2 → run.sh)
for attempt in 1 2; do
  if pull_fallback; then
    state_set PULLED 0
    node=$(docker exec -u 0 "$RUNNER" bash -c "grep -o '\"address\": \"[^\"]*\"' $CFG | head -1")
    state_set STATE ok; state_set PREV ok
    feishu "### ✅ v2rayN 代理已自动恢复 (北京 $(ts))
- 10808 之前无人监听 (疑似 docker 重启/断电重启, 容器内兜底 xray 随容器消亡)
- 已按上次兜底配置拉起 xray: $node
- 如需切换节点等 08:29 自动切换" || logf "恢复成功但飞书未确认"
    logf "RECOVERED via fallback xray ($node, attempt=$attempt)"
    exit 0
  fi
  logf "兜底 xray 第 $attempt 次起后 10808 仍未监听; stderr 尾部:"
  docker exec -u 0 "$RUNNER" bash -c "tail -5 $XRAYERR 2>/dev/null" 2>/dev/null | sed 's/^/    | /' >> "$LOG"
  [ "$attempt" = 1 ] && sleep 3
done

# 完整自愈: 补丁重放 + run.sh
docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_parse_ss_fix.py "$AW/autoswitch.py" >/dev/null 2>&1
docker exec -u 0 "$RUNNER" bash -c "cd $AW && ./run.sh" >/dev/null 2>&1
sleep 5
if port_up; then
  state_set PULLED 0
  state_set STATE ok; state_set PREV ok
  feishu "### ✅ v2rayN 代理已自动恢复 (北京 $(ts))
- 10808 掉线后走完整切换流程重建 (探测→订阅→选延迟最小→兜底 xray)
- 恢复验证通过" || logf "run.sh 恢复成功但飞书未确认"
  logf "RECOVERED via full run.sh"
  exit 0
fi

alert "- 现象: 10808 未监听, 兜底 xray 与完整 run.sh 均未能恢复
- 日志: $LOG 及 $AW/logs/auto-\$(TZ=Asia/Shanghai date +%Y%m%d).log
- 请人工检查"
logf "RECOVERY_FAILED"
exit 0
