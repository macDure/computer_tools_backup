#!/usr/bin/env bash
# v2rayn_c1s2_guard.sh — cron 入口: 确保 runner 存活 -> 跑守护 (常态零输出)
set -u
export TZ=Asia/Shanghai
RUNNER=v2rayn-switch-runner
if ! docker ps --format '{{.Names}}' | grep -qx "$RUNNER"; then
  docker rm -f "$RUNNER" >/dev/null 2>&1
  docker run -d --name "$RUNNER" --restart unless-stopped \
    --pid=host --network=host --user 1000:1000 \
    --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
    -v /home/mac:/home/mac \
    --entrypoint /usr/bin/tail hermes-agent:local -f /dev/null >/dev/null
fi
exec 9>/tmp/v2rayn_c1s2_guard.lock
flock -n 9 || exit 0
docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_c1s2_guard.py >/dev/null 2>&1
exit 0
