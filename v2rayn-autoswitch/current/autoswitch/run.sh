#!/usr/bin/env bash
# cron 入口: 30 8 * * * /home/mac/v2rayN-linux-64/autoswitch/run.sh
# 用法: ./run.sh [--dry-run] [--no-restart]
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TZ=Asia/Shanghai
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"
mkdir -p "$DIR/logs"
exec 9>"$DIR/autoswitch.lock"
if ! flock -n 9; then
  echo "$(date '+%F %T') [WARN] 上一次运行尚未结束, 跳过本次" >> "$DIR/logs/auto-$(date +%Y%m%d).log"
  exit 75
fi
exec python3 "$DIR/autoswitch.py" "$@"
