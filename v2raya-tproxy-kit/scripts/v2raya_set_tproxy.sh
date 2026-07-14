#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${V2RAYA_BASE_URL:-http://127.0.0.1:2017}"
USER_NAME="${V2RAYA_USER:-macp}"
PASSWORD="${V2RAYA_PASS:-mac6833773}"
CRED_FILE="${V2RAYA_CRED_FILE:-/home/mac/v2raya-tproxy-kit/credentials/v2raya-web-credentials.txt}"
V2RAYN_CONFIG="${V2RAYN_CONFIG:-/home/mac/v2rayN-linux-64/guiConfigs/config.json}"

if [[ -z "$USER_NAME" || -z "$PASSWORD" ]]; then
  if [[ -r "$CRED_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CRED_FILE"
    USER_NAME="${USER_NAME:-${username:-}}"
    PASSWORD="${PASSWORD:-${password:-}}"
  fi
fi

if [[ -z "$USER_NAME" || -z "$PASSWORD" ]]; then
  echo "Missing v2rayA credentials. Set V2RAYA_USER and V2RAYA_PASS, or create $CRED_FILE." >&2
  exit 1
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 1; }
}

need_cmd curl
need_cmd jq
need_cmd systemctl
need_cmd gsettings
need_cmd python3

if ! systemctl is-active --quiet v2raya.service; then
  sudo systemctl enable --now v2raya.service >/dev/null
fi

login_v2raya() {
  local user="$1"
  local pass="$2"
  local payload resp token
  payload=$(jq -n --arg username "$user" --arg password "$pass" '{username:$username,password:$password}')
  resp=$(curl -sS --max-time 8 -H 'Content-Type: application/json' -d "$payload" "$BASE_URL/api/login")
  token=$(printf '%s' "$resp" | jq -r '.data.token // empty')
  if [[ -n "$token" && "$token" != "null" ]]; then
    printf '%s' "$token"
    return 0
  fi
  return 1
}

token=""
if token=$(login_v2raya "$USER_NAME" "$PASSWORD"); then
  :
elif [[ -r "$CRED_FILE" ]]; then
  # Fall back to the currently valid local credentials if the hardcoded defaults do not match this machine.
  # shellcheck disable=SC1090
  source "$CRED_FILE"
  USER_NAME="${username:-$USER_NAME}"
  PASSWORD="${password:-$PASSWORD}"
  token=$(login_v2raya "$USER_NAME" "$PASSWORD") || true
fi

if [[ -z "$token" ]]; then
  echo "Failed to log in to v2rayA API with hardcoded credentials and $CRED_FILE." >&2
  exit 1
fi

# If v2rayN has a working Shadowsocks proxy outbound, sync it into v2rayA.
# This prevents stale v2rayA node passwords after subscription updates in v2rayN.
if [[ -r "$V2RAYN_CONFIG" ]]; then
  python3 - "$V2RAYN_CONFIG" >/tmp/v2raya_import_payload.json <<'END_PY'
import base64
import json
import pathlib
import sys
import urllib.parse

cfg = json.loads(pathlib.Path(sys.argv[1]).read_text())
server = None
for outbound in cfg.get("outbounds", []):
    if outbound.get("tag") == "proxy" and outbound.get("protocol") == "shadowsocks":
        servers = outbound.get("settings", {}).get("servers", [])
        if servers:
            server = servers[0]
            break

if not server:
    raise SystemExit(0)

method = server.get("method")
password = server.get("password")
address = server.get("address")
port = server.get("port")
if not all([method, password, address, port]):
    raise SystemExit(0)

userinfo = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
name = urllib.parse.quote(f"v2rayN-current@{address}:{port}")
url = f"ss://{userinfo}@{address}:{port}#{name}"
print(json.dumps({"url": url, "which": {"id": 1, "_type": "server", "sub": 0}}, ensure_ascii=False))
END_PY

  if [[ -s /tmp/v2raya_import_payload.json ]]; then
    import_resp=$(curl -fsS --max-time 20 -X POST \
      -H "Authorization: $token" \
      -H 'Content-Type: application/json' \
      --data-binary @/tmp/v2raya_import_payload.json \
      "$BASE_URL/api/import")
    import_code=$(printf '%s' "$import_resp" | jq -r '.code // empty')
    if [[ "$import_code" != "SUCCESS" ]]; then
      printf 'Failed to sync current Shadowsocks node from v2rayN config: %s\n' "$import_resp" >&2
      exit 1
    fi
    printf 'Synced current Shadowsocks node from v2rayN config.\n'
  fi
fi

setting_resp=$(curl -fsS --max-time 8 -H "Authorization: $token" "$BASE_URL/api/setting")
printf '%s' "$setting_resp" \
  | jq '.data.setting
      | .transparent="whitelist"
      | .transparentType="tproxy"
      | .ipforward=true
      | .routeOnly=false' \
  > /tmp/v2raya-setting-tproxy.json

curl -fsS --max-time 15 -X PUT \
  -H "Authorization: $token" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/v2raya-setting-tproxy.json \
  "$BASE_URL/api/setting" >/dev/null

curl -fsS --max-time 20 -X POST -H "Authorization: $token" "$BASE_URL/api/v2ray" >/dev/null

gsettings set org.gnome.system.proxy mode 'none'

sleep 3

status=$(curl -fsS --max-time 8 -H "Authorization: $token" "$BASE_URL/api/touch")
running=$(printf '%s' "$status" | jq -r '.data.running')
network_paused=$(printf '%s' "$status" | jq -r '.data.networkPaused')
proxy_mode=$(gsettings get org.gnome.system.proxy mode)

printf 'v2rayA running: %s\n' "$running"
printf 'networkPaused: %s\n' "$network_paused"
printf 'GNOME proxy mode: %s\n' "$proxy_mode"

if [[ "$running" != "true" || "$network_paused" == "true" ]]; then
  echo "v2rayA core did not enter a usable running state." >&2
  exit 1
fi

require_proxy_url() {
  local name="$1"
  local url="$2"

  if curl -x http://127.0.0.1:20171 -4 -fsSI --max-time 12 "$url" >/dev/null; then
    printf '%s test: OK\n' "$name"
  else
    printf '%s test: FAIL, v2rayA HTTP proxy cannot reach this URL. The selected node is probably stale or unusable.\n' "$name" >&2
    exit 1
  fi
}

check_url() {
  local name="$1"
  local url="$2"

  if curl --noproxy '*' -4 -fsSI --max-time 10 "$url" >/dev/null; then
    printf '%s test: OK\n' "$name"
  else
    printf '%s test: WARN, v2rayA is running but this connectivity check failed.\n' "$name" >&2
  fi
}

require_proxy_url "v2rayA HTTP proxy Google" "https://www.google.com"
check_url "Google tproxy" "https://www.google.com"
check_url "Baidu tproxy" "https://www.baidu.com"
check_url "Antigravity apt repo tproxy" "https://us-central1-apt.pkg.dev/projects/antigravity-auto-updater-dev/dists/antigravity-debian/InRelease"

printf 'Done. v2rayA is configured for tproxy.\n'
