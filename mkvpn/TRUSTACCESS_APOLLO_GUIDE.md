# TrustAccess 与 Apollo 容器使用记录

更新时间：2026-09-07

本文记录本次在 Ubuntu 主机上安装 TrustAccess、登录单位 VPN、修复 Apollo 容器内部依赖下载并完成 `modules/canbus` 编译的过程。

## 新电脑部署边界

这份 `mkvpn` 备份包含：

```text
TRUSTACCESS_APOLLO_GUIDE.md
linuxclient/trustaccess_1.0.1-1_amd64.deb
linuxclient/*.rpm
palemoon-trustaccess/       # Pale Moon 34.3.2.1、运行库和专用 profile
  connect-trustaccess.sh    # 一键检查网络、启动后台并打开登录页
  install-trustaccess-launcher.sh # 安装桌面/应用菜单快捷方式
```

其中 `.deb` 适用于 Ubuntu/Debian 的 x86_64 主机。新电脑先确认：

```bash
uname -m
dpkg --print-architecture
```

应分别看到 `x86_64` 和 `amd64`。本备份不包含 Apollo Docker 镜像、容器层和 `/apollo_workspace` 工程；新电脑还必须另外准备 Apollo 镜像/工程，或把原容器迁移过去。本文只记录如何让已有的 Apollo 容器使用 TrustAccess 网络。

Pale Moon 需要在本地图形桌面会话中以普通用户启动，不要使用 `sudo` 启动浏览器，也不要从没有图形会话的 SSH/tmux 中启动。如果窗口刚出现就自动消失，先执行 `who`：如果显示 `login screen`，说明当前还停留在 Ubuntu 登录界面，`DISPLAY` 虽然存在但没有可用的用户桌面；必须在电脑本地显示器登录 `mac` 后，再从桌面终端或桌面快捷方式启动。浏览器主要运行库已随便携目录提供，但仍依赖系统的 GTK2、DBus、ALSA、X11 等图形库。

本次验证还需要在 TrustAccess 专用 profile 的 `user.js` 中显式设置：

```text
plugin.state.libnpSecClientAssist=2
plugin.default.state=2
dom.ipc.plugins.enabled=false
```

前两项让旧插件始终激活，最后一项让它使用进程内 NPAPI。它们只放在这个专用 Pale Moon profile 中；该 profile 只访问单位 VPN 网关，不要用于普通网页浏览。

`user.js` 的完整内容应为：

```javascript
// Enable the legacy TrustAccess NPAPI plugin in this dedicated profile.
user_pref("plugin.state.libnpSecClientAssist", 2);
user_pref("plugin.default.state", 2);
user_pref("dom.ipc.plugins.enabled", false);
```

换电脑后优先复制整个 `palemoon-trustaccess` 目录；如果只复制浏览器压缩包，必须在新电脑的 `profile/user.js` 中恢复这三行。不要把这三个设置写入系统其他浏览器的 profile。

## 日常速查

登录 VPN：

```bash
if pgrep -x secvpnMonitord >/dev/null; then
  echo 'TrustAccess 后台服务已运行'
else
  sudo /etc/init.d/secvpnd start
fi
```

浏览器打开 `https://111.202.232.70:1443/` 并登录。

如果电脑在路上断网，先恢复 Wi-Fi、网线或手机热点；完全没有外部网络时，VPN 没有可连接的入口，不能只靠启动 TrustAccess 建立公司网络。恢复网络后，凡是发生过断网、睡眠唤醒、切换 Wi-Fi/网线或 DHCP 地址变化，都按“外出断网后的恢复”流程重新登录，不要直接沿用旧隧道。

关闭 VPN：

```bash
sudo /etc/init.d/secvpnd stop
sudo killall -TERM pluto _plutorun _plutoload 2>/dev/null || true
```

然后执行“关闭 VPN”章节中的进程检查，确认没有 TrustAccess 相关进程残留。

编译 Apollo：

```bash
docker exec -u mac -w /apollo_workspace \
  apollo_neo_dev_10.0.0_pkg \
  buildtool build --opt --gpu -p modules/canbus
```

## 一、TrustAccess 安装与登录

### 1. 安装位置

安装包：`trustaccess_1.0.1-1_amd64.deb`

安装命令（当前下载目录）：

```bash
cd /home/mac/Downloads/linuxclient
sudo dpkg -i trustaccess_1.0.1-1_amd64.deb
```

从本次备份安装时使用：

```bash
cd /home/mac/macperson/computer_tools_backup/mkvpn/linuxclient
sudo dpkg -i ./trustaccess_1.0.1-1_amd64.deb
```

安装完成后确认插件存在：

```bash
test -x /usr/lib/mozilla/plugins/libnpSecClientAssist.so \
  && echo 'TrustAccess 浏览器插件已安装'
```

这个 deb 的安装脚本会尝试启动 `secvpnMonitord`，并配置开机启动。因此安装后先检查进程；不要在已有 `secvpnMonitord` 时重复执行 `start`，否则这个旧版脚本可能启动重复进程。

主要文件：

```text
/usr/local/trustaccess/TrustAccess       # 图形程序
/usr/local/trustaccess/secvpnMonitord    # VPN 监控进程
/usr/local/trustaccess/secvpnServerd     # VPN 服务进程
/usr/local/trustaccess/scsProxyd         # 代理相关进程，按实际情况出现
/etc/init.d/secvpnd                      # 启停脚本
```

TrustAccess 的 deb 安装包还会安装 Pale Moon 需要的旧式浏览器插件：

```text
/usr/lib/mozilla/plugins/libnpSecClientAssist.so
```

所以换电脑时不能只复制 Pale Moon；必须先安装 TrustAccess 的 deb，再使用 Pale Moon。Pale Moon 目录保存的是浏览器本体和 profile，插件由 TrustAccess 安装到系统目录。

安装脚本已经配置了开机启动链接：

```text
/etc/rc2.d/S01secvpnd
/etc/rc3.d/S01secvpnd
/etc/rc4.d/S01secvpnd
/etc/rc5.d/S01secvpnd
```

### 2. 启动并登录

先启动 TrustAccess 后台服务：

```bash
sudo /etc/init.d/secvpnd start
```

如需要启动图形程序：

```bash
/usr/local/trustaccess/TrustAccess > "$HOME/trustaccess.log" 2>&1 &
```

本机直接运行图形程序时出现了 Qt 绘制警告，窗口没有正常显示。这个问题不影响后台 VPN 进程运行，因此本次使用浏览器登录页面完成登录：

本次实际使用的是 **Pale Moon**。它在本次环境中是完成 VPN 登录的关键入口：打开单位登录页、接受内部证书例外并提交用户名密码。Pale Moon 本身不负责建立 VPN 隧道，真正提供 VPN 网络和路由的是 TrustAccess 的后台进程；Pale Moon 负责完成网页端登录和本地客户端交接流程。

```text
https://111.202.232.70:1443/
```

浏览器可能显示 `SEC_ERROR_UNKNOWN_ISSUER` 或证书名称不匹配。确认地址确实是单位提供的 `111.202.232.70:1443` 后，接受该内部站点的证书例外，再输入 VPN 用户名和密码登录。

这里的 `111.202.232.70:1443` 是 VPN 登录网关，不需要写入 Apollo 工程，也不应当把它当作 DNS 服务器配置。

因此，换电脑时不要只启动 `/usr/local/trustaccess/TrustAccess` 就判断登录失败。若 TrustAccess 窗口仍不显示，应打开 Pale Moon 访问上述地址；这是本次已经验证成功的登录方式。

当前机器已经安装桌面快捷方式 **TrustAccess VPN Login**，位置是：

```text
/home/mac/Desktop/TrustAccess-VPN.desktop
```

也可以从应用菜单搜索 `TrustAccess VPN Login`。点击它会自动检查普通网络、清理必要的旧 IPsec 状态、启动 `secvpnd`，然后使用专用 Pale Moon profile 打开 VPN 登录页。正常情况下不需要再手动运行 `/usr/local/trustaccess/TrustAccess` 或单独启动 `start-palemoon.sh`。

如果远端 VPN 会话超时，服务器可能让登录窗口退出并要求重新认证。这是网关会话策略，不能通过本地脚本绕过；重新点击同一个 **TrustAccess VPN Login** 图标，重新输入账号密码即可。脚本不会保存 VPN 密码。如果浏览器进程仍然存在但页面已经失效，先关闭该 Pale Moon 窗口，再点击图标。

登录后检查：

```bash
ps -eo pid,ppid,user,comm,args | \
  awk '$5 ~ /^(secvpnMonitord|secvpnServerd|secvpnServer|scsProxyd|TrustAccess)$/'
ip addr
ip route
```

本机成功登录后出现了 VPN 地址 `172.20.70.135/32`，并且单位内网路由已经生效。VPN 地址每次可能不同，判断标准是出现 `172.20.70.*`，不要固定依赖本次的最后一段地址。

只有浏览器页面显示“登录成功”还不够。必须看到 VPN 地址和内网访问路径；如果只有 `secvpnMonitord`、`secvpnServerd` 进程，却没有 `172.20.70.*` 地址，说明本地隧道没有建立。此时不要直接测试 SSH 密码，应先修复登录交接。

网络从无线切换到有线、DHCP 地址变化，或电脑从公司网络切回家用网络后，旧版 TrustAccess 可能继续使用旧的 `left=` 地址。此时不要直接手工修改 `/etc/ipsec.conf`，该文件由登录过程生成；按下面流程清理旧 IPsec 状态后重新登录：

```bash
# 先完全退出 Pale Moon
sudo /etc/init.d/secvpnd stop
sudo killall -TERM pluto _plutorun _plutoload 2>/dev/null || true
sleep 2
sudo /etc/init.d/secvpnd start

cd /home/mac/Downloads/palemoon-trustaccess
./connect-trustaccess.sh
```

然后重新打开 `https://111.202.232.70:1443/` 登录。确认出现 `172.20.70.*` 地址后，再连接 SSH。

### 2.1 这次排坑结论与故障判断

本次故障表面上是“网页已经登录，但 SSH 到 `172.20.149.215` 超时”，实际分成了几个独立问题。以后换电脑时按下面顺序判断，不要只看浏览器页面：

1. 网页显示登录成功，只说明网关接受了账号密码；它不代表本机的 NPAPI 插件已经把登录结果交给 TrustAccess，也不代表 IPsec 隧道和内网路由已经建立。
2. 本次最初只有 `secvpnMonitord`、`secvpnServerd`，没有 `172.20.70.*` 虚拟地址，说明 Pale Moon 的旧插件交接没有真正执行。专用 profile 中的三个设置必须存在：

   ```bash
   rg -n 'plugin.state.libnpSecClientAssist|plugin.default.state|dom.ipc.plugins.enabled' \
     "$HOME/palemoon-trustaccess/profile/user.js"
   ```

3. 网关配置文件中要求的插件版本是 `5,3,3,37`，本机安装包提供的是旧版 `Secvpn Client 1.0.0.5` 和旧的 `SAG*` 接口。这是版本/API 不匹配，可能导致浏览器页面能打开但插件方法不完整或静默失败。不要从不明来源单独下载插件；应使用单位提供的成套 TrustAccess 安装包和本备份中的专用 profile。若单位以后提供新网关或新客户端包，应使用相互匹配的一套版本。
4. 本机从无线切换到有线后，旧 `/etc/ipsec.conf` 仍然使用之前的 `left=192.168.3.159`，而当前地址已经是 `192.168.5.2`，日志出现 `Errno 101 Network is unreachable`。这不是账号错误，也不是 SSH 错误；按上一节停止并重启 `secvpnd`、清理 `pluto` 后重新登录。不要手工改生成的 `/etc/ipsec.conf`，否则下一次登录仍可能被覆盖或留下不一致的 IPsec 状态。
5. 安装脚本本身会尝试启动后台服务。如果重复执行 `sudo /etc/init.d/secvpnd start`，可能出现多个 `secvpnMonitord`、`secvpnServerd` 或残留 `pluto`。看到重复进程时不要继续叠加启动，按上一节的停止、清理、启动顺序恢复为一套后台进程。
6. 本次修复后出现 `172.20.70.135/32`，`ip route get 172.20.149.215` 使用该地址作为源地址，TCP 22 端口可以连通；此时再执行 SSH，如果只得到 `Permission denied (publickey,password)`，说明 VPN 网络已经正常，剩下的是服务器账号、密码或 SSH 密钥认证问题。

推荐的最小检查命令：

```bash
pgrep -af 'secvpnMonitord|secvpnServerd|scsProxyd|pluto'
ip -br addr
ip route get 172.20.149.215
timeout 5 bash -c '</dev/tcp/172.20.149.215/22' \
  && echo 'TCP 22 reachable' \
  || echo 'TCP 22 unreachable'
```

结果按下面解释：

```text
没有 172.20.70.* 地址        -> 浏览器插件/本地客户端交接失败，先检查 user.js 和专用 Pale Moon
出现旧 left= 地址或 Errno 101 -> 网络发生切换，清理 secvpnd/pluto 后重新登录
TCP 22 reachable              -> VPN 路径正常，SSH 只需处理认证
TCP 22 unreachable            -> 仍未建立正确隧道或路由，暂时不要排查 SSH 密码
```

直接运行 `/usr/local/trustaccess/TrustAccess` 时看到的 `libpng`、`QWidget::paintEngine`、`QPainter` 警告，以及窗口不显示，不是判断 VPN 是否成功的依据。本次 Qt 图形程序没有提供可靠的登录窗口，实际登录入口是 Pale Moon；最终以 TrustAccess 进程、`172.20.70.*` 地址、路由和 TCP 22 连通性为准。

如果 Pale Moon 窗口刚出现就消失，先确认是在本地 Ubuntu 图形桌面以 `mac` 普通用户启动；`who` 只显示 `login screen` 时，当前没有真正登录桌面。不要在 SSH、tmux 或 `sudo` 环境启动这个旧浏览器。

### 2.2 外出断网后的恢复

适用于以下情况：路上网络断开后重新连网、电脑合盖后再打开、从家用 Wi-Fi 切换到手机热点/公司网络，或醒来后 SSH 突然超时。此时通常不需要重新安装 TrustAccess，也不需要重新创建 Apollo 容器；问题多半是旧 IPsec 状态还绑定着断网前的地址。

1. 先在本地 Ubuntu 图形桌面重新连上可用网络。确认本机已经获得地址：

   ```bash
   ip -br addr
   ```

   必须先看到当前 Wi-Fi/网线接口有 IP。没有 IP，或无法访问 `111.202.232.70:1443` 时，先修复普通网络；VPN 本身无法替代外部网络。

2. 退出 Pale Moon 登录窗口。清理旧后台和 IPsec 子进程：

   ```bash
   sudo /etc/init.d/secvpnd stop
   sudo killall -TERM pluto _plutorun _plutoload 2>/dev/null || true
   sleep 2
   sudo /etc/init.d/secvpnd start
   ```

   这样做是为了让下一次登录根据当前网络重新生成 `left=` 地址。不要手工编辑 `/etc/ipsec.conf`，它是登录流程生成的临时配置，手工修改不能可靠解决网络切换问题。

3. 在本地桌面以普通用户启动专用 Pale Moon：

   ```bash
   cd "$HOME/palemoon-trustaccess"
   ./connect-trustaccess.sh
   ```

   如果提示 profile 被占用，确认没有 Pale Moon 进程后再清理锁文件：

   ```bash
   rm -f "$HOME/palemoon-trustaccess/profile/lock" \
         "$HOME/palemoon-trustaccess/profile/.parentlock"
   ```

4. 打开 `https://111.202.232.70:1443/`，必要时重新接受内部证书例外并登录。网页显示成功后，继续检查隧道：

   ```bash
   ip -br addr
   ip route get 172.20.149.215
   timeout 5 bash -c '</dev/tcp/172.20.149.215/22' \
     && echo 'TCP 22 reachable' \
     || echo 'TCP 22 unreachable'
   ```

   看到 `172.20.70.*` 且 TCP 22 可达后，才进入 Apollo 容器或执行 SSH。若没有 `172.20.70.*`，说明本地客户端交接仍未完成，回到“这次排坑结论与故障判断”。

这套恢复流程只清理并重建当前 VPN 会话，不会删除 `/etc/hosts`、Apollo 容器或容器内的 transform 修复。网络恢复后，容器只需重新执行原来的构建命令。

### 3. 为什么必须使用 Pale Moon

这次不是“网页能不能显示”的问题，而是单位 VPN 网关使用了较老的网页登录和本地客户端交接方式。在本次抓到的登录页面和脚本中，仍然可以看到以下旧接口：

```text
NPAPI 插件：application/secvpn-plugin
浏览器插件检测：navigator.mimeTypes
ActiveXObject
本机客户端连接：wss://localhost:9800
```

Chrome 以及现代 Firefox 等浏览器即使能打开登录页，也已经不提供这类 NPAPI/ActiveX 本地插件接口，因此不能可靠完成“网页登录 -> 本地 TrustAccess 客户端 -> VPN 隧道”的交接。之前遇到的情况正是页面或证书提示可以出现，但本地 VPN 登录流程没有完成。

Pale Moon 的作用是提供本次网关仍能使用的旧式 Mozilla 插件兼容入口。当前可用的 Pale Moon 专用 profile 还保存了三项关键设置：

```text
plugin.state.libnpSecClientAssist=2
plugin.default.state=2
dom.ipc.plugins.enabled=false
111.202.232.70:1443 的内部证书例外
```

如果只解压 Pale Moon 本体而没有复制完整 `profile`，需要重新写入上面三项设置；优先复制备份中的整个 `palemoon-trustaccess` 目录。三个设置的作用分别是：`plugin.state.libnpSecClientAssist=2` 启用 TrustAccess 插件，`plugin.default.state=2` 避免旧插件停留在“询问是否激活”，`dom.ipc.plugins.enabled=false` 让本次旧插件使用进程内 NPAPI 交接。最后一项会关闭该 profile 的插件进程隔离，存在安全风险，因此这个 profile 只能用于单位 VPN 网关，不要用于普通网页浏览。

此外，网关证书由单位内部 LeadSec CA 签发，系统浏览器通常会报 `SEC_ERROR_UNKNOWN_ISSUER`，并且证书名称与直接访问的 IP 不匹配；网关实测只协商到 TLS 1.2，未协商 TLS 1.3。这些证书和旧 TLS 兼容问题会进一步增加现代浏览器失败的概率，但不是把 Pale Moon 当作 VPN 的原因。

结论：**Pale Moon 是登录这个旧 VPN 网关和触发本地客户端交接的浏览器，不是 VPN 隧道本身。TrustAccess 后台进程才负责建立隧道和路由。换电脑时必须同时准备 TrustAccess 和 Pale Moon，不能只安装 TrustAccess。**

## 二、换一台电脑时的最短操作流程

以下步骤假设新电脑也是 Ubuntu/Debian x86_64 系统。先把本备份中的整个 `mkvpn` 目录复制到新电脑本地磁盘；下面用 `MKVPN` 表示这个目录的实际路径：

1. 安装 deb：

   ```bash
   export MKVPN=/path/to/mkvpn
   cd "$MKVPN/linuxclient"
   sudo dpkg -i ./trustaccess_1.0.1-1_amd64.deb
   test -x /usr/lib/mozilla/plugins/libnpSecClientAssist.so \
     && echo 'TrustAccess 浏览器插件已安装'
   ```

   本机备份的实际路径是 `/home/mac/macperson/computer_tools_backup/mkvpn`；新电脑不要照抄这个路径，替换为 U 盘、移动硬盘或新电脑上的实际路径。也不要在 Ubuntu/Debian 上使用同目录中的 RPM。

2. 准备 Pale Moon。当前机器已经有一套可直接运行的便携版备份，位置是：

   ```text
   /home/mac/macperson/computer_tools_backup/mkvpn/palemoon-trustaccess/
   ```

   将这个目录复制到新电脑本地磁盘的用户目录，例如 `$HOME/palemoon-trustaccess`，不要直接从可能带 `noexec` 选项的 U 盘或网络盘运行。它不是通过 `apt` 或 `dpkg` 安装的，不需要系统安装；确认浏览器文件可执行：

   ```bash
   chmod +x "$HOME/palemoon-trustaccess/palemoon/palemoon"
   ```

   安装一次桌面和应用菜单快捷方式：

   ```bash
   chmod +x "$HOME/palemoon-trustaccess/connect-trustaccess.sh" \
     "$HOME/palemoon-trustaccess/install-trustaccess-launcher.sh"
   cd "$HOME/palemoon-trustaccess"
   ./install-trustaccess-launcher.sh
   ```

   以后直接点击桌面的 `TrustAccess VPN Login`。如果服务器会话超时导致登录窗口退出，再次点击同一个图标并重新输入账号密码。

   可先检查新电脑是否缺少系统库：

   ```bash
   PM="$HOME/palemoon-trustaccess/palemoon"
   LD_LIBRARY_PATH="$PM" ldd "$PM/libxul.so" | rg 'not found' \
     || echo 'Pale Moon 运行库检查通过'
   ```

   如果输出 `not found`，先按输出的库名安装新电脑发行版对应的 GUI 运行库，再启动 Pale Moon；这不是 TrustAccess 登录配置问题。

   本机原目录内也有浏览器压缩包：

   ```text
   /home/mac/Downloads/palemoon-trustaccess/palemoon.tar.xz
   ```

   如果只拿到这个压缩包，可在新电脑本地磁盘执行：

   ```bash
   mkdir -p "$HOME/palemoon-trustaccess"
   tar -xJf /path/to/palemoon.tar.xz -C "$HOME/palemoon-trustaccess"
   chmod +x "$HOME/palemoon-trustaccess/palemoon/palemoon"
   ```

   但这个压缩包只包含浏览器本体，不包含本次验证过的 `profile`；只用压缩包时需要重新设置插件状态并重新接受证书例外。为了保留本次已经验证过的插件和证书设置，优先复制整个 `palemoon-trustaccess` 目录，包含其中的 `profile`。

   这个 profile 是从旧电脑复制的，可能带有旧电脑的 Pale Moon 锁文件或旧目录路径。确认 Pale Moon 完全退出后，如发现启动时提示 profile 正在使用，可执行：

   ```bash
   rm -f "$HOME/palemoon-trustaccess/profile/lock" \
         "$HOME/palemoon-trustaccess/profile/.parentlock"
   ```

   如果新电脑没有使用 `/home/mac/Downloads/palemoon-trustaccess` 这个原路径，启动前可把 profile 中记录的旧路径改成新路径：

   ```bash
   sed -i "s#/home/mac/Downloads/palemoon-trustaccess#$HOME/palemoon-trustaccess#g" \
     "$HOME/palemoon-trustaccess/profile/prefs.js"
   ```

   这只修正 Pale Moon 的扩展路径记录，不会修改 VPN 地址、用户名或密码。不要删除 profile 中的 `user.js`，其中包含本次验证成功所需的三个插件设置。确认设置没有丢失：

   ```bash
   rg -n 'plugin.state.libnpSecClientAssist|plugin.default.state|dom.ipc.plugins.enabled' \
     "$HOME/palemoon-trustaccess/profile/user.js"
   ```

   输出应包含三行 `user_pref`。如果只使用 `palemoon.tar.xz`，用文本编辑器打开或创建上述 `user.js`，写入“新电脑部署边界”中的完整内容；只解压浏览器本体而不恢复 profile，是本次最容易遗漏的配置。

   ```bash
   chmod +x "$HOME/palemoon-trustaccess/start-palemoon.sh" \
     "$HOME/palemoon-trustaccess/palemoon/palemoon"
   ```

3. 启动 TrustAccess 后台服务：

   ```bash
   if pgrep -x secvpnMonitord >/dev/null; then
     echo 'TrustAccess 后台服务已运行'
   else
     sudo /etc/init.d/secvpnd start
   fi
   ```

4. 如果不使用桌面图标，也可以使用一键连接脚本：

   ```bash
   cd "$HOME/palemoon-trustaccess"
   ./connect-trustaccess.sh
   ```

   该脚本会使用 `-no-remote -profile ... -new-window` 启动专用 Pale Moon，并打开 VPN 登录页；不能改为普通浏览器启动方式，这样才能让本地 TrustAccess 插件连接到 `secvpnServerd`。`start-palemoon.sh` 仍可作为只启动浏览器的底层脚本使用，但不负责自动启动后台服务。

   当前机器也可以直接执行：

   ```bash
   cd /home/mac/Downloads/palemoon-trustaccess
   ./connect-trustaccess.sh
   ```

   新电脑复制完整目录后，运行 `install-trustaccess-launcher.sh` 即可生成对应路径的桌面快捷方式；不要直接复制旧电脑中写死 `/home/mac/Downloads/...` 路径的 `.desktop` 文件。

5. 在 Pale Moon 中打开：

   ```text
   https://111.202.232.70:1443/
   ```

6. 如果出现内部证书警告，核对地址确实是 `111.202.232.70:1443` 后接受证书例外，然后提交 VPN 用户名和密码。不要把该地址当作普通公网网站，也不要把 `1443` 改成 `443`。

7. 登录后确认 VPN 进程、虚拟地址和路由：

   ```bash
   ps -eo pid,ppid,user,comm,args | \
     awk '$5 ~ /^(secvpnMonitord|secvpnServerd|secvpnServer|scsProxyd|TrustAccess)$/'
   ip -br addr
   ip route get 172.20.149.216
   ```

   必须能看到 `172.20.70.*` 地址；如果只有网页“登录成功”而没有该地址，回到“这次排坑结论与故障判断”处理，不要继续编译。

8. 如果单位内部域名不能解析，按下一节补充 hosts。IP 地址以单位实际提供的地址为准，不要盲目照抄旧机器的地址。

### 2.3 Pale Moon 备份说明

本机已将完整目录备份到：

```text
/home/mac/macperson/computer_tools_backup/mkvpn/palemoon-trustaccess/
```

备份内容包括：

```text
palemoon/                 # Pale Moon 34.3.2.1 可执行程序及运行库
profile/                  # 专用 profile，含插件设置、证书例外和登录状态
start-palemoon.sh         # 跟随目录移动仍可用的启动脚本
connect-trustaccess.sh    # 一键检查网络、启动后台并打开登录页
install-trustaccess-launcher.sh # 按当前目录生成桌面/应用菜单快捷方式
palemoon.tar.xz           # 浏览器压缩包
palemoon-eu.tar.xz、part.* # 原目录中已有的其他归档文件
```

完整目录约 201 MB。`profile` 可能还包含 Cookie、历史记录和登录会话，备份目录应按含密码资料保护，不要上传到公共网盘或提交到代码仓库。如果不想迁移这些个人会话，只复制 `palemoon/` 和 `palemoon.tar.xz`，新电脑首次登录时重新接受证书例外即可；但仍必须先安装 TrustAccess，使 `/usr/lib/mozilla/plugins/libnpSecClientAssist.so` 存在。本次建议直接使用完整备份目录。

## 三、单位内部域名解析

### 1. 本次实际补充的 hosts

Apollo 的 buildtool 配置已经使用单位内部包服务器：

```text
http://pkg.mkzy.com/packages/api/...
```

该服务器返回的依赖下载地址又使用了 `minio-api.mkzy.com`。本机最终补充了以下映射：

```text
172.20.149.216 gitlab.mkzy.com
172.20.149.216 pkg.mkzy.com
172.20.149.216 minio-api.mkzy.com
```

编辑方式：

```bash
sudoedit /etc/hosts
```

或者在确认三个域名确实都指向 `172.20.149.216` 后执行：

```bash
sudo sh -c 'grep -qE "^[[:space:]]*172\.20\.149\.216[[:space:]]+gitlab\.mkzy\.com([[:space:]]|$)" /etc/hosts || printf "172.20.149.216 gitlab.mkzy.com\n" >> /etc/hosts'
sudo sh -c 'grep -qE "^[[:space:]]*172\.20\.149\.216[[:space:]]+pkg\.mkzy\.com([[:space:]]|$)" /etc/hosts || printf "172.20.149.216 pkg.mkzy.com\n" >> /etc/hosts'
sudo sh -c 'grep -qE "^[[:space:]]*172\.20\.149\.216[[:space:]]+minio-api\.mkzy\.com([[:space:]]|$)" /etc/hosts || printf "172.20.149.216 minio-api.mkzy.com\n" >> /etc/hosts'
```

验证：

```bash
getent hosts gitlab.mkzy.com pkg.mkzy.com minio-api.mkzy.com
curl --noproxy '*' -I --max-time 8 http://gitlab.mkzy.com/
```

如果 `172.20.149.216` 在新电脑上不可达，应先登录 TrustAccess，再用单位提供的 DNS 或 IP 重新确认映射，不要把公网 DNS 当作单位内部 DNS。

这些 hosts 修改是在**新电脑宿主机**的 `/etc/hosts` 中完成的，不是在 Apollo 容器内单独配置。当前容器是 host 网络模式，因此容器会沿用宿主机的网络路径和这些域名解析结果。

## 四、关闭 VPN

去公司并连接公司内网后，建议停止 TrustAccess 后台服务：

```bash
sudo /etc/init.d/secvpnd stop
```

由于 TrustAccess 会启动 IPsec 的 `pluto` 子进程，关闭后也应清理并检查它：

```bash
sudo killall -TERM pluto _plutorun _plutoload 2>/dev/null || true
```

该脚本会停止以下进程：

```text
secvpnMonitord
secvpnServerd
secvpnServer       # 实际运行中可能出现的子进程
TrustAccess
```

脚本明确处理的是 `secvpnMonitord`、`secvpnServerd` 和 `TrustAccess`；你之前看到的 `secvpnServer` 可能是 `secvpnServerd` 派生的子进程，所以关闭后必须一并检查。

确认是否已经停止：

```bash
ps -eo pid,ppid,user,comm,args | \
  awk '$5 ~ /^(secvpnMonitord|secvpnServerd|secvpnServer|scsProxyd|TrustAccess)$/'
```

如果仍然看到 `secvpnServer` 或 `scsProxyd`，先根据上面的 PID 确认进程确实属于 TrustAccess，再停止对应 PID：

```bash
sudo kill -TERM <残留进程的 PID>
```

再次执行上面的 `ps` 检查命令，确认没有输出后才算进程清理完成。

如果图形界面有托盘菜单，也可以先执行退出/断开，但命令行启停脚本更可靠。公司内网本身可能仍然有单位网段路由，这不代表 TrustAccess 没有关闭。

如果不希望后台服务随系统启动，可以取消开机启动：

```bash
sudo /usr/local/trustaccess/boot_startup.sh del
```

以后需要恢复开机启动：

```bash
sudo /usr/local/trustaccess/boot_startup.sh add
```

通常不需要频繁执行 `del/add`，只需使用 `start/stop` 即可。

## 五、关机、重启后再次使用

### 1. 电脑重启后

先执行：

```bash
if pgrep -x secvpnMonitord >/dev/null; then
  echo 'TrustAccess 后台服务已运行'
else
    sudo /etc/init.d/secvpnd start
fi
```

如果重启前后网络发生变化，直接按“外出断网后的恢复”流程处理；不要只启动后台服务后继续使用旧登录状态。

如果脚本提示已经运行，可以直接打开 Pale Moon 登录页面：

```text
https://111.202.232.70:1443/
```

图形窗口仍不显示时，继续使用 Pale Moon 登录，并用下面命令确认：

```bash
ps -eo pid,ppid,user,comm,args | \
  awk '$5 ~ /^(secvpnMonitord|secvpnServerd|secvpnServer|scsProxyd|TrustAccess)$/'
ip route get 172.20.149.216
```

### 2. 之前手动关闭过 VPN 后

重复以下三步即可：

```bash
if pgrep -x secvpnMonitord >/dev/null; then
  echo 'TrustAccess 后台服务已运行'
else
  sudo /etc/init.d/secvpnd start
fi
```

然后使用 Pale Moon 登录 `https://111.202.232.70:1443/`，最后确认 VPN 路由。

## 六、Apollo 容器内做过的事情

容器名称：`apollo_neo_dev_10.0.0_pkg`

工作目录：`/apollo_workspace`

注意：`mkvpn` 备份不包含这个 Docker 容器和 Apollo 镜像。新电脑上需要先确认它们存在：

```bash
docker ps -a --filter name=apollo_neo_dev_10.0.0_pkg
docker images
```

如果容器不存在，需要从原电脑或单位提供的 Apollo 镜像重新导入/创建，并确保创建时使用 `--network host`；仅复制本文档和 TrustAccess 安装包不能生成 Apollo 容器。

### 0. 编译前先判断网络是否真的恢复

不要看到 buildtool 的 `Can't connect with the server, use offline mode` 就立刻重复编译。先在宿主机确认 VPN 隧道，再在容器内确认域名和 HTTP：

```bash
ip route get 172.20.149.216
docker exec -u mac apollo_neo_dev_10.0.0_pkg \
  getent hosts pkg.mkzy.com minio-api.mkzy.com
docker exec -u mac apollo_neo_dev_10.0.0_pkg sh -c \
  "curl --noproxy '*' -I --max-time 8 http://gitlab.mkzy.com/"
```

三步都正常后再运行 `buildtool`。如果宿主机路由不通，先处理 TrustAccess 登录；如果路由通但容器域名解析失败，检查宿主机 `/etc/hosts`；如果网络检查正常而出现 `transform.BUILD is not a regular file`，再执行后面的 transform 元数据修复。这样可以把 VPN、DNS 和 Apollo 包元数据问题分开，避免反复重装容器。

### 1. 先确认容器网络模式

当前容器使用 host 网络模式，因此容器直接使用宿主机的 VPN 网络路径：

```bash
docker inspect apollo_neo_dev_10.0.0_pkg \
  --format '{{.HostConfig.NetworkMode}}'
```

输出为 `host` 时，容器不需要单独配置 Docker 网关或额外 VPN。关键是宿主机必须已经登录 TrustAccess，并且容器内能解析内部域名。

### 2. 修复了内部包服务器解析

在宿主机 `/etc/hosts` 增加 `gitlab.mkzy.com`、`pkg.mkzy.com`、`minio-api.mkzy.com` 后，容器内验证成功：

```bash
docker exec -u mac apollo_neo_dev_10.0.0_pkg \
  getent ahostsv4 gitlab.mkzy.com pkg.mkzy.com minio-api.mkzy.com

docker exec -u mac apollo_neo_dev_10.0.0_pkg sh -c \
  "curl --noproxy '*' -I --max-time 8 http://gitlab.mkzy.com/"
```

最初 buildtool 报错是：

```text
Can't connect with the server, use offline mode
NetworkIoError
Failed to resolve 'pkg.mkzy.com'
```

补充 `pkg.mkzy.com` 后，又发现实际 deb 下载地址使用 `minio-api.mkzy.com`，因此再补充了后者。

### 3. 修复 transform 包的错误版本元数据

网络恢复后，buildtool 能下载 `apollo-neo-transform`，但该包文件名版本为：

```text
0.0.3.dev2026090301
```

包内 `cyberfile.xml` 却写成：

```text
10.0.1
```

buildtool 安装后把它误判成旧版本并删除，造成：

```text
/apollo_workspace/dev/bazel/transform.BUILD is not a regular file
```

该路径实际上是指向 transform 元数据的符号链接，但目标目录被错误清理了。

本次在容器内做了以下修复：

```text
/opt/apollo/neo/share/packages/transform/cyberfile.xml
```

先备份为：

```text
/opt/apollo/neo/share/packages/transform/cyberfile.xml.bak_20260905
```

再把其中的版本从 `10.0.1` 改为 `local`，使 buildtool 将它视为当前容器内的本地已安装包，不再重复删除。

### 4. 最终验证

执行的构建命令：

```bash
docker exec -u mac -w /apollo_workspace \
  apollo_neo_dev_10.0.0_pkg \
  buildtool build --opt --gpu -p modules/canbus
```

最终退出码为 `0`，日志为：

```text
compilation done!
```

产物已经生成：

```text
/opt/apollo/neo/lib/modules/canbus/libapollo_canbus.so
/opt/apollo/neo/lib/modules/canbus/libcanbus_component.so
/opt/apollo/neo/bin/canbus_tester
```

## 七、以后是否还需要重复这些操作

### 只关机或停止容器

一般不需要重复修复：

1. 宿主机 `/etc/hosts` 的三条映射仍然存在。
2. TrustAccess 登录后，容器可以继续使用 host 网络。
3. 当前容器中的 `transform` 元数据修改仍然存在。
4. 容器只是 `stop/start`，不会丢失容器文件系统内容。

启动 VPN 后可直接进入容器执行原来的构建命令。

### 删除并重新创建容器

如果执行了 `docker rm`、重新创建容器或换了新的 Apollo 镜像，容器内的 transform 修复可能丢失。此时按下面流程处理：

1. 先在宿主机登录 TrustAccess，并确认三个内部域名可解析。
2. 确认容器是 host 网络模式。
3. 在宿主机通过 `docker exec` 执行：

   ```bash
   docker exec -u mac -w /apollo_workspace \
     apollo_neo_dev_10.0.0_pkg buildtool reinstall transform
   ```

4. 检查并修正版本元数据：

   ```bash
   docker exec -u mac apollo_neo_dev_10.0.0_pkg sh -c \
     "grep -n '<version>' /opt/apollo/neo/share/packages/transform/cyberfile.xml"
   ```

   如果仍然显示 `10.0.1`，先备份再改为 `local`：

   ```bash
   docker exec -u mac apollo_neo_dev_10.0.0_pkg sh -c \
     "cp -p /opt/apollo/neo/share/packages/transform/cyberfile.xml /opt/apollo/neo/share/packages/transform/cyberfile.xml.bak && sed -i 's#<version>10.0.1</version>#<version>local</version>#' /opt/apollo/neo/share/packages/transform/cyberfile.xml"
   ```

5. 再执行 Apollo 编译。

这是针对当前单位包仓库元数据错误的临时修复。长期应让包维护者重新发布与文件名版本一致的 `cyberfile.xml`，这样新容器也不需要手动修改。

## 八、常见无害警告

下面这些日志不是本次失败原因：

```text
pkg_resources is deprecated as an API
The following rc files are no longer being read
compiler warning / deprecated-declarations / sign-compare
```

真正需要优先关注的是：

```text
Failed to resolve '*.mkzy.com'
NetworkIoError
is not a regular file
Build did NOT complete successfully
```

## 九、网络恢复后手动清理旧 IPsec 状态

适用场景：电脑在路上断网后重新联网、睡眠唤醒、切换 Wi-Fi/网线/手机热点，或者重新联网后 SSH 超时。前提是电脑已经先恢复普通网络；完全没有 Wi-Fi、网线或手机热点时，VPN 没有外部连接入口，无法启动。

如果当前 VPN 连接仍然正常，不需要执行清理。需要重新连接 VPN 时，按以下顺序手动操作：

1. 先关闭 Pale Moon 窗口。
2. 在终端执行：

   ```bash
   sudo /etc/init.d/secvpnd stop
   sudo killall -TERM pluto _plutorun _plutoload 2>/dev/null || true
   sleep 2
   sudo /etc/init.d/secvpnd start
   ```

   这几条命令分别用于：停止旧 TrustAccess 后台、清理残留的 IPsec 进程、等待进程退出、重新启动服务。这样下一次登录会根据当前网络重新生成 `left=` 地址，避免继续使用断网前的旧地址。即使某个进程本来就不存在，命令也可以继续执行。

3. 在本地 Ubuntu 图形桌面以普通用户启动专用 Pale Moon：

   ```bash
   cd /home/mac/Downloads/palemoon-trustaccess
   ./connect-trustaccess.sh
   ```

   如果目录已复制到用户主目录，则使用：

   ```bash
   cd "$HOME/palemoon-trustaccess"
   ./connect-trustaccess.sh
   ```

4. 在 Pale Moon 中打开并重新登录：

   ```text
   https://111.202.232.70:1443/
   ```

5. 登录后确认隧道已经重新建立：

   ```bash
   ip -br addr
   ip route get 172.20.149.215
   timeout 5 bash -c '</dev/tcp/172.20.149.215/22' \
     && echo 'TCP 22 reachable' \
     || echo 'TCP 22 unreachable'
   ```

   必须看到 `172.20.70.*` 地址，且 TCP 22 可达，才继续执行 SSH 或 Apollo 编译。若没有该地址，说明本地浏览器插件交接或 VPN 隧道仍未成功，回到“这次排坑结论与故障判断”。

不要删除或手工修改 `/etc/ipsec.conf`，不要重新安装 TrustAccess，也不要因为网络短暂中断就重新创建 Apollo 容器。上述清理只重建当前 VPN 会话，不会删除 `/etc/hosts`、Apollo 容器或容器内已经修复的 transform 元数据。
