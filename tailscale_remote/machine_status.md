# 本机 Tailscale 和 SSH 部署状态

检查日期：2026 年 10 月 25 日，Asia/Shanghai。

**当前状态：Tailscale 已安装并绑定账号上线，SSH 和 Tailscale 均已启用开机自启，本机通过 Tailscale 地址访问 SSH 检查通过，设备密钥过期已禁用。** 手机外网登录和重启后连接仍需验收。

| 项目 | 实际检查结果 |
| --- | --- |
| 系统 | Ubuntu 20.04.6 LTS，x86_64 |
| 主机名 | `mac-c` |
| Linux 登录用户 | `mac` |
| SSH | OpenSSH Server 已安装，TCP 22 已监听 |
| SSH 服务 | `ssh.service` 为 enabled 和 active |
| SSH 身份认证 | 本机 SSH 握手后提供 publickey、password；未保存或更改密码 |
| Tailscale | 1.104.2 已安装，`tailscaled.service` 为 enabled 和 active |
| Tailscale 账号 | 已绑定，`Running`，设备在线，健康提示为空 |
| TUN | `/dev/net/tun` 存在 |
| tmux | 已安装，版本 3.0a |
| 接通电源时空闲休眠 | GNOME `sleep-inactive-ac-type` 为 `nothing` |
| 官方控制面与软件源 | 当前网络不经桌面代理直连，HTTP 200 |
| 有线联网自动连接 | NetworkManager 的 `Profile 1` 已启用 autoconnect |
| Tailscale IPv4 | `100.123.75.64` |
| Tailscale DNS 名称 | `mac-c.tail0ca432.ts.net`；Termius 直接使用 IP |
| SSH 经 Tailscale 地址访问 | 已收到 `SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.13` 握手 |
| SSH 主机身份复核 | 经 `100.123.75.64` 获取的 ED25519 主机指纹与本地公钥一致 |
| 实际组网配置 | 不接管本机 DNS，不接收子网路由，未开启 Tailscale SSH，operator 为 `mac` |
| 设备密钥过期 | 已在后台禁用，并现场确认本机 `Self.KeyExpiry` 为空 |
| 手机外网登录 | 待使用手机移动数据验收 |
| 重启后远程登录 | 开机自启配置已检查，待择机重启验收 |

手机 Termius 填写地址 `100.123.75.64`、端口 `22`、用户名 `mac`，使用 Linux 用户密码登录。手机 Tailscale 需保持连接，并选择电脑所在的同一个 tailnet。

本次首次安装及浏览器绑定已经完成。以后在电脑本地需要重新认证时运行：

```bash
tailscale up --accept-dns=false --accept-routes=false --ssh=false --timeout=5m
```

随时重新运行检查：

```bash
bash /home/mac/macperson/computer_tools_backup/tailscale_remote/verify.sh
```

## SSH 主机公钥指纹

这些是 SSH 服务的公钥指纹，用于在手机首次连接时识别主机。

| 算法 | SHA256 指纹 |
| --- | --- |
| ED25519 | `SHA256:QrCReeXlzPjUXMpBBdviAmF2W6LIih0bc4Ur7WLU9c8` |
| ECDSA | `SHA256:8nJ1qyD6YDptOlJmdq1UuyAQbct5BmNfG+59LUWitEA` |
| RSA | `SHA256:YWhSLUWRWonvrn+nm1f3TE+gPRHrNynW8RXA+VH2NIE` |

重装系统或重新生成 SSH 主机密钥后，以上指纹需要更新。现场复核：

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub
ssh-keygen -lf /etc/ssh/ssh_host_rsa_key.pub
```
