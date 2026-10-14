#!/bin/bash
set -e

echo "================================================================="
echo "    开始完全卸载深信服 aTrust 与 EasyConnect 客户端及其所有残留    "
echo "================================================================="

# 检查 root 权限
if [ "$(id -u)" -ne 0 ]; then
    echo "错误：此脚本必须使用 root 权限执行！" >&2
    echo "请使用: sudo bash $0" >&2
    exit 1
fi

echo "[1/7] 停止所有相关的 systemd 服务与后台进程..."
# aTrust 服务
systemctl stop aTrustDaemon.service 2>/dev/null || true
systemctl disable aTrustDaemon.service 2>/dev/null || true
systemctl stop aTrustShell.service 2>/dev/null || true
systemctl disable aTrustShell.service 2>/dev/null || true
systemctl stop aTrustTray@*.service 2>/dev/null || true
systemctl disable aTrustTray@*.service 2>/dev/null || true

# EasyConnect 服务
systemctl stop EasyMonitor.service 2>/dev/null || true
systemctl disable EasyMonitor.service 2>/dev/null || true
service EasyMonitor.sh stop 2>/dev/null || true
update-rc.d -f EasyMonitor.sh remove 2>/dev/null || true
rm -f /etc/init.d/EasyMonitor.sh /etc/init/EasyMonitor.conf 2>/dev/null || true

# 彻底终止所有相关进程
echo "终止残留进程..."
killall -9 aTrustAgent aTrustXtunnel-64 aTrustTray aTrustTray2 aTrustDiagnosisTool 2>/dev/null || true
killall -9 EasyMonitor ECAgent EasyConnect CSClient svpnservice 2>/dev/null || true
sleep 1

echo "[2/7] 使用 dpkg/apt 彻底清除 (purge) 软件包..."
# 卸载 aTrust
if dpkg -s cn.com.sangfor.atrust >/dev/null 2>&1; then
    echo "正在 purge cn.com.sangfor.atrust..."
    dpkg --purge cn.com.sangfor.atrust || apt-get purge -y cn.com.sangfor.atrust || true
else
    echo "软件包 cn.com.sangfor.atrust 未安装或已清除。"
fi

# 卸载 EasyConnect
if dpkg -s easyconnect >/dev/null 2>&1; then
    echo "正在 purge easyconnect..."
    dpkg --purge easyconnect || apt-get purge -y easyconnect || true
else
    echo "软件包 easyconnect 未安装或已清除。"
fi

echo "[3/7] 清理系统级文件与目录..."
# 删除整个深信服共享安装目录
rm -rf /usr/share/sangfor

# 清理 systemd 服务单元残留文件
rm -f /usr/lib/systemd/system/aTrustDaemon.service \
      /usr/lib/systemd/system/aTrustShell.service \
      /usr/lib/systemd/system/aTrustTray@.service \
      /usr/lib/systemd/user/aTrustShell.service \
      /usr/lib/systemd/user/aTrustTray.service \
      /usr/lib/systemd/system/EasyMonitor.service \
      /etc/systemd/system/multi-user.target.wants/aTrustDaemon.service \
      /etc/systemd/system/multi-user.target.wants/EasyMonitor.service

# 清理桌面与自启动项
rm -f /etc/xdg/autostart/cn.com.sangfor.atrust.desktop
rm -f /usr/share/applications/cn.com.sangfor.atrust.desktop
rm -f /usr/share/applications/EasyConnect.desktop
rm -f /home/*/Desktop/cn.com.sangfor.atrust.desktop
rm -f /home/*/Desktop/EasyConnect.desktop

echo "[4/7] 清理用户与临时目录中的数据、日志与缓存..."
# 清理用户家目录
rm -rf /home/*/.aTrust
rm -rf /home/*/.config/EasyConnect
rm -rf /root/.aTrust
rm -rf /root/.config/EasyConnect

# 清理 /tmp 下的残留锁文件与临时目录
rm -rf /tmp/com.sangfor.* /tmp/.com.sangfor.* /tmp/sangfor.* /tmp/aTrustShell.* /tmp/sapp2_* /tmp/.org.chromium.Chromium.*

echo "[5/7] 清理防火墙 (iptables) 规则与虚拟网卡..."
# 清理 iptables 规则
iptables -t nat -F ATRUST_DNS 2>/dev/null || true
iptables -t nat -D OUTPUT -j ATRUST_DNS 2>/dev/null || true
iptables -t nat -X ATRUST_DNS 2>/dev/null || true

iptables -t filter -F ATRUST_BLOCK_DNS 2>/dev/null || true
iptables -t filter -D OUTPUT -j ATRUST_BLOCK_DNS 2>/dev/null || true
iptables -t filter -X ATRUST_BLOCK_DNS 2>/dev/null || true

ip6tables -t mangle -F ATRUST_DNS 2>/dev/null || true
ip6tables -t mangle -D OUTPUT -j ATRUST_DNS 2>/dev/null || true
ip6tables -t mangle -X ATRUST_DNS 2>/dev/null || true

ip6tables -t nat -F ATRUST_DNS 2>/dev/null || true
ip6tables -t nat -D OUTPUT -j ATRUST_DNS 2>/dev/null || true
ip6tables -t nat -X ATRUST_DNS 2>/dev/null || true

# 删除虚拟网卡 utun7
if ip link show utun7 >/dev/null 2>&1; then
    ip link delete utun7 2>/dev/null || true
    echo "虚拟网卡 utun7 已删除。"
fi

echo "[6/7] 清理 /etc/hosts 中深信服写入的配置条目..."
sed -i '/# This line is auto added by aTrustAgent/d' /etc/hosts
sed -i '/localhost\.sangfor\.com\.cn/d' /etc/hosts

echo "[7/7] 重载 systemd 守护进程..."
systemctl daemon-reload

echo "================================================================="
echo "    深信服 aTrust 与 EasyConnect 均已彻底完全卸载！              "
echo "================================================================="
