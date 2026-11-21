# 本机 Wi-Fi 热点配置记录

配置时间：2026-11-21。目录中的 [5 GHz AP 方案](INSTALL-5GHZ-AP-NETWORKMANAGER.md) 使用 NetworkManager 的 `ipv4.method shared`，由 NetworkManager 创建热点、DHCP、DNS 和 NAT。

**部署优先级：优先建立并验证 5 GHz 热点。** 首选信道 36 等符合当地监管要求的非 DFS 信道；5 GHz 因网卡、驱动、监管域或终端兼容性确实不可用时才回退到 2.4 GHz，并向用户说明实际频段。

**当前状态（2026-11-22）：内置 Intel 网卡提供 2.4 GHz 热点。** 接口为 `wlp0s20f3`，SSID `Mac-AP`，信道 6；有线 `enp0s31f6` 为上游。热点已由 `mac-ap.sh on` 启动，NetworkManager 报告 `connected`，实际频率 2437 MHz。手机上次重新连接后的上网结果由用户于 2026-11-21 确认。NetworkManager 的 `Mac-AP` 自动连接已启用。

此前 88x2bu USB 网卡曾成功建立 5 GHz 热点：USB ID `0bda:b812`，接口 `wlxe0e1a918da4f`，信道 36（5180 MHz，实际带宽 20 MHz），用户确认手机能上网。对应 `Mac-AP-5G-USB` 配置仍保留，但自动连接已关闭，以免抢占当前 Intel 热点。

此前 USB 网卡尚未接入时，内置 Intel `iwlwifi` 网卡 `wlp0s20f3` 虽报告支持 AP 和 5 GHz，但实际查询发现其全部 5 GHz 信道标记为 `no IR`。尝试信道 36 时 wpa_supplicant 报 `Failed to start AP functionality`，NetworkManager 激活超时；当时临时恢复到 2.4 GHz 信道 6。该限制只针对当时的 Intel PHY，不能套用到 USB 网卡。

## 5 GHz 深入排查与 USB 方案

本机内置芯片由内核日志识别为 **Intel Wi-Fi 7 BE201 320MHz**（PCI `8086:7740`，子设备 `8086:00e4`），使用 `iwlwifi` / `iwlmld`，固件为 `101.6e695a70.0 bz-b0-fm-c0-c101.ucode`。它可以作为客户端连接 5 GHz Wi-Fi；当前阻碍的是本机驱动/固件对主动创建 5 GHz AP 的限制，不能据此说硬件不支持 5 GHz。

实测 `iw reg get` 显示该 PHY 是 `self-managed`，自身监管域为 `CN`；`iw phy phy0 info` 中 36–48 和 149–165 信道均为 `no IR`，DFS 信道也标记了 `no IR`。不只是系统全局 `country 00` 的显示问题。Linux 内核说明 `NO_IR` 包括不允许主动发送 beacon，普通 AP 正需要 beacon；Intel 无线驱动的监管约束也不能简单靠用户设定国家码保证消除。参见 [Linux cfg80211 信道标记](https://github.com/torvalds/linux/blob/master/include/net/cfg80211.h) 和 [Linux Wireless FAQ](https://wireless.docs.kernel.org/en/latest/en/users/documentation/faq.html)。

驱动报告可在同一个物理信道上组合 STA 和 AP，监管域也显示 `IR-CONCURRENT`；但本机 `/boot/config-7.0.0-34-generic` 中 `CONFIG_CFG80211_CERTIFICATION_ONUS` 未开启，内核文档所述的相关 `NO_IR` 放宽依赖相应内核配置和驱动支持，并针对特定条件下的 P2P GO。不能将这一标记直接当作本机普通 5 GHz 热点可行的证据。参见 [Linux Wireless 监管规则](https://wireless.docs.kernel.org/en/latest/en/developers/regulatory/processing_rules.html)。

接入支持 5 GHz AP 的 88x2bu USB 网卡后，已完成：

1. 当前 `7.0.0-34-generic` 内核的 `rtl88x2bu/5.13.1` DKMS 模块已安装且加载。`0bda:b812` 已绑定 `rtl88x2bu`，USB PHY 的 5180 MHz 未标记 `no IR`，5 GHz AP 曾实际启动并通过手机上网验证。
2. NetworkManager 配置 `Mac-AP-5G-USB` 保留并绑定接口 `wlxe0e1a918da4f`，SSID 为 `Mac-AP`，优先信道 36；按用户要求切回 Intel 热点后已关闭 USB 配置的自动连接。
3. 已将 `iw` 6.7 的用户版放在 `$HOME/.local/bin/iw`；这是用户目录中的可执行文件，不是系统 dpkg 安装。管理员安装没有获得认证。

如果更换 USB 网卡，先识别设备、绑定的驱动和 PHY，并检查信道 36 是否允许主动发射：

```bash
lsusb
nmcli device status
readlink -f /sys/class/net/<USB接口>/device/driver
"$HOME/.local/bin/iw" dev
"$HOME/.local/bin/iw" phy <USB的PHY> info
```

只有确认 USB 驱动绑定正确、AP 模式存在且 5180 MHz 不受 `no IR` / `disabled` 限制后，才切换热点。以下命令中 `<USB接口>` 和 `<USB的PHY>` 是占位符，需替换后执行：

```bash
nmcli connection down id Mac-AP
nmcli connection up id Mac-AP-5G-USB ifname <USB接口>
"$HOME/.local/bin/iw" dev <USB接口> info
```

如 USB 5 GHz 启动失败，恢复 `nmcli connection up id Mac-AP ifname wlp0s20f3`。成功后应实际用手机重连、确认 DHCP 地址、DNS 和互联网可达，并复核代理和有线上游；配置存在不等于 5 GHz 成功。切换时客户端会短暂断连。当前不建议直接使用针对其他芯片或其他内核版本的补丁清除监管标记：该方法尚未证明适用于本机 BE201 / `iwlmld`，且不能保证固件正常运行。

| 项目 | 配置 |
| --- | --- |
| NetworkManager 连接名 / SSID | `Mac-AP` / `Mac-AP` |
| 网卡 / 频段 | `wlp0s20f3` / 2.4 GHz 信道 6（2437 MHz、20 MHz） |
| 加密 | WPA2-PSK / AES-CCMP |
| 网段 / 网关 | `10.42.0.0/24` / `10.42.0.1` |
| DHCP | `10.42.0.10` 至 `10.42.0.254` |
| 启动方式 | Intel 热点配置自动连接；需无线电开关开启。USB 5 GHz 配置自动连接关闭 |
| 密码文件 | `/home/mac/.local/state/mac-wifi-ap/credentials`，权限 0600；密码不写入仓库 |

切回后已验证 Intel 热点为 `connected`、无线模式 `AP`、实际频率 2437 MHz、共享地址 `10.42.0.1/24`；手机重新连接后，用户确认能上网。USB 5 GHz 热点此前也已验证手机可上网。两种模式的 DNS、NAT 与转发由 NetworkManager 共享功能提供，xray 原进程保持运行。手机实际互联网吞吐尚未测量。

有线网卡当前协商速率为 100 Mb/s；一次直接下载 10 MB 的上游单连接测试约为 6.37 Mb/s。后者只代表当时对该测试端点的平均速度，不代表 2.4 GHz Wi-Fi 链路速率，也不保证其他时段的速度。

查看本机保存的热点名称和密码：

```bash
cat "$HOME/.local/state/mac-wifi-ap/credentials"
```

快速开关：脚本 `mac-ap.sh` 已链接到 `/usr/local/bin/mac-ap`，该目录在本机终端 PATH 中；新开终端后可在任意目录执行：

```bash
mac-ap on
mac-ap off
mac-ap status
```

NetworkManager 需要授权时会按系统配置提示认证；脚本只操作内置 Intel 网卡上的 `Mac-AP` 配置。关闭时会禁用此配置的自动连接，但不关闭整机 Wi-Fi 无线电，也不影响 USB 网卡配置；再次开启会恢复热点自动连接。脚本不操作 v2rayN / Xray。

也可以直接使用 NetworkManager 命令：

```bash
nmcli connection up id Mac-AP ifname wlp0s20f3
nmcli connection down id Mac-AP
```

状态检查：

```bash
nmcli -f GENERAL.DEVICE,GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS device show wlp0s20f3
"$HOME/.local/bin/iw" dev wlp0s20f3 info
ip -4 route show default
sudo cat /var/lib/NetworkManager/dnsmasq-wlp0s20f3.leases
```

若无线被关闭，先执行 `nmcli radio wifi on`。本热点使用普通网络转发；本机监听在 `127.0.0.1:10808` 的 v2rayN 代理不会自动对热点客户端共享。TrustAccess VPN 内网访问也需另行验证。
