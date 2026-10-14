#!/usr/bin/env bash
# Install the portable v2rayN AutoSwitch bundle; do not copy runtime secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_USER="${TARGET_USER:-mac}"
TARGET_UID="${TARGET_UID:-1000}"
TARGET_GID="${TARGET_GID:-1000}"
V2RAYN_DIR="${V2RAYN_DIR:-/home/mac/v2rayN-linux-64}"
HERMES_HOME="${HERMES_HOME:-/home/mac/.hermes}"
RUNTIME_SCRIPT_DIR="${RUNTIME_SCRIPT_DIR:-/opt/data/scripts}"
AW_DIR="$V2RAYN_DIR/autoswitch"
HERMES_SCRIPT_DIR="$HERMES_HOME/scripts"

if [[ "$(id -u)" != 0 ]]; then
  echo "请使用 root 执行: sudo bash deployment/deploy.sh" >&2
  exit 2
fi
if ! [[ "$TARGET_UID" =~ ^[0-9]+$ && "$TARGET_GID" =~ ^[0-9]+$ ]]; then
  echo "TARGET_UID/TARGET_GID 必须是数字: $TARGET_UID/$TARGET_GID" >&2
  exit 2
fi
if [[ ! -d "$V2RAYN_DIR" ]]; then
  echo "v2rayN 目录不存在: $V2RAYN_DIR" >&2
  exit 2
fi

owner_args=(-o "$TARGET_UID" -g "$TARGET_GID")
install -d "${owner_args[@]}" "$AW_DIR" "$HERMES_SCRIPT_DIR" "$RUNTIME_SCRIPT_DIR" \
  "$HERMES_SCRIPT_DIR/shuimu_daily" "$RUNTIME_SCRIPT_DIR/shuimu_daily" \
  "$V2RAYN_DIR/autoswitch/logs" "$HERMES_HOME/state" "$HERMES_HOME/logs"

# Main tool: preserve a pre-existing target config; install a template beside it.
install "${owner_args[@]}" -m 0755 "$ROOT/current/autoswitch/autoswitch.py" "$AW_DIR/autoswitch.py"
install "${owner_args[@]}" -m 0755 "$ROOT/current/autoswitch/run.sh" "$AW_DIR/run.sh"
install "${owner_args[@]}" -m 0644 "$ROOT/current/autoswitch/DESIGN.md" "$AW_DIR/DESIGN.md"
install "${owner_args[@]}" -m 0644 "$ROOT/current/autoswitch/config.conf.example" "$AW_DIR/config.conf.example"
if [[ ! -e "$AW_DIR/config.conf" ]]; then
  install "${owner_args[@]}" -m 0644 "$ROOT/current/autoswitch/config.conf.example" "$AW_DIR/config.conf"
  echo "已生成 $AW_DIR/config.conf"
else
  echo "保留已有 $AW_DIR/config.conf"
fi

SCRIPT_FILES=(
  v2rayn_autoswitch.sh
  v2rayn_cn_route_fix.py
  v2rayn_gentle_mode_fix.py
  v2rayn_gentle_v2_fix.py
  v2rayn_mode_guard.py
  v2rayn_mode_guard.sh
  v2rayn_mode_guard_test.py
  v2rayn_owner.py
  v2rayn_parse_ss_fix.py
  v2rayn_proxy_guard.sh
  v2rayn_sub_notify.py
  v2rayn_sub_refresh.py
  v2rayn_sub_refresh_cron.sh
)
for name in "${SCRIPT_FILES[@]}"; do
  mode=0644
  [[ "$name" == *.sh || "$name" == *.py ]] && mode=0755
  install "${owner_args[@]}" -m "$mode" "$ROOT/current/scripts/$name" "$HERMES_SCRIPT_DIR/$name"
  install "${owner_args[@]}" -m "$mode" "$ROOT/current/scripts/$name" "$RUNTIME_SCRIPT_DIR/$name"
done

# Direct Feishu delivery is optional, but wrappers expect this path when enabled.
install "${owner_args[@]}" -m 0755 "$ROOT/current/scripts/shuimu_daily/deliver_feishu.py" \
  "$HERMES_SCRIPT_DIR/shuimu_daily/deliver_feishu.py"
install "${owner_args[@]}" -m 0755 "$ROOT/current/scripts/shuimu_daily/deliver_feishu.py" \
  "$RUNTIME_SCRIPT_DIR/shuimu_daily/deliver_feishu.py"

# Legacy tools are documentation/reference only and are not scheduled.
install -d "${owner_args[@]}" "$HERMES_SCRIPT_DIR/legacy" "$RUNTIME_SCRIPT_DIR/legacy"
for file in "$ROOT"/legacy/*; do
  [[ -f "$file" ]] || continue
  name="$(basename "$file")"
  install "${owner_args[@]}" -m 0644 "$file" "$HERMES_SCRIPT_DIR/legacy/$name"
  install "${owner_args[@]}" -m 0644 "$file" "$RUNTIME_SCRIPT_DIR/legacy/$name"
done

printf '%s\n' '源码安装完成。下一步：'
printf '%s\n' '1) 在 v2rayN GUI 中重新添加订阅并更新；'
printf '%s\n' '2) 执行 deployment/bootstrap_runner.sh；'
printf '%s\n' '3) 阅读 docs/CRON-JOBS.md 后创建 Hermes cron。'
