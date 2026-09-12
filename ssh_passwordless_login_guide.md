# SSH 服务器免密登录配置指南

本文档适用于：从本地机器（如 `~mac`）免密登录局域网/内网中的多台 Linux 服务器，不再每次输入密码。

核心原理：把本地 SSH 公钥追加到目标服务器的 `~/.ssh/authorized_keys` 中，之后用私钥直接认证，无需密码。

---

## 本机实际涉及的服务器

| 服务器 | 用户 | IP | 密码 |
| --- | --- | --- | --- |
| lenovo | `lenovo` | `172.20.149.215` | （已配置免密，密码见个人密码本，勿写入文档） |
| mac | `mac` | `172.20.149.210` | （已配置免密，密码见个人密码本，勿写入文档） |

> 安全提示：密码不要写进任何文档、脚本或 shell 历史，本文统一用 `<密码>` 占位。

---

## 前置条件

1. 本机已安装 `ssh`、`ssh-copy-id`（一般随 `openssh-client` 自带）：

   ```bash
   which ssh-copy-id ssh
   ```

2. 安装 `sshpass`（用于非交互式输入密码，`ssh-copy-id` 首次推送时需要）：

   ```bash
   # Ubuntu / Debian
   sudo apt install sshpass

   # Fedora
   sudo dnf install sshpass

   # macOS (Homebrew)
   brew install hudochenkov/sshpass/sshpass
   ```

3. 目标服务器已开启 SSH，且允许密码登录（`sshd_config` 中 `PasswordAuthentication yes`）。

---

## 快速流程

### 第 1 步：确认本地有 SSH 密钥对

```bash
ls -la ~/.ssh/
```

如果没有 `id_ed25519` / `id_rsa`，生成一个（推荐 ed25519）：

```bash
ssh-keygen -t ed25519 -C "mac-personal"
```

一路回车即可（ passphrase 可留空，留空才能真正一键免密）。

确认私钥无口令（否则每次 ssh 仍要输私钥口令）：

```bash
ssh-keygen -y -P "" -f ~/.ssh/id_ed25519 >/dev/null 2>&1 && echo "no-passphrase" || echo "has-passphrase"
```

### 第 2 步：把公钥推送到目标服务器

每台服务器执行一次，把 `<密码>` 换成实际密码：

```bash
sshpass -p '<密码>' ssh-copy-id \
  -i ~/.ssh/id_ed25519.pub \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=10 \
  lenovo@172.20.149.215

sshpass -p '<密码>' ssh-copy-id \
  -i ~/.ssh/id_ed25519.pub \
  -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=10 \
  mac@172.20.149.210
```

说明：

- `-i ~/.ssh/id_ed25519.pub`：指定要推送的公钥（多密钥时必加，默认 `~/.ssh/id_*.pub` 全部推送）。
- `-o StrictHostKeyChecking=accept-new`：首次连接自动记录主机指纹，避免交互式确认；对已知的旧主机则不会覆盖。
- 推送成功后会提示 `Number of key(s) added: 1`。

### 第 3 步：验证免密登录

```bash
ssh -o BatchMode=yes lenovo@172.20.149.215 'echo ok-215'
ssh -o BatchMode=yes mac@172.20.149.210 'echo ok-210'
```

`BatchMode=yes` 会禁用一切交互（包括输密码），能直接返回 `ok-xxx` 即说明免密成功；如果提示 `Permission denied (publickey)` 说明公钥没推成功。

### 第 4 步（可选）：在 `~/.ssh/config` 中起别名

编辑 `~/.ssh/config`，每台服务器加一段：

```text
Host lenovo
  HostName 172.20.149.215
  User lenovo

Host macserver
  HostName 172.20.149.210
  User mac
```

之后直接：

```bash
ssh lenovo
ssh macserver
scp 文件.txt lenovo:~/
rsync -av ./dir macserver:~/backup/
```

> 注意：本机 config 里如果已存在同 IP 的 Host 段（例如 `172.20.149.210`），直接复用或改名均可，不要重复定义同一个 Host 别名。

---

## 常见选项速查

```bash
ssh-copy-id [选项] 用户@IP
```

| 选项 | 作用 |
| --- | --- |
| `-i 公钥路径` | 指定要推送的公钥文件 |
| `-o StrictHostKeyChecking=accept-new` | 首次连接自动接受主机密钥 |
| `-o ConnectTimeout=10` | 连接超时 10 秒，网络不通时快速失败 |
| `-p 2222` | 目标 SSH 端口不是 22 时使用（`ssh-copy-id -p 端口`） |

用 `sshpass` 免交互输密码的其他写法（避免密码进入 shell 历史）：

```bash
read -rs PASS        # 静默输入密码
sshpass -e SSH_ASK_PASS=... # 或
SSHPASS='<密码>' sshpass -e ssh-copy-id user@IP
unset SSHPASS
```

---

## 排错

1. **`Permission denied (publickey)`**：公钥没推上去。重新执行第 2 步；确认目标机 `~/.ssh` 权限为 `700`、`authorized_keys` 为 `600`。
2. **`Could not resolve hostname` / 连接超时**：IP 不通或不在同一网段，先 `ping IP`。
3. **主机密钥冲突（REMOTE HOST IDENTIFICATION HAS CHANGED）**：目标机重装过系统，执行：
   ```bash
   ssh-keygen -R 172.20.149.215
   ```
   然后重新 `ssh-copy-id`。
4. **目标机禁止密码登录**：`ssh-copy-id` 推不上去，需先通过 VNC/串口或控制台临时打开 `PasswordAuthentication yes`，推完公钥后再改回。
5. **想撤销某台机器的免密**：删除目标机 `~/.ssh/authorized_keys` 中对应那行公钥即可。
6. **本机私钥设了口令想改免口令**（可选）：
   ```bash
   ssh-keygen -p -f ~/.ssh/id_ed25519   # 先输入旧口令，再两次留空
   ```

---

## 安全建议

- 密码只存在个人密码本中，不写入文档、脚本、`~/.ssh/config`。
- `sshpass -p '密码'` 会把密码暴露在进程列表和 shell 历史中，配置完成后不要再使用；临时用可配合 `read -rs` 或 `SSHPASS` 环境变量。
- 长期运行的服务器建议逐步禁用密码登录，只保留公钥登录：目标机 `/etc/ssh/sshd_config` 设 `PasswordAuthentication no` 后 `sudo systemctl reload ssh`。
- `~/.ssh` 目录权限保持 `700`，`authorized_keys` / 私钥保持 `600`。
