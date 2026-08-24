# Codex CLI 新机器安装与更新操作指南

更新时间：2026-08-21

## 新机器安装（Linux/macOS）

官方 OpenAI 文档：<https://learn.chatgpt.com/docs/codex/cli>

官方独立安装器会自动安装或更新 Codex CLI：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

安装后刷新当前 Shell 并验证：

```bash
hash -r
command -v codex
codex --version
```

首次使用时，在项目目录运行：

```bash
codex
```

然后按提示选择 `Sign in with ChatGPT` 或其他可用登录方式。安装成功只以 `codex --version` 能正常输出版本号为准。

## 在远程机器 `lenovo@172.20.149.215` 上安装

### 远程机的 v2rayN 代理

该机器已经运行 v2rayN/xray，并监听：

```text
127.0.0.1:10808  SOCKS5
```

远程用户的 `.bashrc` 已配置以下代理变量；新开交互式终端后会自动生效：

```bash
export http_proxy=socks5h://127.0.0.1:10808
export https_proxy=socks5h://127.0.0.1:10808
export all_proxy=socks5h://127.0.0.1:10808
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export ALL_PROXY="$all_proxy"
```

这里使用 `socks5h`，因为远程 v2rayN 的 10808 是 SOCKS 入站，不是 HTTP CONNECT 端口。临时启用方式：

```bash
export http_proxy=socks5h://127.0.0.1:10808
export https_proxy=socks5h://127.0.0.1:10808
export all_proxy=socks5h://127.0.0.1:10808
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export ALL_PROXY="$all_proxy"
```

先确保 SSH 登录成功；本次尝试已能连到 22 端口，但当前 SSH 公钥未被远程主机接受：

```text
Permission denied (publickey,password)
```

如果远程账户允许密码登录，可以先执行下面的命令完成公钥授权（会交互式询问远程账户密码，不要把密码写入脚本或本文档）：

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub lenovo@172.20.149.215
```

然后登录并安装：

```bash
ssh lenovo@172.20.149.215

curl -fsSL https://chatgpt.com/codex/install.sh | sh
hash -r
command -v codex
codex --version
codex
```

也可以在本机直接执行安装命令：

```bash
ssh -t lenovo@172.20.149.215 'bash -lic "curl -fsSL https://chatgpt.com/codex/install.sh | sh"'
```

本次实际安装结果：

```text
Codex CLI 0.149.0 installed successfully.
codex-cli 0.149.0
/home/lenovo/.local/bin/codex
```

官方安装地址经远程 v2rayN 代理测试返回 HTTP 200。

如果远程主机没有 `curl`，先在远程主机安装它，再重新执行官方安装器。例如 Debian/Ubuntu：

```bash
sudo apt-get update
sudo apt-get install -y curl
```

## 更新 Codex

官方更新命令与安装命令相同，重复执行即可：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
hash -r
codex --version
```

下面的“代理故障排查”是旧机器的历史记录；只有远程机器确实使用 `127.0.0.1:10808` SOCKS 代理时才参考，不要直接套用其中的代理地址。

以下内容是旧机器在 2026-07-30 的历史排障记录。

用途：

1. 给我自己下次更新 Codex 时直接照着执行。
2. 如果又失败，把这份文档给大模型，让它不要重复让我试已经踩过的坑。

## 旧机器历史排障脚本（2026-07-30）

下面脚本保留作历史排障参考。远程 Ubuntu 20.04 的 `curl 7.68.0` 不支持 `--retry-all-errors`；远程机更新优先使用上面的官方命令，并让 `.bashrc` 中的 SOCKS5 代理生效。

在普通终端执行，不要在 Codex 会话里的受限 shell 执行。

直接复制整段：

```bash
set -e

PROXY="socks5h://127.0.0.1:10808"
INSTALLER="/tmp/codex-install.sh"
WRAP_DIR="/tmp/codex-curl-bin"

echo "==> 当前 Codex"
codex --version || true
readlink -f "$(command -v codex)" || true

echo "==> 下载官方安装脚本"
curl --http1.1 --retry 5 --retry-all-errors --retry-delay 2 \
  --connect-timeout 30 --max-time 180 \
  -fL -x "$PROXY" \
  https://releases.openai.com/codex/install.sh \
  -o "$INSTALLER"

echo "==> 确认脚本下载成功"
wc -c "$INSTALLER"

echo "==> 创建 curl 包装器，保证安装脚本内部下载也走稳定参数"
mkdir -p "$WRAP_DIR"
cat > "$WRAP_DIR/curl" <<'EOF'
#!/bin/sh
exec /usr/bin/curl --http1.1 --retry 5 --retry-all-errors --retry-delay 2 --connect-timeout 30 --max-time 300 -x socks5h://127.0.0.1:10808 "$@"
EOF
chmod +x "$WRAP_DIR/curl"

echo "==> 执行 Codex 更新"
PATH="$WRAP_DIR:$PATH" \
  CODEX_NON_INTERACTIVE=1 \
  sh "$INSTALLER"

echo "==> 验证更新结果"
hash -r
codex --version
readlink -f "$(command -v codex)"
ls -la ~/.codex/packages/standalone/current
```

成功标准：

```text
Codex CLI 0.x.y installed successfully.
codex-cli 0.x.y
```

并且：

```bash
readlink -f "$(command -v codex)"
```

应该指向类似：

```text
/home/mac/.codex/packages/standalone/releases/0.x.y-x86_64-unknown-linux-musl/bin/codex
```

只要 `codex --version` 已经变成新版本，就算更新完成。

## 如果又失败，先看这几个关键坑

下面这些是已经试过的，不要反复浪费时间。

### 坑 1：不要相信 `Update now` 的成功提示

`Update now` 实际运行类似：

```bash
sh -c 'curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh'
```

本机出现过假成功：

```text
curl: (7) Failed to connect to 127.0.0.1 port 10808
🎉 Update ran successfully! Please restart Codex.
```

结论：提示 success 没意义，必须看：

```bash
codex --version
```

### 坑 2：不要优先跑裸 `codex update`

`codex update` 在本机也会走官方安装脚本，但内部 `curl` 参数太弱，可能失败后仍显示成功。

结论：优先用本文第一段完整命令。

### 坑 3：只下载 `/tmp/codex-install.sh` 不够

之前已经验证过：安装脚本本身可以下载成功：

```bash
curl --http1.1 --retry 5 --retry-all-errors \
  -fL -x socks5h://127.0.0.1:10808 \
  https://releases.openai.com/codex/install.sh \
  -o /tmp/codex-install.sh
```

但直接执行仍可能失败：

```text
curl: (28) SSL connection timeout
WARNING: releases.openai.com is unavailable; falling back to GitHub Releases.
curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to api.github.com:443
Could not fetch GitHub release metadata for Codex latest.
```

原因：官方安装脚本内部还会继续调用 `curl` 下载 metadata 和 release 包。

结论：`/tmp/codex-curl-bin/curl` 包装器是关键，不是可选项。

### 坑 4：必须显式用 `socks5h://127.0.0.1:10808`

不要依赖当前环境变量里的：

```bash
https_proxy=http://127.0.0.1:10808/
ALL_PROXY=socks://127.0.0.1:10808/
```

`curl` 访问 HTTPS 时会优先使用 `https_proxy`，可能把 `10808` 当 HTTP CONNECT 代理。

结论：更新 Codex 时始终显式使用：

```text
socks5h://127.0.0.1:10808
```

### 坑 5：不要把 `curl -I 200` 当成完整成功

之前 `releases.openai.com` 和 `raw.githubusercontent.com` 都返回过 `HTTP/2 200`，但安装脚本仍可能在后续正文下载、GitHub API、release asset 下载阶段失败。

结论：`HEAD 200` 只能证明入口可达，不能证明安装链路稳定。

### 坑 6：如果 10808 有两个 v2rayN xray，先清掉旧的

检查：

```bash
ss -lntup sport = :10808
ps -eo pid,ppid,user,comm,args | rg -i 'v2rayN-linux-64|xray|v2raya|v2ray|sing-box|clash|mihomo'
```

本次曾出现两个 v2rayN 子进程同时监听 `10808`：

```text
1267588 ... /home/mac/v2rayN-linux-64/bin/xray/xray run -c config.json
3090707 ... /home/mac/v2rayN-linux-64/bin/xray/xray run -c config.json
```

当时处理方式：

```bash
kill -TERM 1267588
```

原则：

- 只停掉较旧的 v2rayN `xray`。
- 保留较新的 v2rayN `xray`。
- 不要 `pkill xray`，因为机器上还可能有系统级 `xray` 或 v2raya。

## 给下一次大模型的要求

如果我把这份文档给你，并让你帮我升级 Codex：

1. 先让我执行“下次更新直接执行”里的整段命令。
2. 不要先让我试 `Update now`、`codex update`、裸 `curl | sh`。
3. 不要只让我测 `curl -I`。
4. 如果安装失败，先确认有没有使用 `/tmp/codex-curl-bin/curl` 包装器。
5. 如果代理异常，再检查 `10808` 是否有重复 v2rayN `xray`。
6. 最终只以 `codex --version` 作为升级成功依据。

## 本次成功记录

本次实际从：

```text
codex-cli 0.145.0
```

成功更新到：

```text
codex-cli 0.146.0
```

最后真正成功的关键命令是：

```bash
PATH=/tmp/codex-curl-bin:$PATH \
  CODEX_NON_INTERACTIVE=1 \
  sh /tmp/codex-install.sh

hash -r
codex --version
```
