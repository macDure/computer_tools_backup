#!/usr/bin/env bash
# Create/start the host-PID/network Docker runner used by v2rayN tools.
set -euo pipefail
RUNNER="${RUNNER:-v2rayn-switch-runner}"
IMAGE="${IMAGE:-hermes-agent:local}"

if ! command -v docker >/dev/null 2>&1; then
  echo '未找到 docker' >&2
  exit 2
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "未找到镜像 $IMAGE；请先准备与当前环境相同的 Hermes 本地镜像" >&2
  exit 2
fi
if docker ps --format '{{.Names}}' | grep -qx "$RUNNER"; then
  echo "$RUNNER 已在运行"
  exit 0
fi
if docker ps -aq --filter "name=^/${RUNNER}$" | grep -q .; then
  docker start "$RUNNER" >/dev/null
else
  docker run -d --name "$RUNNER" --restart unless-stopped \
    --pid=host --network=host --user 1000:1000 \
    --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
    -v /home/mac:/home/mac \
    --entrypoint /usr/bin/tail "$IMAGE" -f /dev/null >/dev/null
fi
for _ in 1 2 3 4 5; do
  if docker ps --format '{{.Names}}' | grep -qx "$RUNNER"; then
    docker ps --filter "name=^/${RUNNER}$" --format '{{.Names}} {{.Status}}'
    exit 0
  fi
  sleep 1
done
echo "runner 启动失败: $RUNNER" >&2
exit 1
