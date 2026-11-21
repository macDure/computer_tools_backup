#!/bin/sh
set -eu

BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROFILE="$BASE/profile"
BROWSER="$BASE/palemoon/palemoon"
GATEWAY=111.202.232.70
LOGIN_URL="https://$GATEWAY:1443/"
RECONNECT=0
case "${1:-}" in
    --check) shift; exec python3 "$BASE/check-trustaccess.py" "$@" ;;
    --reconnect) RECONNECT=1; shift ;;
    '') ;;
    *) printf '%s\n' '用法: connect-trustaccess.sh [--check | --reconnect]' >&2; exit 2 ;;
esac
[ "$#" -eq 0 ] || exit 2

notify_error() {
    MESSAGE=$1
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -u critical 'TrustAccess VPN' "$MESSAGE" >/dev/null 2>&1 || true
    fi
    printf '%s\n' "$MESSAGE" >&2
}

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    notify_error '请先在本机登录 Ubuntu 图形桌面。'
    exit 1
fi

if command -v loginctl >/dev/null 2>&1 && [ -n "${XDG_SESSION_ID:-}" ]; then
    SESSION_ACTIVE=$(loginctl show-session "$XDG_SESSION_ID" -p Active --value 2>/dev/null || true)
    SESSION_TYPE=$(loginctl show-session "$XDG_SESSION_ID" -p Type --value 2>/dev/null || true)
    if [ "$SESSION_ACTIVE" != yes ] || [ "$SESSION_TYPE" = tty ]; then
        notify_error '当前不是活动的图形桌面会话，请先在本机登录 Ubuntu 桌面。'
        exit 1
    fi
fi

if [ ! -x "$BROWSER" ]; then
    notify_error "找不到 Pale Moon: $BROWSER"
    exit 1
fi

if [ ! -x /etc/init.d/secvpnd ] || [ ! -r /usr/lib/mozilla/plugins/libnpSecClientAssist.so ]; then
    notify_error 'TrustAccess 服务或 NPAPI 插件未安装，请先安装 linuxclient 中的 deb。'
    exit 1
fi

if ! ip route get "$GATEWAY" >/dev/null 2>&1; then
    notify_error '当前没有可用的普通网络，请先连接 Wi-Fi、网线或手机热点。'
    exit 1
fi

# Only close this user's VPN profile when recovery is explicitly requested.
if [ "$RECONNECT" -eq 1 ]; then
    python3 - "$PROFILE" <<'PY'
import os, signal, sys, time
from pathlib import Path
profile = Path(sys.argv[1]).resolve()
pids = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        if proc.stat().st_uid != os.getuid():
            continue
        args = (proc / 'cmdline').read_bytes().split(b'\0')
        if Path(os.fsdecode(args[0])).name not in ('palemoon', 'palemoon-bin'):
            continue
        if b'-profile' not in args:
            continue
        pos = args.index(b'-profile') + 1
        if Path(os.fsdecode(args[pos])).resolve() == profile:
            os.kill(int(proc.name), signal.SIGTERM)
            pids.append(proc)
    except (OSError, IndexError):
        continue
for _ in range(50):
    if not any(p.exists() for p in pids):
        break
    time.sleep(0.2)
else:
    sys.exit('VPN 浏览器尚未退出，请手动关闭后重试。')
PY
fi

if pgrep -u "$(id -u)" -x palemoon >/dev/null 2>&1 || pgrep -u "$(id -u)" -x palemoon-bin >/dev/null 2>&1; then
    notify_error 'Pale Moon 已经在运行，请使用已有窗口；如果登录页已退出，关闭该窗口后再次点击桌面图标。'
    exit 0
fi

# Serialize double clicks before changing backend or profile state.
umask 077
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/mkvpn"
mkdir -p "$STATE_DIR"
exec 9>"$STATE_DIR/launch.lock"
if ! flock -n 9; then
    notify_error 'VPN 登录程序正在启动，请稍候。'
    exit 0
fi

if [ -e "$PROFILE/lock" ] || [ -L "$PROFILE/lock" ] || [ -e "$PROFILE/.parentlock" ]; then
    rm -f "$PROFILE/lock" "$PROFILE/.parentlock"
fi

vpn_ip_present() {
    ip -4 -o addr show 2>/dev/null |
        awk '$4 ~ /^172\.20\.70\./ { found=1 } END { exit(found ? 0 : 1) }'
}

ipsec_running() {
    pgrep -x pluto >/dev/null 2>&1 ||
        pgrep -x _plutorun >/dev/null 2>&1 ||
        pgrep -x _plutoload >/dev/null 2>&1
}

stale_source() {
    CURRENT_SOURCE=$(ip -4 route get "$GATEWAY" | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1);exit}}')
    [ -n "$CURRENT_SOURCE" ] || return 1
    awk -F= -v current="$CURRENT_SOURCE" '
        /^[[:space:]]*left[[:space:]]*=/ {
            gsub(/[[:space:]]/, "", $2)
            if ($2 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && $2 != current) stale=1
        } END {exit(stale ? 0 : 1)}' /etc/ipsec.conf 2>/dev/null
}

# A tunnel address can survive a network change; also compare its old source.
if [ "$RECONNECT" -eq 1 ] || { ipsec_running && { ! vpn_ip_present || stale_source; }; }; then
    if ! command -v pkexec >/dev/null 2>&1; then
        notify_error '需要 pkexec 清理旧 IPsec 状态，但当前系统没有 pkexec。'
        exit 1
    fi
    # Fixed commands only. Do not call "secvpn setup stop": it flushes global XFRM.
    # Refuse to stop a foreign pluto implementation on a multi-VPN machine.
    if ! pkexec /bin/sh -c '
        for pid in $(pgrep -x pluto); do
            case "$(readlink -f "/proc/$pid/exe")" in
                /usr/local/trustaccess/*) ;;
                *) echo "检测到非 TrustAccess 的 pluto，停止自动清理。" >&2; exit 1 ;;
            esac
        done
        /etc/init.d/secvpnd stop || exit 1
        /usr/bin/pkill -TERM -f "^(/bin/sh )?/usr/local/trustaccess/(lib|libexec)/ipsec/_(plutorun|plutoload)( |$)" || true
        for pid in $(pgrep -x pluto); do
            case "$(readlink -f "/proc/$pid/exe")" in
                /usr/local/trustaccess/*) kill -TERM "$pid" ;;
            esac
        done
        sleep 2
    '; then
        notify_error '停止旧 TrustAccess 状态失败，请在终端执行文档中的清理命令。'
        exit 1
    fi
fi

if ! pgrep -x secvpnMonitord >/dev/null 2>&1; then
    if pgrep -x secvpnServerd >/dev/null 2>&1; then
        notify_error 'TrustAccess 只剩部分后台进程，请使用“换网后重连”清理后再启动。'
        exit 1
    fi
    if ! command -v pkexec >/dev/null 2>&1; then
        notify_error 'TrustAccess 后台未运行，且当前系统没有 pkexec。'
        exit 1
    fi
    if ! pkexec /etc/init.d/secvpnd start; then
        notify_error '启动 TrustAccess 后台服务失败。'
        exit 1
    fi
fi

for WAIT_STEP in 1 2 3 4 5; do
    if pgrep -x secvpnServerd >/dev/null 2>&1 && [ -S /var/run/secvpn/secvpn.fox ]; then
        break
    fi
    sleep 1
done
if ! pgrep -x secvpnServerd >/dev/null 2>&1 || [ ! -S /var/run/secvpn/secvpn.fox ]; then
    notify_error 'TrustAccess 后台不完整，请使用桌面图标的“换网后重连”操作。'
    exit 1
fi

# Keep errors outside the Git backup, with private permissions.
exec "$BROWSER" -no-remote -profile "$PROFILE" -new-window "$LOGIN_URL" >>"$STATE_DIR/browser.log" 2>&1
