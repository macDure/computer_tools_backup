#!/usr/bin/env bash
# v2rayN 统一时段守护：04:00-08:28 保 c1s3，08:28-08:33 给 08:29 主任务让行；
# 08:29-次日04:00 优先 c1s1/c1s2，c1s3 仅作故障临时兜底并触发订阅复检
set -u
export TZ=Asia/Shanghai
RUNNER=v2rayn-switch-runner

ensure_runner() {
  if docker ps -q --filter name="$RUNNER" 2>/dev/null | grep -q .; then
    return 0
  fi
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
  printf '%s\n' '⚠️ v2rayN 时段守护: runner 容器不可用，未执行本轮检查。'
  exit 0
fi

# 所有实际读写、host PID 观察和信号操作都在 runner 内完成。
out=$(docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_mode_guard.py 2>&1)
rc=$?
if [ "$rc" -eq 0 ]; then
  [ -n "$out" ] && printf '%s\n' "$out"
  exit 0
fi
if [ -n "$out" ]; then
  printf '%s\n' "$out"
else
  printf '⚠️ v2rayN 时段守护: runner/Python 执行失败(rc=%s)，未确认代理状态。\n' "$rc"
fi
# no_agent 由 stdout 投递告警；脚本异常本身不让调度器进入重试风暴。
exit 0
