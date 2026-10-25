# 安卓手机通过 Tailscale 和 Termius 登录家中 Linux

本方案让安卓手机在外使用移动数据或其他 Wi-Fi，登录家中 `mac-c` 电脑的 Linux 终端。家中不需要公网 IP，也不需要路由器端口转发。Tailscale 提供账号管理、设备组网和加密中继；Termius 提供手机上的 SSH 终端。

**本机已安装并上线，Termius 地址为 `100.123.75.64`，端口 `22`，用户名 `mac`。** SSH 和 Tailscale 均已设置开机自启，设备密钥过期已禁用。详细检查结果见 [本机部署状态](machine_status.md)；首次部署和以后迁移的流程如下。

## 方案和费用

连接路径是：安卓 Termius → 安卓 Tailscale → 加密私有网络 → 家中电脑 Tailscale → OpenSSH 22 端口 → Linux 用户 `mac`。

Tailscale 优先建立设备间直连；无法直连时，使用官方 DERP 云中继转发已经加密的数据。这里使用的是 Tailscale 提供的云服务，无须另租服务器。手机也必须加入同一个 Tailscale 网络，才能访问电脑的 `100.x.x.x` 私有地址。[官方中继说明](https://tailscale.com/docs/reference/derp-servers)

个人使用可选择 Tailscale Personal 免费方案；Termius Starter 免费方案包含本地保存主机和 SSH，足以完成本方案。Termius 的跨设备云同步属于其他付费方案，与 Tailscale 的组网账号独立。[Tailscale 价格](https://tailscale.com/pricing) · [Termius 价格](https://termius.com/pricing)

## 在电脑上完成首次部署

在这台电脑上以 `mac` 用户打开终端，运行：

```bash
bash /home/mac/macperson/computer_tools_backup/tailscale_remote/setup.sh
```

1. 输入本机 sudo 密码。终端输入密码时不显示字符，正常输入后回车。
2. 脚本从 Tailscale 官方稳定版 APT 源安装软件，并启用 `ssh.service` 和 `tailscaled.service`。
3. 打开终端输出的登录链接，使用自己的 Tailscale 账号登录并批准添加这台电脑。安卓手机之后要使用同一账号、同一个 tailnet。
4. 等脚本输出 `Termius 地址：100.x.x.x`，记录这个**实际地址**；文档中的 `100.x.x.x` 只是占位符。
5. 打开 [Tailscale 设备管理](https://login.tailscale.com/admin/machines)，找到这台电脑，在右侧菜单选择 **Disable Key Expiry**。对长期无人值守的电脑禁用设备密钥过期，可避免日后到期需要重新登录；这也意味着该设备保持授权，直到你撤销或移除它。[官方说明](https://tailscale.com/docs/features/access-control/key-expiry)

脚本保留终端现有 HTTP 代理供下载使用；后台 `tailscaled` 不依赖桌面代理。它将 `mac` 设置为本机 Tailscale operator，使该用户可以完成登录和管理本机组网。启用 UFW 的机器会额外允许 `tailscale0` 上的 TCP 22 入站。

本方案通过 Tailscale 网络使用现有 OpenSSH：`--ssh=false` 关闭的是 Tailscale 自带的另一套 SSH 身份认证，Termius 仍使用 Linux 密码或 SSH 密钥登录。`--accept-dns=false` 和 `--accept-routes=false` 保留本机已有 DNS 与公司内网路由；手机直接填写电脑的 Tailscale IP。

安装依据：[官方 Ubuntu 20.04 稳定版软件源](https://pkgs.tailscale.com/stable/#ubuntu-focal) · [Linux 安装说明](https://tailscale.com/docs/install/linux)。

### 登录超时或中途退出后继续

如果已经安装好，只是浏览器授权没完成，可运行下面的命令重新取得登录链接，无须重装：

```bash
tailscale up --accept-dns=false --accept-routes=false --ssh=false --timeout=5m
bash /home/mac/macperson/computer_tools_backup/tailscale_remote/verify.sh
```

如果提示无操作权限，先在本机运行：

```bash
sudo tailscale set --operator=mac
```

## 安卓手机下载安装

| App | 用途 | 官方下载 |
| --- | --- | --- |
| Tailscale | 让手机加入电脑所在的私有网络 | [Google Play](https://play.google.com/store/apps/details?id=com.tailscale.ipn) · [官方 Android 安装说明](https://tailscale.com/docs/install/android) |
| Termius | SSH 终端客户端 | [Google Play](https://play.google.com/store/apps/details?id=com.server.auditor.ssh.client) · [官方 Android 页面](https://www.termius.com/free-ssh-client-for-android) |

没有 Google Play 时，可在 [Tailscale 官方稳定版下载页](https://pkgs.tailscale.com/stable/#android) 下载 Android 通用 APK；该 APK 需要自己更新。Termius 优先使用官网指向的官方商店渠道。

### 先连接手机 Tailscale

1. 打开 Tailscale，按提示允许 Android VPN 配置。
2. 登录电脑绑定时使用的同一账号，并确认选中了同一个 tailnet。
3. 打开连接开关，确认列表中能看到 `mac-c` 或电脑实际显示的设备名，状态为在线。
4. 将 Tailscale 的电池设置改为允许后台运行或不受限制；部分品牌手机还需要允许自启动。

Android 同一用户通常只能维持一个 VPN 服务。如果手机正在运行 Clash、v2rayNG、公司 VPN 等使用 Android VPN 的 App，需要切换到 Tailscale 后再连接终端。[Android VPN 官方说明](https://developer.android.com/develop/connectivity/vpn)

### 再配置 Termius

打开 Termius 的 Hosts，点加号添加主机。界面名称可能随 App 版本略有变化，填写以下字段：

| 字段 | 填写内容 |
| --- | --- |
| Label 名称 | 家里 Linux |
| Address 地址 | 本机为 `100.123.75.64`；换电脑后以 `tailscale ip -4` 或手机设备列表的实际地址为准 |
| Port 端口 | `22` |
| Username 用户名 | `mac` |
| Password 密码 | 这台 Linux 上 `mac` 用户的登录密码 |
| Protocol 协议 | SSH |

Tailscale 的账号负责组网；这里的用户名和密码属于 Linux。保存后连接，首次会提示 SSH 主机指纹，核对 [本机部署状态](machine_status.md) 中相应算法的指纹后接受。

成功后应看到这台电脑的 Shell。可运行 `hostname` 和 `whoami`，分别确认主机为 `mac-c`、用户为 `mac`。

### 可选的手机密钥登录

先完成密码登录，再在 Termius 的 Keychain 中生成一个专用于手机的 SSH 密钥，将其公钥追加到电脑的 `/home/mac/.ssh/authorized_keys`，最后在主机配置中选择该密钥。公钥形如 `ssh-ed25519 AAAA... android-termius`；私钥留在手机端，给私钥设置口令并使用手机解锁保护。

本方案没有修改已有的 SSH 密码或密钥设置。已有 [SSH 公钥登录指南](../ssh_passwordless_login_guide.md) 可供参考；不要把密码、手机私钥或 Tailscale 登录凭据放入 Git 仓库。

## 手机上继续使用终端任务

本机已有 tmux。长时间任务可放在 tmux 会话中，手机断网后重新连接还能继续查看：

```bash
tmux new-session -A -s phone
```

在会话内执行平时的 Shell 命令。暂时离开时依次按 `Ctrl+b`、`d`，下次连接后再次执行上面的命令即可。tmux 可保留网络断开期间的进程；电脑重启会终止当时的进程。原有配置见 [tmux 说明](../tmux_setup/README.md)。

## 开机自启和验收

完成首次绑定后，`tailscaled` 会在 `/var/lib/tailscale` 保存本机状态，后续随系统启动自动连接；SSH 也随系统启动，无须每天执行 `tailscale up`，不依赖桌面用户登录。

要从手机连上，电脑必须已启动、保持联网且未休眠。如果系统盘使用启动前解密，需要先完成解锁。本机检查时接通电源的 GNOME 空闲休眠设置为 `nothing`；手动休眠或关机后仍无法登录。

在电脑上检查：

```bash
bash /home/mac/macperson/computer_tools_backup/tailscale_remote/verify.sh
```

正常应看到两个服务均为 `enabled` 和 `active`、Tailscale 状态 `Running`，以及 Tailscale IP 上的 SSH 握手通过。这个检查只验证本机条件，还需用手机完成外网验收：

1. 手机关闭 Wi-Fi，使用 4G 或 5G，保持 Tailscale 在线。
2. 在 Termius 中连接，执行 `hostname`、`whoami`。
3. 在自己方便时重启电脑；等系统联网后，再用手机连接，确认开机后无需手动启动服务。

维护命令：

```bash
systemctl is-enabled ssh tailscaled
systemctl is-active ssh tailscaled
tailscale status
tailscale ip -4
tailscale netcheck
sudo journalctl -u tailscaled -b -n 80 --no-pager
sudo journalctl -u ssh -b -n 50 --no-pager
```

| 现象 | 检查或处理 |
| --- | --- |
| 没有 Tailscale IP，状态 NeedsLogin | 在本机执行前面的 `tailscale up` 命令并完成浏览器授权 |
| 手机看不到电脑 | 确认账号、tailnet、电脑联网和休眠状态；在后台检查设备是否等待审批或已过期 |
| 手机显示电脑在线，SSH 超时 | 检查手机 VPN 是否仍是 Tailscale、Termius 地址和端口、tailnet 访问策略及本机防火墙 |
| Connection refused | 检查 `ssh.service`；可在本机运行 `sudo systemctl start ssh` |
| Permission denied | 确认用户名 `mac`、Linux 密码或手机选择的 SSH 密钥；这是 SSH 身份认证问题 |
| SSH 主机指纹变化 | 在电脑本地重新核对公钥指纹，确认原因后再更新手机记录 |
| 显示 relay，速度略慢 | 已在使用中继；可运行 `tailscale netcheck` 检查网络，终端命令通常仍可使用 |
| 过一段时间必须重新认证 | 在后台检查本机是否已设置 Disable Key Expiry；手机按 App 提示重新认证 |

## 备份和迁移

本目录中的 `setup.sh`、`install-system.sh`、`verify.sh`、`machine_status.md` 和本说明构成可复用的方案备份。修改前已有的 Tailscale APT 源及服务自启状态由安装器备份到本机 `/var/backups/tailscale-remote.*`，仅管理员可读。

`config_snapshot/` 保存本机安装后的非私密配置，供核对和恢复时参考：

| 备份文件 | 本机来源 |
| --- | --- |
| `tailscale.list` | `/etc/apt/sources.list.d/tailscale.list` |
| `tailscaled.default` | `/etc/default/tailscaled` |
| `tailscaled.service` | `/lib/systemd/system/tailscaled.service` |
| `tailscale-settings.txt` | 本机 `tailscale get --set-flags` 输出，不含登录密钥 |
| `sshd_config` | `/etc/ssh/sshd_config`，本次沿用原配置 |
| `ssh.service` | `/lib/systemd/system/ssh.service` |

新电脑优先通过脚本安装适配当前系统的软件包；服务文件快照用于比对，不直接覆盖新系统的软件包文件。

Tailscale 私密状态 `/var/lib/tailscale`、SSH 主机私钥、用户私钥及密码不提交到仓库。目录内 `.local/` 和常见凭据文件名已加入忽略规则；保存临时日志时使用 `.local/`。迁移到新电脑时重新运行 `setup.sh` 并绑定设备，重新核对新主机指纹和新 IP。

### 停用本方案

在电脑本地执行下列命令将中断 Tailscale 远程连接：

```bash
tailscale down
sudo systemctl disable --now tailscaled
```

之后在 Tailscale 设备管理中移除电脑即可。若安装时添加过 UFW 规则，可用下列命令移除：

```bash
sudo ufw delete allow in on tailscale0 to any port 22 proto tcp
```

原先已经使用的 SSH 服务继续按原配置运行。
