#!/bin/sh
set -eu

BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CONNECT="$BASE/connect-trustaccess.sh"

if [ ! -x "$CONNECT" ]; then
    printf '%s\n' "找不到连接脚本: $CONNECT" >&2
    exit 1
fi

if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR=$(xdg-user-dir DESKTOP)
else
    DESKTOP_DIR="$HOME/Desktop"
fi

APP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR" "$APP_DIR"

write_entry() {
    TARGET=$1
    TMP="$TARGET.tmp.$$"
    printf '%s\n' \
        '[Desktop Entry]' \
        'Type=Application' \
        'Name=TrustAccess VPN Login' \
        'Comment=Start TrustAccess and open the VPN login page' \
        "Exec=\"$CONNECT\"" \
        "Path=$BASE" \
        'Terminal=false' \
        'Icon=web-browser' \
        'Categories=Network;' \
        'StartupNotify=true' \
        'Actions=Reconnect;Check;' \
        '' \
        '[Desktop Action Reconnect]' \
        'Name=换网后重连（关闭 VPN 登录窗口）' \
        "Exec=\"$CONNECT\" --reconnect" \
        '' \
        '[Desktop Action Check]' \
        'Name=检查 VPN 连通性' \
        "Exec=gnome-terminal -- \"$CONNECT\" --check --samples 2 --interval 5 --pause" > "$TMP"
    mv "$TMP" "$TARGET"
    chmod +x "$TARGET"
    if command -v gio >/dev/null 2>&1; then
        gio set "$TARGET" metadata::trusted true >/dev/null 2>&1 || true
    fi
}

write_entry "$DESKTOP_DIR/TrustAccess-VPN.desktop"
write_entry "$APP_DIR/TrustAccess-VPN.desktop"
printf '%s\n' "桌面快捷方式已安装: $DESKTOP_DIR/TrustAccess-VPN.desktop"
