#!/bin/bash
# v2rayN 订阅高频刷新 — cron 宿主侧入口 (每 30min)
# 容器把宿主 /home/mac 原样挂进来, /opt/data = 宿主 /home/mac/.hermes,
# 所以容器内直接可见 /home/mac/.hermes/scripts/v2rayn_sub_refresh.py, 无需 cp。
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
OUT=$(docker exec -u 0 "$RUNNER" bash -c \
  'python3 /home/mac/.hermes/scripts/v2rayn_sub_refresh.py 2>&1 | tee -a /home/mac/v2rayN-linux-64/autoswitch/logs/sub-refresh.log')
rc=${PIPESTATUS[0]}
if [ $rc -ne 0 ]; then
  echo "[v2rayN 订阅刷新失败 exit=$rc] 日志尾部:"
  echo "$OUT" | tail -12
  exit $rc
fi
exit 0
