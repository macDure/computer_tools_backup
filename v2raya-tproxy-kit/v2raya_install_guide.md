# v2rayA 2.4.6 + tproxy 透明代理排坑文档

适用环境：Ubuntu 24.04 / GNOME 桌面 / 需要系统级透明代理的场景。

最终结论：本机不要使用 v2rayA 的 `tun` / TinyTun 模式，稳定方案是 **v2rayA + tproxy**。

本机实测结果：

```text
v2rayA: 2.4.6
v2raya_core: 2.4.6 (xray-core)
透明代理实现: tproxy
GNOME 系统代理: none
Google: 可访问
Baidu: 可访问
Antigravity IDE: 可登录
Antigravity apt 仓库: 可更新
```

---

## 一、最终可用配置

v2rayA Web 设置中应保持以下配置：

```text
透明代理/系统代理: 启用
透明代理/系统代理实现方式: tproxy
局域网 IP 转发: 开启
路由模式 routeOnly: 关闭
GNOME 系统代理: none
```

通过 API 读取时应看到：

```json
{
  "transparent": "whitelist",
  "transparentType": "tproxy",
  "ipforward": true,
  "routeOnly": false
}
```

常用端口：

```text
v2rayA Web:        http://127.0.0.1:2017
v2rayA SOCKS:      127.0.0.1:20170
v2rayA HTTP:       127.0.0.1:20171
v2rayA rule HTTP:  127.0.0.1:20172
```

---

## 二、安装文件准备

本方案使用本地 deb 安装，不依赖 `apt.v2raya.org`。

原因：此前官方 apt 源曾出现 GPG key 过期问题，报错类似：

```text
EXPKEYSIG 354E516D494EF95F
```

本机使用的安装包：

```text
/home/mac/installer_debian_x64_2.4.6.deb
/home/mac/tinytun-v0.0.3-alpha.2-x86_64-unknown-linux-gnu.zip
```

如果迁移到新机器，先下载 v2rayA release 中的 Debian x64 安装包：

```bash
wget https://github.com/v2rayA/v2rayA/releases/download/v2.4.6/installer_debian_x64_2.4.6.deb
```

TinyTun 不是最终 tproxy 方案必须依赖的核心路径，但安装它不影响 tproxy，保留后续排查备用：

```bash
wget https://github.com/v2rayA/TinyTun/releases/download/v0.0.3-alpha.2/tinytun-v0.0.3-alpha.2-x86_64-unknown-linux-gnu.zip
```

---

## 三、干净安装步骤

先停止旧服务：

```bash
sudo systemctl stop v2raya.service || true
```

清理旧包：

```bash
sudo apt purge -y v2raya v2ray
sudo apt autoremove -y
```

安装 v2rayA：

```bash
sudo apt install -y ./installer_debian_x64_2.4.6.deb
```

安装 TinyTun 备用：

```bash
unzip -o tinytun-v0.0.3-alpha.2-x86_64-unknown-linux-gnu.zip
sudo install -m 0755 tinytun-x86_64-unknown-linux-gnu /usr/local/bin/tinytun
```

启动并设置开机自启：

```bash
sudo systemctl enable --now v2raya.service
```

确认版本：

```bash
v2raya --version
/usr/bin/v2raya_core version
```

期望结果：

```text
2.4.6
V2RAYA_CORE 2.4.6 (xray-core)
```

---

## 四、首次登录和导入节点

打开：

```text
http://127.0.0.1:2017
```

首次进入时创建 v2rayA Web 账号。

然后导入订阅或节点，选择一个节点连接到默认出站 `proxy`。

如果忘记 v2rayA Web 密码，可以重置账号：

```bash
sudo systemctl stop v2raya.service
sudo v2raya --config /etc/v2raya --reset-password
sudo systemctl start v2raya.service
```

重置后重新打开 Web 页面创建账号。

---

## 五、正确设置为 tproxy

### 方法一：Web 界面设置

进入 v2rayA Web：

```text
http://127.0.0.1:2017
```

设置项：

```text
Settings
Transparent Proxy / System Proxy: Enable
Transparent Proxy / System Proxy Implementation: tproxy
IP Forward: on
Save and Apply
```

然后点击主界面状态按钮启动代理，使状态变为 Running。

GNOME 系统代理必须关闭：

```bash
gsettings set org.gnome.system.proxy mode 'none'
```

### 方法二：脚本一键设置

本机已固化脚本：

```text
/home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

运行：

```bash
bash /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

脚本会执行：

```text
1. 确认 v2raya.service 已启动；如果服务未启动，会调用 sudo systemctl enable --now v2raya.service
2. 登录 v2rayA API
3. 将 transparentType 设置为 tproxy
4. 开启 transparent / ipforward
5. 启动 v2rayA core
6. 将 GNOME 系统代理设置为 none
7. 执行 Google、Baidu、Antigravity apt 仓库连通性测试
```

如果 v2raya.service 已经是 active，脚本不会触发 sudo。迁移到新机器首次运行时，如果服务尚未启动，终端会要求输入一次 sudo 密码。

首次迁移到新电脑时，需要在脚本里填入 v2rayA Web 的用户名和密码，或设置环境变量：

```bash
V2RAYA_USER='你的用户名' V2RAYA_PASS='你的密码' bash /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

---

## 六、为什么不用 tun

本机实测 `tun` 模式现象：

```text
v2rayA 服务能启动
v2raya_core 能启动
TinyTun 能启动
tun0 能创建
0.0.0.0/1 和 128.0.0.0/1 路由能创建
但是实际联网超时
```

失败测试：

```bash
curl --noproxy '*' -4 -I --max-time 12 https://www.google.com
curl --noproxy '*' -4 -I -x http://127.0.0.1:20171 --max-time 10 https://www.google.com
```

日志关键报错：

```text
SOCKS5 connect timed out
```

结论：这不是 v2rayA 没装好，也不是节点不可用，而是 TinyTun 数据面在当前系统环境下不稳定。禁用 v2rayA 的 IPv6 参数也没有解决，因为 TinyTun 生成配置里仍会出现：

```text
ipv6_mode: auto
```

因此本机最终放弃 `tun`，改用 `tproxy`。

---

## 七、验证命令

查看服务：

```bash
systemctl status v2raya --no-pager
```

查看端口：

```bash
ss -lntup | rg '2017|20170|20171|20172|52345'
```

期望看到：

```text
*:2017
127.0.0.1:20170
127.0.0.1:20171
127.0.0.1:20172
127.0.0.1:52345
```

确认 GNOME 系统代理关闭：

```bash
gsettings get org.gnome.system.proxy mode
```

期望：

```text
'none'
```

真实透明代理测试，不走环境变量代理：

```bash
curl --noproxy '*' -4 -I --max-time 8 https://www.google.com
curl --noproxy '*' -4 -I --max-time 8 https://www.baidu.com
```

期望：

```text
Google: HTTP/2 200
Baidu: HTTP/1.1 200 OK
```

测试 v2rayA 本地 HTTP 代理：

```bash
curl -x http://127.0.0.1:20171 -I --max-time 8 https://www.google.com
```

测试 Antigravity apt 仓库：

```bash
curl --noproxy '*' -4 -I --max-time 8 \
  https://us-central1-apt.pkg.dev/projects/antigravity-auto-updater-dev/dists/antigravity-debian/InRelease
```

期望：

```text
HTTP/2 200
```

---

## 八、apt 使用注意事项

使用 tproxy 后，不要再强制 apt 走 v2rayN 的 `10808`：

```bash
# 不推荐
sudo apt -o Acquire::http::Proxy="http://127.0.0.1:10808" update
```

推荐直接：

```bash
sudo apt update
```

如果必须显式指定代理，使用 v2rayA 的 HTTP 端口：

```bash
sudo apt \
  -o Acquire::http::Proxy="http://127.0.0.1:20171" \
  -o Acquire::https::Proxy="http://127.0.0.1:20171" \
  update
```

---

## 九、v2rayN 与 v2rayA 的关系

最终方案中，v2rayA 是主代理。

```text
v2rayA: 主代理，tproxy 透明代理
v2rayN: 可保留作备用，但不要让 GNOME 系统代理指向 10808
```

如果 GNOME 系统代理被改成 `manual` 且指向 `127.0.0.1:10808`，很多应用会绕过 v2rayA，重新依赖 v2rayN。

恢复 v2rayA 主代理：

```bash
gsettings set org.gnome.system.proxy mode 'none'
sudo systemctl start v2raya.service
bash /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

---

## 十、回滚到 v2rayN

如果 v2rayA 出问题，需要临时回到 v2rayN：

```bash
sudo systemctl stop v2raya.service

gsettings set org.gnome.system.proxy mode 'manual'
gsettings set org.gnome.system.proxy.http host '127.0.0.1'
gsettings set org.gnome.system.proxy.http port 10808
gsettings set org.gnome.system.proxy.https host '127.0.0.1'
gsettings set org.gnome.system.proxy.https port 10808
gsettings set org.gnome.system.proxy.socks host '127.0.0.1'
gsettings set org.gnome.system.proxy.socks port 10808
```

确保 v2rayN 的 xray 正在监听：

```bash
ss -lntup | rg '10808'
```

---

## 十一、常见问题

### 1. v2rayA 服务 active，但 20171 不存在

说明只是 Web 服务启动了，代理核心没有启动。

解决：

```bash
bash /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

### 2. apt 卡在 127.0.0.1:10808

说明命令或环境变量强制 apt 走 v2rayN。

解决：

```bash
sudo apt update
```

不要加：

```bash
-o Acquire::http::Proxy="http://127.0.0.1:10808"
```

### 3. Antigravity IDE 无法登录

先确认：

```bash
gsettings get org.gnome.system.proxy mode
curl --noproxy '*' -4 -I --max-time 8 https://www.google.com
```

期望：

```text
'none'
HTTP/2 200
```

如果这两个正常，Antigravity IDE 登录应正常。

### 4. 误切回 tun 后断网

进入 v2rayA Web，把透明代理实现方式改回：

```text
tproxy
```

或者直接运行：

```bash
bash /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

### 5. 浏览器不能访问外网，但新终端 curl 可以

现象：

```text
浏览器打不开 https://www.google.com
新建终端执行 curl -L https://www.google.com 可以访问
关闭 v2rayA 代理后，旧终端连正常网络也不能访问
重新打开一个新终端又正常
```

原因不是单一的“节点坏了”，而是不同进程持有的网络状态不一致：

```text
浏览器是长期运行进程，会缓存 DNS、HTTP/2/QUIC 连接、代理配置、DoH 状态和失败连接状态
旧终端可能继承了旧的 http_proxy / https_proxy / all_proxy 环境变量
新终端是新进程，读取的是当前系统网络状态，所以 curl 可能正常
```

v2rayA tproxy 本身不依赖 GNOME 系统代理，推荐状态是：

```text
GNOME proxy mode: none
v2rayA tproxy: running
v2rayN: 保留备用，但不要抢系统代理
```

检查旧终端和新终端是否有代理环境变量：

```bash
env | grep -i proxy
```

如果旧终端里有这些变量：

```text
http_proxy
https_proxy
all_proxy
HTTP_PROXY
HTTPS_PROXY
ALL_PROXY
```

而代理已经关闭，这个旧终端里的 curl 仍会尝试走已经不可用的代理端口，表现为连正常网络也失败。

临时修复旧终端：

```bash
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
```

本机已固化 source 脚本：

```bash
source /home/mac/v2raya-tproxy-kit/scripts/proxy_env.sh
```

它会提供几个命令：

```text
proxy-show    查看当前终端里的代理环境变量
proxy-off     清理当前终端里的代理环境变量
proxy-v2raya  将当前终端显式切到 v2rayA: HTTP 20171 / SOCKS 20170
proxy-v2rayn  将当前终端显式切到 v2rayN: 10808
proxy-auto    根据当前终端已有代理变量自动检查端口，失效则清理
```

新开的 bash 终端会自动加载这个脚本。自动检查逻辑：

```text
当前终端代理变量指向 127.0.0.1:10808：
  如果 10808 正在监听，保留 v2rayN 环境变量
  如果 10808 没有监听，自动清理

当前终端代理变量指向 127.0.0.1:20171 或 127.0.0.1:20170：
  如果 v2rayA 代理端口正在监听，保留 v2rayA 环境变量
  如果 v2rayA 代理端口没有监听，自动清理

当前终端没有代理环境变量：
  保持不变，因为 v2rayA tproxy 模式不需要终端代理变量
```

旧终端不会自动重新读取 `.bashrc`，需要手动执行：

```bash
source ~/.bashrc
```

或者直接清理：

```bash
proxy-off
```

浏览器卡住时，最快处理是重启浏览器，或至少关闭相关标签页后重新打开。浏览器可能还在使用旧连接池或旧 DNS/DoH 结果，不一定会立刻跟随 v2rayA 开关状态。

使用建议：不要频繁关闭/打开 v2rayA 透明代理。更稳的方式是保持 v2rayA 开启，用规则/direct 控制直连，而不是反复关掉整个代理。频繁开关会让 tproxy 规则、DNS、浏览器连接池和终端环境变量出现半新半旧的状态。

---


---

## 十二、2026-07-05 重启后失效的根因与修复

重启后现象：

```text
v2raya.service 是 active
但 v2raya_core 没有运行
20170 / 20171 / 20172 / 52345 没有监听
GNOME 系统代理被 v2rayN 改回 manual -> 127.0.0.1:10808
v2rayA 不能上网，需要挂着 v2rayN 才能联网
```

进一步排查发现：v2rayA 和 v2rayN 表面上使用同一个 Shadowsocks 节点地址端口，但 v2rayA 里保存的是旧密码，v2rayN 里是更新后的可用密码。

验证方式是不打印密码，只比较哈希和长度：

```text
v2rayA SS password length: 12
v2rayN SS password length: 10
same password: false
```

所以 v2rayA 的 TCP 能连到节点服务器，但 Shadowsocks 认证不匹配，表现为：

```text
HTTP/1.1 200 Connection established
随后超时
```

修复方式：

```text
1. 从 v2rayN 当前运行配置 /home/mac/v2rayN-linux-64/guiConfigs/config.json 读取可用 Shadowsocks 节点
2. 通过 v2rayA /api/import 覆盖 v2rayA 第 1 个节点
3. 设置 transparentType=tproxy
4. 启动 v2rayA core
5. 设置 GNOME proxy mode 为 none
```

这些步骤已经固化到：

```text
/home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

脚本现在会自动执行：

```text
Synced current Shadowsocks node from v2rayN config.
v2rayA running: true
networkPaused: false
GNOME proxy mode: 'none'
Google direct test: OK
Baidu direct test: OK
Antigravity apt repo test: OK
```

为避免下次重启后只启动 v2rayA Web 而不启动 core/tproxy，已创建用户级 systemd 服务：

```text
/home/mac/.config/systemd/user/v2raya-tproxy-setup.service
```

启用命令：

```bash
systemctl --user enable v2raya-tproxy-setup.service
```

手动运行：

```bash
systemctl --user start v2raya-tproxy-setup.service
```

查看状态：

```bash
systemctl --user status v2raya-tproxy-setup.service --no-pager
```

当前已验证该服务运行成功，登录后会自动运行 `v2raya_set_tproxy.sh`。

### 2026-07-06 再次重启后失效

这次现象：

```text
v2raya.service: active
v2rayA Web: 127.0.0.1:2017 正常
v2rayA API /api/touch: running=false
v2raya_core: 未运行
20170 / 20171 / 20172: 未监听
GNOME 系统代理: manual -> 127.0.0.1:10808
v2rayN: 10808 正常，仍可作为备用对话通道
```

直接原因：用户级 `v2raya-tproxy-setup.service` 上次启动时脚本已经把 v2rayA core 拉起来了，但最后的 Google/Baidu/Antigravity 连通性测试中某次 DNS 解析超时，脚本因为 `set -e` 退出，systemd 将服务标记为 failed。后续 v2rayA core 又没有保持 running，最终只剩 Web 服务还活着。

修复：

```text
1. 手动执行 /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh 恢复当前网络
2. 修改脚本：v2rayA running=false 才退出失败；外部网站连通性测试失败只输出 WARN
3. 修改用户级 systemd 服务：登录后延迟 8 秒执行，失败后 15 秒重试，最多 5 次
4. systemctl --user daemon-reload 后重新验证服务执行成功
```

验证结果：

```text
v2rayA API running: true
networkPaused: false
20170 / 20171 / 20172: 已监听
curl --noproxy '*' https://www.google.com: HTTP 200
curl -x http://127.0.0.1:20171 https://www.google.com: HTTP 200
GNOME 系统代理: none
```

注意：v2rayN 的 `guiConfigs/guiNConfig.json` 中 `SystemProxyItem.SysProxyType=1` 会把 GNOME 系统代理设回 `127.0.0.1:10808`。这不等于 v2rayA core 失败，但会让部分桌面应用继续走 v2rayN。如果目标是完全使用 v2rayA tproxy，应在 v2rayN UI 里关闭“系统代理”，保留 v2rayN 作为手动备用即可。

### 2026-07-07 重启后仍不能代理外网

这次现象：

```text
v2raya.service: active
v2raya_core: running
20170 / 20171 / 20172 / 52345: 已监听
用户级 v2raya-tproxy-setup.service: SUCCESS
但 v2rayA 的 20171 / 20170 访问 Google 超时
v2rayN 的 10808 访问 Google 正常
```

最终根因：v2rayA 和 v2rayN 看起来使用同一个 Shadowsocks 服务器 `97.64.17.52:26328`，但密码并不一致。

不打印密码的验证结果：

```text
v2rayA password length: 12
v2rayN password length: 10
password sha256: 不一致
```

所以 v2rayA 能连到节点服务器，但 Shadowsocks 认证失败，表现为：

```text
HTTP/1.1 200 Connection established
随后超时
```

修复方式：重新从 v2rayN 当前运行配置导入节点到 v2rayA 后，密码哈希一致，v2rayA 立刻恢复：

```text
v2rayA HTTP proxy Google test: OK
Google tproxy test: OK
Baidu tproxy test: OK
Antigravity apt repo tproxy test: OK
```

已修复脚本逻辑：

```text
1. /api/import 后必须检查返回 code=SUCCESS
2. 启动 v2rayA core 后，必须用 127.0.0.1:20171 访问 Google 成功
3. 如果 v2rayA HTTP 代理测试失败，脚本直接失败，不再假装配置成功
```

同时关闭了 v2rayN 自动设置系统代理：

```json
"SystemProxyItem": {
  "SysProxyType": 0
}
```

原因：此前 v2rayN 会把 GNOME 系统代理改回 `manual -> 127.0.0.1:10808`，导致桌面应用到底走 v2rayA 还是 v2rayN 变得混乱。保留 v2rayN 作为备用代理，但不再让它抢系统代理。

### 2026-07-10 手工 server 能 ping 但不能代理上网

这次现象：

```text
v2rayA 中手工设置了一个 server
UI 里 ping 能通
v2raya.service 和 v2raya_core 都在运行
20170 / 20171 / 20172 / 52345 都已监听
但 v2rayA 代理访问外网失败
v2rayN 代理仍可访问外网，并被用作当前对话通道
```

关键结论：**ping 通不代表代理可用**。ping 或延迟测试只能证明 `IP:端口` 网络可达，不能证明 Shadowsocks / VMess 的认证参数正确。

本次实际问题是 v2rayA 和 v2rayN 看起来使用同一个节点地址：

```text
97.64.23.19:26328
SS(aes-256-gcm)
```

但密码不一致：

```text
v2rayA password_len: 12
v2rayN password_len: 10
sha256: 不一致
```

因此 v2rayA 能连到节点服务器，甚至 UI ping 看起来正常，但真正代理流量时 Shadowsocks 认证失败，表现为 HTTP/SOCKS 代理超时。

正确的诊断方式是不要相信普通 `curl`，因为当前终端可能继承 v2rayN 的代理环境变量：

```text
http_proxy=http://127.0.0.1:10808/
https_proxy=http://127.0.0.1:10808/
all_proxy=socks://127.0.0.1:10808/
```

这种情况下，普通 `curl https://www.google.com` 测到的是 v2rayN，不是 v2rayA。要清除环境变量后再测：

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  curl -x http://127.0.0.1:20171 -I --max-time 12 https://www.google.com

env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  curl -x socks5h://127.0.0.1:20170 -I --max-time 12 https://www.google.com
```

对比 v2rayA 和 v2rayN 当前节点密码时，不打印明文，只比较哈希：

```bash
sudo jq -r '.outbounds[] | select(.tag=="proxy") | .settings.servers[0].password' /etc/v2raya/config.json | sha256sum
jq -r '.outbounds[] | select(.tag=="proxy") | .settings.servers[0].password' /home/mac/v2rayN-linux-64/guiConfigs/config.json | sha256sum
```

修复方式：重新运行同步脚本，把 v2rayN 当前可用节点覆盖到 v2rayA：

```bash
bash /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

修复后验证结果：

```text
v2rayA 和 v2rayN 密码 sha256 一致
v2rayA password_len: 10
v2rayA HTTP 代理 127.0.0.1:20171 -> Google OK
v2rayA SOCKS 代理 127.0.0.1:20170 -> Google OK
```

本次还发现一个独立问题：系统 DNS 对 Google 解析仍然污染/超时：

```text
resolvectl query www.google.com
耗时约 14 秒
返回 2001::1 / 157.240.7.20 等异常地址
```

所以即使 v2rayA 的 HTTP/SOCKS 代理已恢复，透明代理路径和浏览器仍可能因为系统 DNS 污染/超时而表现不稳定。后续若继续排障，应单独处理 DNS 路径，而不是继续反复改 server。


---

## 十三、UI 无法输入订阅地址时的导入方法

问题现象：v2rayA Web UI 页面里无法成功输入或提交订阅地址。

解决方法：绕过 UI，直接调用 v2rayA 本地 API `/api/import` 导入订阅。

已固化脚本：

```text
/home/mac/v2raya-tproxy-kit/scripts/v2raya_import_subscription.sh
```

推荐用法：不要把订阅地址直接写在命令行历史里，而是临时放到文件：

```bash
nano /tmp/v2raya-sub.txt
# 粘贴订阅地址并保存

cat /tmp/v2raya-sub.txt | /home/mac/v2raya-tproxy-kit/scripts/v2raya_import_subscription.sh
rm -f /tmp/v2raya-sub.txt
```

也可以直接传参：

```bash
/home/mac/v2raya-tproxy-kit/scripts/v2raya_import_subscription.sh 'https://your-subscription-url'
```

脚本会执行：

```text
1. 登录 v2rayA API
2. POST /api/import 导入订阅地址
3. 查询 /api/touch 验证订阅和节点数量
```

本次实测结果：

```text
Subscription import: OK
Subscriptions: 1
Standalone servers: 1
订阅内节点数: 6
v2rayA running: true
networkPaused: false
```

注意：导入订阅后，v2rayA 不会自动切换到订阅里的新节点。本次导入后当前连接仍是原来的独立节点：

```text
_type: server
id: 1
outbound: proxy
```

如果 UI 选择订阅节点也不好用，可以继续通过 API 列出订阅里的节点并连接指定节点。

### v2rayA 更新订阅不走代理的坑

现象：系统里浏览器、Antigravity、apt 都能通过 v2rayA tproxy 上网，但 v2rayA Web 页面里点“更新订阅”仍然失败。

原因：更新订阅这个请求是 `v2raya` 服务进程自己发起的，不一定会走它自己创建的 tproxy 透明代理。透明代理通常需要排除代理程序自身，例如：

```text
v2raya
v2raya_core
xray
tinytun
```

如果不排除，可能出现自引用回环：

```text
v2rayA 更新订阅
-> 请求被 v2rayA tproxy 捕获
-> 交给 v2rayA core 代理
-> core 自己的连接再次被捕获
-> 循环或异常
```

所以会出现：

```text
普通应用走 tproxy 正常
v2rayA 自己更新订阅不走代理或更新失败
```

推荐做法：不要依赖 v2rayA Web UI 自己更新订阅。更稳的路径是二选一：

```text
1. 用 /home/mac/v2raya-tproxy-kit/scripts/v2raya_import_subscription.sh 通过本地 API 导入订阅
2. 用 v2rayN 更新订阅，再运行 /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh，把 v2rayN 当前可用节点同步到 v2rayA
```

理论上可以给 `v2raya.service` 加代理环境变量：

```ini
Environment=http_proxy=http://127.0.0.1:20171
Environment=https_proxy=http://127.0.0.1:20171
```

但不推荐作为默认方案。原因是 v2rayA 启动早期 `20171` 可能还没起来，而且容易引入自引用问题。当前方案定位是：v2rayA 负责 tproxy 接管系统流量，订阅更新交给 v2rayN 或 API 脚本处理。


---

## 十四、v2rayA Web 账号密码的坑

v2rayA 没有固定的官方默认账号密码。

容易误解的点：

```text
admin / v2raya_admin 不是 v2rayA 官方默认账号
这些账号通常来自之前的手工初始化、脚本创建或排障过程
```

### 1. `--reset-password` 的真实含义

命令：

```bash
sudo v2raya --config /etc/v2raya --reset-password
```

它不是把密码改成某个默认值，而是重置/清空账号状态。之后必须重新通过 Web UI 或 `/api/account` 创建账号。

### 2. 账号库位置

当前 systemd 服务使用的配置目录是：

```text
/etc/v2raya
```

账号数据库也在这个目录里。

如果用不同启动方式或不同 `--config` 参数启动 v2rayA，就可能读到另一套账号库，表现为：

```text
昨天账号能登录，今天提示用户名或密码错误
```

### 3. 脚本账号必须和数据库账号一致

`/home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh` 里固化了默认登录账号：

```text
username = macp
password = mac6833773
```

这只是脚本默认使用的登录参数，不会自动修改 v2rayA 数据库里的账号。

如果数据库里的真实账号不是 `macp`，脚本登录就会失败。因此一旦账号混乱，应执行一次账号重置并重新创建 `macp`。

### 4. 当前固定账号

当前已将 v2rayA Web 账号统一为：

```text
username: macp
password: mac6833773
```

凭据文件：

```text
/home/mac/v2raya-tproxy-kit/credentials/v2raya-web-credentials.txt
```

该文件权限应为：

```text
600
```

### 5. 账号重置标准流程

如果再次出现 UI 登录提示用户名或密码错误，按下面流程修复：

```bash
sudo systemctl stop v2raya.service
sudo v2raya --config /etc/v2raya --reset-password
sudo systemctl start v2raya.service
```

然后创建账号：

```bash
curl -sS -H 'Content-Type: application/json'   -d '{"username":"macp","password":"mac6833773"}'   http://127.0.0.1:2017/api/account
```

更新凭据文件：

```bash
cat > /home/mac/v2raya-tproxy-kit/credentials/v2raya-web-credentials.txt <<'EOF'
username=macp
password=mac6833773
EOF
chmod 600 /home/mac/v2raya-tproxy-kit/credentials/v2raya-web-credentials.txt
```

最后恢复 tproxy：

```bash
bash /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

### 6. 安全注意

当前为了迁移方便，密码同时存在于脚本、文档和凭据文件中。单用户本机使用问题不大；如果迁移到多人机器，建议改成只放在 `600` 权限的凭据文件里，不要写入文档。

## 十五、附录：v2raya_set_tproxy.sh 完整脚本

脚本文件路径：

```text
/home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

完整内容如下：

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${V2RAYA_BASE_URL:-http://127.0.0.1:2017}"
USER_NAME="${V2RAYA_USER:-macp}"
PASSWORD="${V2RAYA_PASS:-mac6833773}"
CRED_FILE="${V2RAYA_CRED_FILE:-/home/mac/v2raya-tproxy-kit/credentials/v2raya-web-credentials.txt}"
V2RAYN_CONFIG="${V2RAYN_CONFIG:-/home/mac/v2rayN-linux-64/guiConfigs/config.json}"

if [[ -z "$USER_NAME" || -z "$PASSWORD" ]]; then
  if [[ -r "$CRED_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CRED_FILE"
    USER_NAME="${USER_NAME:-${username:-}}"
    PASSWORD="${PASSWORD:-${password:-}}"
  fi
fi

if [[ -z "$USER_NAME" || -z "$PASSWORD" ]]; then
  echo "Missing v2rayA credentials. Set V2RAYA_USER and V2RAYA_PASS, or create $CRED_FILE." >&2
  exit 1
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 1; }
}

need_cmd curl
need_cmd jq
need_cmd systemctl
need_cmd gsettings
need_cmd python3

if ! systemctl is-active --quiet v2raya.service; then
  sudo systemctl enable --now v2raya.service >/dev/null
fi

login_v2raya() {
  local user="$1"
  local pass="$2"
  local payload resp token
  payload=$(jq -n --arg username "$user" --arg password "$pass" '{username:$username,password:$password}')
  resp=$(curl -sS --max-time 8 -H 'Content-Type: application/json' -d "$payload" "$BASE_URL/api/login")
  token=$(printf '%s' "$resp" | jq -r '.data.token // empty')
  if [[ -n "$token" && "$token" != "null" ]]; then
    printf '%s' "$token"
    return 0
  fi
  return 1
}

token=""
if token=$(login_v2raya "$USER_NAME" "$PASSWORD"); then
  :
elif [[ -r "$CRED_FILE" ]]; then
  # Fall back to the currently valid local credentials if the hardcoded defaults do not match this machine.
  # shellcheck disable=SC1090
  source "$CRED_FILE"
  USER_NAME="${username:-$USER_NAME}"
  PASSWORD="${password:-$PASSWORD}"
  token=$(login_v2raya "$USER_NAME" "$PASSWORD") || true
fi

if [[ -z "$token" ]]; then
  echo "Failed to log in to v2rayA API with hardcoded credentials and $CRED_FILE." >&2
  exit 1
fi

# If v2rayN has a working Shadowsocks proxy outbound, sync it into v2rayA.
# This prevents stale v2rayA node passwords after subscription updates in v2rayN.
if [[ -r "$V2RAYN_CONFIG" ]]; then
  python3 - "$V2RAYN_CONFIG" >/tmp/v2raya_import_payload.json <<'END_PY'
import base64
import json
import pathlib
import sys
import urllib.parse

cfg = json.loads(pathlib.Path(sys.argv[1]).read_text())
server = None
for outbound in cfg.get("outbounds", []):
    if outbound.get("tag") == "proxy" and outbound.get("protocol") == "shadowsocks":
        servers = outbound.get("settings", {}).get("servers", [])
        if servers:
            server = servers[0]
            break

if not server:
    raise SystemExit(0)

method = server.get("method")
password = server.get("password")
address = server.get("address")
port = server.get("port")
if not all([method, password, address, port]):
    raise SystemExit(0)

userinfo = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
name = urllib.parse.quote(f"v2rayN-current@{address}:{port}")
url = f"ss://{userinfo}@{address}:{port}#{name}"
print(json.dumps({"url": url, "which": {"id": 1, "_type": "server", "sub": 0}}, ensure_ascii=False))
END_PY

  if [[ -s /tmp/v2raya_import_payload.json ]]; then
    import_resp=$(curl -fsS --max-time 20 -X POST \
      -H "Authorization: $token" \
      -H 'Content-Type: application/json' \
      --data-binary @/tmp/v2raya_import_payload.json \
      "$BASE_URL/api/import")
    import_code=$(printf '%s' "$import_resp" | jq -r '.code // empty')
    if [[ "$import_code" != "SUCCESS" ]]; then
      printf 'Failed to sync current Shadowsocks node from v2rayN config: %s\n' "$import_resp" >&2
      exit 1
    fi
    printf 'Synced current Shadowsocks node from v2rayN config.\n'
  fi
fi

setting_resp=$(curl -fsS --max-time 8 -H "Authorization: $token" "$BASE_URL/api/setting")
printf '%s' "$setting_resp" \
  | jq '.data.setting
      | .transparent="whitelist"
      | .transparentType="tproxy"
      | .ipforward=true
      | .routeOnly=false' \
  > /tmp/v2raya-setting-tproxy.json

curl -fsS --max-time 15 -X PUT \
  -H "Authorization: $token" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/v2raya-setting-tproxy.json \
  "$BASE_URL/api/setting" >/dev/null

curl -fsS --max-time 20 -X POST -H "Authorization: $token" "$BASE_URL/api/v2ray" >/dev/null

gsettings set org.gnome.system.proxy mode 'none'

sleep 3

status=$(curl -fsS --max-time 8 -H "Authorization: $token" "$BASE_URL/api/touch")
running=$(printf '%s' "$status" | jq -r '.data.running')
network_paused=$(printf '%s' "$status" | jq -r '.data.networkPaused')
proxy_mode=$(gsettings get org.gnome.system.proxy mode)

printf 'v2rayA running: %s\n' "$running"
printf 'networkPaused: %s\n' "$network_paused"
printf 'GNOME proxy mode: %s\n' "$proxy_mode"

if [[ "$running" != "true" || "$network_paused" == "true" ]]; then
  echo "v2rayA core did not enter a usable running state." >&2
  exit 1
fi

require_proxy_url() {
  local name="$1"
  local url="$2"

  if curl -x http://127.0.0.1:20171 -4 -fsSI --max-time 12 "$url" >/dev/null; then
    printf '%s test: OK\n' "$name"
  else
    printf '%s test: FAIL, v2rayA HTTP proxy cannot reach this URL. The selected node is probably stale or unusable.\n' "$name" >&2
    exit 1
  fi
}

check_url() {
  local name="$1"
  local url="$2"

  if curl --noproxy '*' -4 -fsSI --max-time 10 "$url" >/dev/null; then
    printf '%s test: OK\n' "$name"
  else
    printf '%s test: WARN, v2rayA is running but this connectivity check failed.\n' "$name" >&2
  fi
}

require_proxy_url "v2rayA HTTP proxy Google" "https://www.google.com"
check_url "Google tproxy" "https://www.google.com"
check_url "Baidu tproxy" "https://www.baidu.com"
check_url "Antigravity apt repo tproxy" "https://us-central1-apt.pkg.dev/projects/antigravity-auto-updater-dev/dists/antigravity-debian/InRelease"

printf 'Done. v2rayA is configured for tproxy.\n'
```

---

## 十六、附录：v2raya_import_subscription.sh 完整脚本

脚本文件路径：

```text
/home/mac/v2raya-tproxy-kit/scripts/v2raya_import_subscription.sh
```

完整内容如下：

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${V2RAYA_BASE_URL:-http://127.0.0.1:2017}"
USER_NAME="${V2RAYA_USER:-macp}"
PASSWORD="${V2RAYA_PASS:-mac6833773}"
CRED_FILE="${V2RAYA_CRED_FILE:-/home/mac/v2raya-tproxy-kit/credentials/v2raya-web-credentials.txt}"
SUB_URL="${1:-}"

if [[ -z "$SUB_URL" && ! -t 0 ]]; then
  SUB_URL="$(cat | tr -d '\r\n')"
fi

if [[ -z "$SUB_URL" ]]; then
  echo "Usage:" >&2
  echo "  $0 'https://your-subscription-url'" >&2
  echo "  cat sub-url.txt | $0" >&2
  exit 1
fi

if [[ -r "$CRED_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CRED_FILE"
  USER_NAME="${username:-$USER_NAME}"
  PASSWORD="${password:-$PASSWORD}"
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 1; }
}

need_cmd curl
need_cmd jq
need_cmd systemctl

if ! systemctl is-active --quiet v2raya.service; then
  sudo systemctl enable --now v2raya.service >/dev/null
fi

payload=$(jq -n --arg username "$USER_NAME" --arg password "$PASSWORD" '{username:$username,password:$password}')
login_resp=$(curl -fsS --max-time 8 -H 'Content-Type: application/json' -d "$payload" "$BASE_URL/api/login")
token=$(printf '%s' "$login_resp" | jq -r '.data.token // empty')

if [[ -z "$token" || "$token" == "null" ]]; then
  echo "Failed to log in to v2rayA API." >&2
  exit 1
fi

import_payload=$(jq -n --arg url "$SUB_URL" '{url:$url}')
import_resp=$(curl -fsS --max-time 60 -X POST \
  -H "Authorization: $token" \
  -H 'Content-Type: application/json' \
  -d "$import_payload" \
  "$BASE_URL/api/import")

code=$(printf '%s' "$import_resp" | jq -r '.code')
message=$(printf '%s' "$import_resp" | jq -r '.message // empty')
if [[ "$code" != "SUCCESS" ]]; then
  echo "Import failed: $message" >&2
  printf '%s\n' "$import_resp" >&2
  exit 1
fi

touch_resp=$(curl -fsS --max-time 8 -H "Authorization: $token" "$BASE_URL/api/touch")
servers=$(printf '%s' "$touch_resp" | jq -r '.data.touch.servers | length')
subs=$(printf '%s' "$touch_resp" | jq -r '.data.touch.subscriptions | length')

printf 'Subscription import: OK\n'
printf 'Subscriptions: %s\n' "$subs"
printf 'Standalone servers: %s\n' "$servers"
```
