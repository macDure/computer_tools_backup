# Ubuntu 使用 RTL8812BU/RTL8822BU 网卡创建 5GHz AP

本文档使用 Ubuntu 的 NetworkManager 共享网络功能，把本机有线网络通过 RTL8812BU/RTL8822BU USB 无线网卡共享成 5GHz Wi-Fi 热点。

本文档只配置 5GHz AP、DHCP、DNS 和 NAT，不配置 v2rayN、v2rayA 或其他代理。

## 一、最终网络结构

~~~text
有线网卡（例如 enp8s0）
        │
        │  本机上游网络
        ▼
NetworkManager shared
        │
        ├── DHCP/DNS：NetworkManager 启动 dnsmasq
        ├── NAT：把无线客户端流量转发到有线网卡
        └── 5GHz AP：RTL8812BU/RTL8822BU
                    │
                    └── 手机、平板、电脑等客户端
~~~

无线客户端默认处于独立子网，不会和有线网处于同一个二层网段。它们可以通过本机有线网络访问互联网。

本机示例使用：

- Wi-Fi 接口：wlxe0e1a918da4f
- 热点 SSID：Mac-5G-AP
- 热点密码：Mac123456
- 5GHz 信道：36
- AP 信道宽度：20MHz
- 无线网关：10.42.0.1
- DHCP 地址范围：10.42.0.10 到 10.42.0.254

为了让其他电脑配置出与本机相同的热点，SSID 和密码都保持上面的值。本文档现在包含 Wi-Fi 密码，请注意备份文件的访问权限。

本机已启用 NetworkManager 自动连接：开机时或插入匹配的无线网卡后，会自动启动 Mac-5G-AP。

## 二、准备条件

### 1. 确认无线网卡型号和 USB ID

插入无线网卡后执行：

~~~bash
lsusb
~~~

本目录驱动支持的常见 ID 包括：

~~~text
0bda:b812
0bda:b81a
0bda:b82c
~~~

完整列表见本目录的 supported-device-IDs。

### 2. 安装或确认驱动

如果驱动尚未安装，在包含 install-driver.sh 的目录执行：

~~~bash
sudo sh ./install-driver.sh NoPrompt
sudo depmod -a
sudo modprobe 88x2bu
~~~

确认驱动已经绑定：

~~~bash
for d in /sys/class/net/wlx*; do
    [ -e "$d" ] || continue
    printf '%s -> ' "$(basename "$d")"
    readlink -f "$d/device/driver"
done
~~~

输出中应包含：

~~~text
/sys/bus/usb/drivers/rtl88x2bu
~~~

### 3. 确认网卡支持 AP 和 5GHz

~~~bash
iw dev
iw list | sed -n '/Supported interface modes:/,/Band 1:/p'
iw list | sed -n '/Band 2:/,/Band 3:/p'
~~~

在 Supported interface modes 中应看到：

~~~text
* AP
~~~

5GHz 频段通常在 Band 2 中。应能看到 5180 MHz/信道 36 等频率。

### 4. 安装 NetworkManager 共享功能依赖

~~~bash
sudo apt update
sudo apt install -y network-manager dnsmasq-base iw rfkill
~~~

hostapd 不是本方案的必需组件。NetworkManager 会在启用 ipv4.method shared 时启动自己的 dnsmasq 实例，提供 DHCP、DNS 和 NAT。

确认 NetworkManager 正在运行：

~~~bash
systemctl is-active NetworkManager
nmcli general status
~~~

同时确认本机有线网卡已经联网：

~~~bash
nmcli device status
ip route
~~~

## 三、创建 5GHz 热点

先找出无线接口名：

~~~bash
nmcli device status
iw dev
~~~

下面把无线接口名替换成实际值。示例接口名是 wlxe0e1a918da4f。

~~~bash
IFACE="wlxe0e1a918da4f"
CON_NAME="Mac-5G-AP"
SSID="Mac-5G-AP"
AP_PASSWORD="Mac123456"
~~~

如果使用 nmcli connection add 创建新连接：

~~~bash
sudo nmcli connection add \
    type wifi \
    ifname "$IFACE" \
    con-name "$CON_NAME" \
    ssid "$SSID"
~~~

配置为 5GHz AP、WPA2-AES、共享有线网络：

~~~bash
sudo nmcli connection modify "$CON_NAME" \
    802-11-wireless.mode ap \
    802-11-wireless.band a \
    802-11-wireless.channel 36 \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.proto rsn \
    802-11-wireless-security.pairwise ccmp \
    802-11-wireless-security.group ccmp \
    802-11-wireless-security.psk "$AP_PASSWORD" \
    ipv4.method shared \
    ipv6.method disabled \
    connection.autoconnect yes
~~~

启动热点：

~~~bash
sudo nmcli connection up "$CON_NAME"
~~~

如果 NetworkManager 报告连接已存在，不要重复执行 connection add，直接执行上面的 connection modify 和 connection up 即可。

## 四、为什么使用 5GHz 信道 36

建议第一次使用非 DFS 信道：

- 36
- 40
- 44
- 48

信道 52 到 144 通常涉及 DFS 雷达检测。部分手机、电视、投影仪和物联网设备对 DFS 支持不完整，热点可能不可见或等待较长时间后才开始广播。

信道 149 到 165 是否可用取决于国家/地区监管域，不要脱离当地法规使用。

本机 Ubuntu 20.04 的 NetworkManager 1.22.10 不支持通过连接属性直接设置 channel-width。本机实际启动后的 AP 由 iw 报告为 20MHz：

~~~text
channel 36 (5180 MHz), width: 20 MHz
~~~

配置完成后必须用 iw dev <无线接口> info 检查实际信道宽度，不要只看连接配置文件。

## 五、验证热点是否正常

### 1. 检查 NetworkManager 状态

~~~bash
nmcli device status
nmcli connection show --active
~~~

无线设备应显示为 connected，连接名称应为热点连接名称。

### 2. 检查实际 AP 参数

~~~bash
iw dev "$IFACE" info
~~~

应看到类似：

~~~text
ssid Mac-5G-AP
type AP
channel 36 (5180 MHz), width: 20 MHz
~~~

### 3. 检查无线网关地址

~~~bash
ip -br addr show "$IFACE"
ip route
~~~

共享热点通常会使用：

~~~text
10.42.0.1/24
10.42.0.0/24 dev <无线接口>
~~~

### 4. 检查 NetworkManager 启动的 DHCP/DNS

~~~bash
pgrep -af dnsmasq
~~~

正常时可以看到监听 10.42.0.1、地址范围类似 10.42.0.10 到 10.42.0.254 的 dnsmasq 进程。

### 5. 检查 NAT

~~~bash
sudo iptables -t nat -S
~~~

正常时应有类似：

~~~text
-A POSTROUTING -s 10.42.0.0/24 ! -d 10.42.0.0/24 -j MASQUERADE
~~~

### 6. 让手机或其他设备连接

客户端连接 SSID 后，应该获得：

- IP：10.42.0.x
- 网关：10.42.0.1
- DNS：10.42.0.1

可以查看 DHCP 租约：

~~~bash
sudo cat /var/lib/NetworkManager/dnsmasq-<无线接口>.leases
~~~

## 六、启动、停止和自动检测

### 开机或插入网卡后自动启动

本机已将热点连接设置为自动连接。开机时或插入匹配的无线网卡后，NetworkManager 会自动检测接口并启动热点，通常不需要手动执行命令。

热点连接绑定到无线接口名 wlxe0e1a918da4f：

~~~text
connection.interface-name: wlxe0e1a918da4f
connection.autoconnect: yes
~~~

确认启动成功：

~~~bash
nmcli device status
iw dev wlxe0e1a918da4f info
~~~

应看到无线接口处于 connected/AP 状态，SSID 为 Mac-5G-AP。

### 自动启动失败时手动启动

如果插入网卡后没有自动启动，先确认 USB 网卡已经插入，再执行：

~~~bash
lsusb
iw dev
sudo modprobe 88x2bu
sudo nmcli connection up id Mac-5G-AP
~~~

启动：

~~~bash
sudo nmcli connection up "Mac-5G-AP"
~~~

停止：

~~~bash
sudo nmcli connection down "Mac-5G-AP"
~~~

查看连接：

~~~bash
nmcli connection show "Mac-5G-AP"
~~~

查看自动连接设置：

~~~bash
nmcli -f connection.id,connection.interface-name,connection.autoconnect connection show Mac-5G-AP
~~~

如果需要启用自动启动：

~~~bash
sudo nmcli connection modify Mac-5G-AP connection.autoconnect yes
~~~

如果需要改回手动启动：

~~~bash
sudo nmcli connection modify Mac-5G-AP connection.autoconnect no
~~~

## 七、常见问题

### 热点不可见

依次检查：

~~~bash
rfkill list
iw list | sed -n '/Supported interface modes:/,/Band 1:/p'
iw dev <无线接口> info
sudo nmcli connection up "Mac-5G-AP"
~~~

优先使用 5GHz 信道 36，并避免 DFS 信道。

### 手机能连接但没有 IP

检查 dnsmasq：

~~~bash
pgrep -af dnsmasq
sudo journalctl -u NetworkManager --no-pager -n 100
~~~

确认热点接口存在 10.42.0.1/24 地址，并确认没有其他程序占用 DHCP 端口。

### 手机获得 IP 但不能上网

检查本机有线网络和默认路由：

~~~bash
nmcli device status
ip route
sysctl net.ipv4.ip_forward
sudo iptables -t nat -S
~~~

上游有线网卡必须处于 connected 状态，并且本机必须有默认路由。

### Wi-Fi 速度低

无线速率不是固定值，会受信号强度、手机空间流数、信道宽度、调制方式和协议开销影响。

本驱动在 5GHz、80MHz、2x2、VHT MCS9 条件下报告的理论最高 PHY 速率是约 867Mbps；本机 AP 为 20MHz 时，2x2 理论 PHY 速率上限约为 173Mbps，实际 TCP/HTTP 吞吐会更低。

查看当前 AP 实际参数：

~~~bash
iw dev <无线接口> info
iw dev <无线接口> station dump
~~~

旧版 rtl88x2bu 驱动有时不会在 station dump 中显示客户端实时 TX/RX bitrate，此时只能确认信号和 AP 参数，不能从该命令得到手机的精确协商速率。

## 八、安全建议

- 使用 WPA2-AES，不使用开放热点、WEP、TKIP。
- 本机及本文档使用的 Wi-Fi 密码是 Mac123456；该密码长度较短，不建议用于不受信任的公共环境。
- 本文档包含 Wi-Fi 密码，不要把文件公开发布；如果需要公开分享文档，应先删除密码。
- 只使用当地法规允许的 5GHz 信道。
- 如果不希望插入网卡后自动广播，可将 connection.autoconnect 设置为 no。
- 本方案不包含 v2rayN 代理转发；如需代理共享，应另行设计透明代理或客户端代理配置。

## 九、本机验证记录

本机验证环境：

- Ubuntu 20.04.6 LTS
- 内核：5.4.0-216-generic
- NetworkManager：1.22.10
- 网卡驱动：rtl88x2bu
- 无线接口：wlxe0e1a918da4f
- USB ID：0bda:b812
- AP 信道：36
- AP 频段：5GHz
- AP 实际宽度：20MHz
- AP 网关：10.42.0.1

本机实际配置命令使用了：

~~~bash
sudo nmcli connection add type wifi \
    ifname wlxe0e1a918da4f \
    con-name Mac-5G-AP \
    ssid Mac-5G-AP

sudo nmcli connection modify Mac-5G-AP \
    802-11-wireless.mode ap \
    802-11-wireless.band a \
    802-11-wireless.channel 36 \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.proto rsn \
    802-11-wireless-security.pairwise ccmp \
    802-11-wireless-security.group ccmp \
    802-11-wireless-security.psk "Mac123456" \
    ipv4.method shared \
    ipv6.method disabled \
    connection.autoconnect yes

sudo nmcli connection up Mac-5G-AP
~~~

迁移到其他电脑时，只需要根据新电脑的实际无线接口名修改 IFACE 和 ifname；热点 SSID 使用 Mac-5G-AP，密码使用 Mac123456。
