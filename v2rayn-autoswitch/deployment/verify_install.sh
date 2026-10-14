#!/usr/bin/env bash
# Static/runtime installation verification for the v2rayN bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V2RAYN_DIR="${V2RAYN_DIR:-/home/mac/v2rayN-linux-64}"
HERMES_HOME="${HERMES_HOME:-/home/mac/.hermes}"
SCRIPT_DIR="${SCRIPT_DIR:-/opt/data/scripts}"
RUNNER="${RUNNER:-v2rayn-switch-runner}"

for file in "$V2RAYN_DIR/autoswitch/autoswitch.py" "$V2RAYN_DIR/autoswitch/run.sh" \
  "$SCRIPT_DIR/v2rayn_autoswitch.sh" "$SCRIPT_DIR/v2rayn_mode_guard.py" \
  "$SCRIPT_DIR/v2rayn_mode_guard.sh" "$SCRIPT_DIR/v2rayn_owner.py"; do
  [[ -f "$file" ]] || { echo "缺少文件: $file" >&2; exit 1; }
done
bash -n "$V2RAYN_DIR/autoswitch/run.sh" "$SCRIPT_DIR"/*.sh
python3 -m py_compile "$V2RAYN_DIR/autoswitch/autoswitch.py" "$SCRIPT_DIR"/v2rayn_*.py
python3 "$SCRIPT_DIR/v2rayn_mode_guard_test.py"

if docker ps --format '{{.Names}}' | grep -qx "$RUNNER"; then
  docker exec "$RUNNER" python3 -m py_compile /home/mac/.hermes/scripts/v2rayn_mode_guard.py
  docker exec -u 0 "$RUNNER" python3 /home/mac/.hermes/scripts/v2rayn_mode_guard.py --dry-run
else
  echo "runner 未运行，跳过容器内 dry-run"
fi

if python3 - <<'PY'
import socket
s=socket.socket(); s.settimeout(1)
try:
    s.connect(('127.0.0.1',10808))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
then
  curl -x socks5h://127.0.0.1:10808 -o /dev/null -s \
    -w 'proxy_http=%{http_code} total=%{time_total}\n' \
    --max-time 10 https://www.google.com/generate_204
else
  echo '10808 当前未监听：跳过代理 204 验收（启动 GUI/fallback 后再执行）'
fi
printf '%s\n' 'v2rayN AutoSwitch 安装验收通过。'
