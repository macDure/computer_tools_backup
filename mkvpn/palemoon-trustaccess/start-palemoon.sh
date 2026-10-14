#!/bin/sh
set -eu

BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROFILE="$BASE/profile"
BROWSER="$BASE/palemoon/palemoon"

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo '请在本地图形桌面会话中运行此脚本。'
    exit 1
fi

# DISPLAY may still point at GDM's login screen after the desktop session ended.
if command -v loginctl >/dev/null 2>&1 && [ -n "${XDG_SESSION_ID:-}" ]; then
    SESSION_ACTIVE=$(loginctl show-session "$XDG_SESSION_ID" -p Active --value 2>/dev/null || true)
    SESSION_TYPE=$(loginctl show-session "$XDG_SESSION_ID" -p Type --value 2>/dev/null || true)
    if [ "$SESSION_ACTIVE" != yes ] || [ "$SESSION_TYPE" = tty ]; then
        echo '当前不是活动的图形桌面会话，请先在本机登录 Ubuntu 桌面后再启动 Pale Moon。' >&2
        exit 1
    fi
fi

if [ ! -x "$BROWSER" ]; then
    echo "找不到可执行文件: $BROWSER" >&2
    exit 1
fi

if pgrep -x palemoon >/dev/null 2>&1 || pgrep -x palemoon-bin >/dev/null 2>&1; then
    echo 'Pale Moon 已经在运行，请使用已有窗口。'
    exit 0
fi

# 如果没有运行中的 Pale Moon 进程，自动清理旧崩溃/非正常退出留下的锁文件
if [ -e "$PROFILE/lock" ] || [ -e "$PROFILE/.parentlock" ]; then
    rm -f "$PROFILE/lock" "$PROFILE/.parentlock"
fi

# 检查并尝试拉起底层守护进程
if ! pgrep -x secvpnMonitord >/dev/null 2>&1; then
    if [ -x /usr/bin/pkexec ]; then
        pkexec /etc/init.d/secvpnd start >/dev/null 2>&1 || true
    fi
fi

if [ "$#" -eq 0 ]; then
    set -- 'https://111.202.232.70:1443/'
fi

exec "$BROWSER" -no-remote -profile "$PROFILE" -new-window "$@"
