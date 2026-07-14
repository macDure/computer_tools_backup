#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${V2RAYA_BASE_URL:-http://127.0.0.1:2017}"
USER_NAME="${V2RAYA_USER:-macp}"
PASSWORD="${V2RAYA_PASS:-mac6833773}"
CRED_FILE="${V2RAYA_CRED_FILE:-/home/mac/v2raya-tproxy-kit/credentials/v2raya-web-credentials.txt}"
SUB_URL="${1:-}"

if [[ -z "$SUB_URL" && ! -t 0 ]]; then
  SUB_URL="$(cat | tr -d '\r\n')"
fi

if [[ -z "$SUB_URL" ]]; then
  echo "Usage:" >&2
  echo "  $0 'https://your-subscription-url'" >&2
  echo "  cat sub-url.txt | $0" >&2
  exit 1
fi

if [[ -r "$CRED_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CRED_FILE"
  USER_NAME="${username:-$USER_NAME}"
  PASSWORD="${password:-$PASSWORD}"
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 1; }
}

need_cmd curl
need_cmd jq
need_cmd systemctl

if ! systemctl is-active --quiet v2raya.service; then
  sudo systemctl enable --now v2raya.service >/dev/null
fi

payload=$(jq -n --arg username "$USER_NAME" --arg password "$PASSWORD" '{username:$username,password:$password}')
login_resp=$(curl -fsS --max-time 8 -H 'Content-Type: application/json' -d "$payload" "$BASE_URL/api/login")
token=$(printf '%s' "$login_resp" | jq -r '.data.token // empty')

if [[ -z "$token" || "$token" == "null" ]]; then
  echo "Failed to log in to v2rayA API." >&2
  exit 1
fi

import_payload=$(jq -n --arg url "$SUB_URL" '{url:$url}')
import_resp=$(curl -fsS --max-time 60 -X POST \
  -H "Authorization: $token" \
  -H 'Content-Type: application/json' \
  -d "$import_payload" \
  "$BASE_URL/api/import")

code=$(printf '%s' "$import_resp" | jq -r '.code')
message=$(printf '%s' "$import_resp" | jq -r '.message // empty')
if [[ "$code" != "SUCCESS" ]]; then
  echo "Import failed: $message" >&2
  printf '%s\n' "$import_resp" >&2
  exit 1
fi

touch_resp=$(curl -fsS --max-time 8 -H "Authorization: $token" "$BASE_URL/api/touch")
servers=$(printf '%s' "$touch_resp" | jq -r '.data.touch.servers | length')
subs=$(printf '%s' "$touch_resp" | jq -r '.data.touch.subscriptions | length')

printf 'Subscription import: OK\n'
printf 'Subscriptions: %s\n' "$subs"
printf 'Standalone servers: %s\n' "$servers"
