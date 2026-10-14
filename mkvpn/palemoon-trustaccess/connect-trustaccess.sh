#!/bin/sh
set -eu

BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROFILE="$BASE/profile"
BROWSER="$BASE/palemoon/palemoon"
GATEWAY=111.202.232.70
LOGIN_URL="https://$GATEWAY:1443/"

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

if ! ip route get "$GATEWAY" >/dev/null 2>&1; then
    notify_error '当前没有可用的普通网络，请先连接 Wi-Fi、网线或手机热点。'
    exit 1
fi

if pgrep -x palemoon >/dev/null 2>&1 || pgrep -x palemoon-bin >/dev/null 2>&1; then
    notify_error 'Pale Moon 已经在运行，请使用已有窗口；如果登录页已退出，关闭该窗口后再次点击桌面图标。'
    exit 0
fi

if [ -e "$PROFILE/lock" ] || [ -e "$PROFILE/.parentlock" ]; then
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

if ipsec_running && ! vpn_ip_present; then
    if ! command -v pkexec >/dev/null 2>&1; then
        notify_error '需要 pkexec 清理旧 IPsec 状态，但当前系统没有 pkexec。'
        exit 1
    fi
    if ! pkexec /etc/init.d/secvpnd stop; then
        notify_error '停止旧 TrustAccess 状态失败，请在终端执行文档中的清理命令。'
        exit 1
    fi
    pkexec /usr/bin/killall -TERM pluto _plutorun _plutoload >/dev/null 2>&1 || true
    sleep 2
fi

if ! pgrep -x secvpnMonitord >/dev/null 2>&1; then
    if ! command -v pkexec >/dev/null 2>&1; then
        notify_error 'TrustAccess 后台未运行，且当前系统没有 pkexec。'
        exit 1
    fi
    if ! pkexec /etc/init.d/secvpnd start; then
        notify_error '启动 TrustAccess 后台服务失败。'
        exit 1
    fi
fi

exec "$BROWSER" -no-remote -profile "$PROFILE" -new-window "$LOGIN_URL"
