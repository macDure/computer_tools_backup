# TrustAccess VPN 实战排坑记录与完整解决方案备份

更新时间：2026-09-17  
适用系统：Ubuntu 20.04 LTS (x86_64) / Debian 系列

---

## 一、本次部署遇到的核心问题与解决方案

在本次全新部署和使用 TrustAccess VPN 的过程中，共排查出 **5 个关键技术陷阱**。如果不做针对性处理，会导致“无法加载插件”、“账号密码提交无效”、“挂机数小时后突然断连”或“SSH 连不上”等现象。

---

### 问题 1：多 VPN 冲突（深信服 aTrust 与 EasyConnect 干扰）

- **故障现象**：
  系统开机常驻深信服 aTrust（占用 1.3GB+ 内存）与 EasyConnect，创建了虚拟网卡 `utun7`，并在 `/etc/hosts` 与 `iptables` 中注入了 DNS 重定向链。同时开启多个企业级 VPN 会导致路由表错乱、DNS 劫持及 TUN/TAP 端口冲突。
- **排查手段**：
  `dpkg -l | grep -iE 'atrust|sangfor'`，检查 `ip addr` 是否存在 `utun` 接口。
- **解决方案**：
  彻底完全清除（Purge）深信服全部组件，恢复纯净网络栈：
  ```bash
  # 停止服务并杀掉所有深信服后台进程
  sudo systemctl stop aTrustDaemon EasyMonitor 2>/dev/null || true
  sudo killall -9 aTrustAgent aTrustXtunnel-64 aTrustTray EasyMonitor ECAgent 2>/dev/null || true
  
  # 彻底清除软件包
  sudo dpkg --purge cn.com.sangfor.atrust easyconnect || true
  
  # 清理系统级与用户级残留文件、iptables 规则与 hosts 劫持
  sudo rm -rf /usr/share/sangfor ~/.aTrust ~/.config/EasyConnect /root/.aTrust
  sudo sed -i '/sangfor/d' /etc/hosts
  sudo ip link delete utun7 2>/dev/null || true
  ```

---

### 问题 2：Pale Moon 默认 User-Agent 阻断 NPAPI 插件加载（最隐蔽的坑）

- **故障现象**：
  deb 包与后台服务都安装启动成功，用 Pale Moon 访问网关 `https://111.202.232.70:1443/`，页面正常显示登录表单，输入账号密码提交后**没有任何反应**，系统始终没有分配 `172.20.70.*` 地址，也没有建立 IPsec 隧道。
- **底层根因分析**：
  深入分析网关前端核心脚本 `https://111.202.232.70:1443/vpn/common/js/jquery.sslvpn.js`，发现网关使用了强依赖字符串匹配的浏览器检测代码：
  ```javascript
  } else if (agent.indexOf("Firefox") > -1) {
      sslvpn.Agent.isFirefox = true;
      ...
  }
  
  // 只有满足 isFirefox && isLinux，网关才会在页面动态插入插件节点！
  sslvpn.checkAgent(function(agent) {
      if (agent.isFirefox && agent.isLinux) {
          document.write("<div style=\"visibility:hidden;height:1px\"><embed id=\"secvpnplugin\" type=\"application/secvpn-plugin\"></div>");
      }
  });
  ```
  **致命矛盾**：Pale Moon 默认使用的是其专属的 Goanna 引擎 User-Agent，**完全不包含 "Firefox" 字符串**！  
  导致网关误判当前浏览器不支持插件，**根本没有在 DOM 中创建 `<embed id="secvpnplugin">` 节点**。浏览器没有加载 `/usr/lib/mozilla/plugins/libnpSecClientAssist.so` 插件，网页点击登录后无法向本地 Unix Socket（`/var/run/secvpn/secvpn.fox`）发送指令，后台隧道服务完全未被触发！
- **解决方案**：
  在 Pale Moon 的专用 profile 配置文件（`profile/user.js` 与 `profile/prefs.js`）中强制覆盖 User-Agent 为 Firefox，并强制激活插件：
  ```javascript
  user_pref("general.useragent.override", "Mozilla/5.0 (X11; Linux x86_64; rv:68.0) Gecko/20100101 Firefox/68.0");
  user_pref("general.useragent.override.111.202.232.70", "Mozilla/5.0 (X11; Linux x86_64; rv:68.0) Gecko/20100101 Firefox/68.0");
  user_pref("plugin.state.libnpSecClientAssist", 2);
  user_pref("plugin.state.libnpsecclientassist", 2);
  user_pref("plugin.default.state", 2);
  ```
  配置后重启 Pale Moon，网关立即识别成功并插入插件节点，系统随即启动 `plugin-container` 进程加载插件，登录瞬间打通隧道！
  *(注：该配置已永久固化在备份目录 `palemoon-trustaccess/profile/user.js` 中)*

---

### 问题 3：Ubuntu 缺少 `/sbin/iptables` 软链接导致 SSH 等非 Web 流量无法转发

- **故障现象**：
  网页端成功登录且获得了 `172.20.70.*` 虚拟 IP，GitLab 网页能访问，但通过终端执行 `ssh mac@172.20.149.210` 连接公司内部服务器时显示 `Connection timed out`。
- **底层根因分析**：
  TrustAccess 客户端包含一个专门处理 CS 架构（客户端/服务端，如 SSH 22 端口、数据库）流量转发的代理进程 `scsProxyd`。排查其错误日志 `/tmp/scsProxy.error` 时发现：
  ```text
  sh: 1: /sbin/iptables: not found
  createScsDnat error!
  controlReadCallBack handle message error
  ```
  TrustAccess 为旧版 Linux（CentOS 6/7）编译，程序内部写死了调用 `/sbin/iptables` 进行 DNAT 规则下发。而在 Ubuntu 20.04 中，iptables 默认安装在 `/usr/sbin/iptables`，系统中不存在 `/sbin/iptables` 路径，导致其端口转发规则创建失败。
- **解决方案**：
  在系统根目录下补全软链接（跨重启永久生效）：
  ```bash
  sudo ln -sf /usr/sbin/iptables /sbin/iptables
  sudo ln -sf /usr/sbin/iptables-legacy /sbin/iptables-legacy 2>/dev/null || true
  sudo ln -sf /usr/sbin/ip6tables /sbin/ip6tables 2>/dev/null || true
  ```

---

### 问题 4：网关服务端“会话超时”（约 3.5 小时后静默断连，“假在线”）

- **故障现象**：
  白天工作连着 VPN 正常，几小时后突然 SSH 卡死或断开、内网网页打不开；但查看桌面的 Pale Moon 页面，右上方依然显示“欢迎使用安全网关”、“在线时间：03:38:46”，TrustAccess 小窗口也依然显示“已登录”。
- **底层根因分析**：
  - **服务端强制超时**：公司网关配置了单次连接最大生命周期策略（通常为 3.5 ~ 4 小时）。达到时长后，网关在服务端注销了会话并销毁了 IPsec 密钥，断开解密通道。
  - **前端假象**：Pale Moon 页面上的“在线时间”只是浏览器本地 JavaScript 的秒表计时器；TrustAccess 小窗口在初次建立连接后不会自动退出。界面虽然看似“在线”，但实际隧道已被服务端掐断。
  - 抓包证实：向内网服务器发出的所有 TCP/UDP 报文，网关一律不再解密、不再回包。
- **解决方案（秒级恢复）**：
  **这是正常安全策略，无需重启电脑**：
  1. 切到 Pale Moon 浏览器窗口。
  2. 按快捷键 **`Ctrl + F5`** 强制刷新网页。
  3. 页面会自动跳出登录框（提示 `0x80000014: 登录会话超时，请重新登录`），重新输入一次密码并点击「确定」登录。
  4. 登录成功后，隧道立刻重新激活，终端 SSH 与内网网页秒级恢复连通！

---

### 问题 5：Pale Moon 非正常退出后残留锁文件导致无法二次启动

- **故障现象**：
  如果电脑异常关机、合盖睡眠或强制杀掉 Pale Moon 进程后，再次双击桌面图标，浏览器无法启动，后台提示：
  `profile 中存在旧锁文件。确认 Pale Moon 已完全退出后执行：rm -f ...`
- **解决方案**：
  已对启动脚本 `start-palemoon.sh` 进行健壮性升级：在拉起浏览器前，先检测系统中是否已有 palemoon 进程。若没有正在运行的进程，**自动静默清理 `profile/lock` 和 `profile/.parentlock`**，彻底消除该报错。
  *(注：该优化已同步更新至备份目录 `palemoon-trustaccess/start-palemoon.sh`)*

---

## 二、新电脑部署极简操作 Checklist

当您未来将 `/home/mac/macperson/computer_tools_backup/mkvpn` 拷贝到全新电脑（Ubuntu/Debian x86_64）时，请按以下 4 步顺序执行，保证 100% 一次成功：

### 第一步：清理可能存在的冲突 VPN 并补全系统软链接
```bash
# 1. 确保 iptables 软链接存在（解决 scsProxyd DNAT 报错）
sudo ln -sf /usr/sbin/iptables /sbin/iptables

# 2. 如果新机预装了深信服 aTrust/EasyConnect，务必先卸载
sudo dpkg --purge cn.com.sangfor.atrust easyconnect 2>/dev/null || true
```

### 第二步：安装 TrustAccess deb 底层服务
```bash
cd /path/to/mkvpn/linuxclient
sudo dpkg -i ./trustaccess_1.0.1-1_amd64.deb
test -x /usr/lib/mozilla/plugins/libnpSecClientAssist.so && echo "NPAPI 插件已就绪"
```

### 第三步：部署便携版 Pale Moon 浏览器
```bash
# 拷贝到用户家目录
cp -a /path/to/mkvpn/palemoon-trustaccess "$HOME/palemoon-trustaccess"
chmod +x "$HOME/palemoon-trustaccess/palemoon/palemoon"
chmod +x "$HOME/palemoon-trustaccess/start-palemoon.sh"

# 创建桌面快捷方式
cat << 'EOF' > "$HOME/Desktop/TrustAccess-Pale-Moon.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=TrustAccess VPN (Pale Moon)
Comment=Launch Pale Moon for TrustAccess VPN Login
Exec=/home/mac/palemoon-trustaccess/start-palemoon.sh https://111.202.232.70:1443/
Icon=/home/mac/palemoon-trustaccess/palemoon/browser/icons/mozicon128.png
Terminal=false
Categories=Network;WebBrowser;
StartupNotify=true
EOF
chmod +x "$HOME/Desktop/TrustAccess-Pale-Moon.desktop"
```

### 第四步：配置内部域名并登录验证
```bash
# 1. 写入常用内部域名解析（如 GitLab 等）
sudo sed -i '/mkzy.com/d' /etc/hosts
echo "172.20.149.216 gitlab.mkzy.com pkg.mkzy.com minio-api.mkzy.com" | sudo tee -a /etc/hosts

# 2. 确认服务状态，启动 Pale Moon
"$HOME/palemoon-trustaccess/start-palemoon.sh"
```
在弹出的网页中输入账号密码登录。

### 第五步：验证网络连通性
登录成功后在终端运行：
```bash
# 验证是否获取到 172.20.70.* 隧道地址
ip -4 addr show | grep '172.20.70'

# 验证 SSH 免密连通内网开发机
ssh -o BatchMode=yes -o ConnectTimeout=5 mac@172.20.149.210 "hostname"
# 正常应返回: mac-ThinkPad-T14p-Gen-3
```
---

## 三、常用应急命令速查表

| 操作需求 | 推荐命令 | 说明 |
| :--- | :--- | :--- |
| **关机后再开机连接** | 直接双击桌面图标启动 Pale Moon 输入账号密码登录 | 脚本会自动检查并启动后台服务 |
| **连接超时/假在线** | Pale Moon 窗口中按 `Ctrl + F5` 刷新重新登录 | 网关 3.5h 超时后的秒级重连方法 |
| **杀掉所有残留重置** | `sudo killall -9 secvpnMonitord secvpnServerd secvpnServer scsProxyd TrustAccess && sudo /usr/local/trustaccess/secvpnMonitord` | 遇到僵死进程或多重启动时的彻底重置 |
| **关闭 VPN 退出** | `sudo /etc/init.d/secvpnd stop && sudo killall -9 pluto _plutorun _plutoload` | 彻底断开 VPN 隧道并释放资源 |
