#!/usr/bin/env bash
set -Eeuo pipefail

# Toggle only the saved Intel Mac-AP NetworkManager profile.
# This script does not stop or restart v2rayN/Xray or NetworkManager.
readonly CONNECTION="Mac-AP"
readonly IFACE="wlp0s20f3"
readonly EXPECTED_SSID="Mac-AP"
readonly IW_BIN="${HOME}/.local/bin/iw"

usage() {
    cat <<'EOF'
用法：mac-ap.sh on|off|status

  on      开启 Intel 网卡 2.4 GHz 热点，并恢复自动连接
  off     关闭 Mac-AP，并关闭该热点配置的自动连接
  status  查看热点连接状态
EOF
}

check_profile() {
    local actual
    if ! nmcli connection show "$CONNECTION" >/dev/null 2>&1; then
        echo "找不到 NetworkManager 配置：$CONNECTION" >&2
        exit 1
    fi

    actual="$(nmcli -g connection.interface-name connection show "$CONNECTION")"
    if [[ "$actual" != "$IFACE" ]]; then
        echo "安全检查失败：$CONNECTION 绑定到 '$actual'，预期为 '$IFACE'。未做更改。" >&2
        exit 1
    fi

    actual="$(nmcli -g 802-11-wireless.ssid connection show "$CONNECTION")"
    if [[ "$actual" != "$EXPECTED_SSID" ]]; then
        echo "安全检查失败：$CONNECTION 的 SSID 为 '$actual'，预期为 '$EXPECTED_SSID'。未做更改。" >&2
        exit 1
    fi

    actual="$(nmcli -g 802-11-wireless.mode connection show "$CONNECTION")"
    if [[ "$actual" != "ap" ]]; then
        echo "安全检查失败：$CONNECTION 不是 AP 配置。未做更改。" >&2
        exit 1
    fi
}

show_status() {
    echo "热点配置：$CONNECTION（$EXPECTED_SSID，接口 $IFACE）"
    nmcli -f GENERAL.DEVICE,GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS device show "$IFACE"
    if [[ -x "$IW_BIN" ]]; then
        "$IW_BIN" dev "$IFACE" info 2>/dev/null \
            | grep -E '^(Interface |[[:space:]]*type |[[:space:]]*channel )' || true
    fi
}

case "${1:-}" in
    on)
        check_profile
        nmcli radio wifi on
        nmcli connection modify "$CONNECTION" connection.autoconnect yes
        nmcli connection up id "$CONNECTION" ifname "$IFACE"
        echo "Mac-AP 已开启。"
        show_status
        ;;
    off)
        check_profile
        nmcli connection modify "$CONNECTION" connection.autoconnect no
        if nmcli -t -f NAME connection show --active | grep -Fqx "$CONNECTION"; then
            nmcli connection down id "$CONNECTION"
        fi
        echo "Mac-AP 已关闭；该热点不会自行重新连接。无线电开关和其他网络配置保持原样。"
        ;;
    status)
        show_status
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
