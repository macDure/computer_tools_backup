#!/usr/bin/env bash
# Run as the Linux user who will log in from Android.
set -euo pipefail
kit_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --help ]]; then
  printf '用法：bash setup.sh\n安装官方 Tailscale、启用 SSH 和 Tailscale 开机自启，然后通过浏览器绑定账号。\n'
  exit 0
fi
if (( EUID == 0 )); then
  printf '请以普通用户运行 bash setup.sh；脚本会在需要时调用 sudo。\n' >&2
  exit 1
fi
printf '即将安装 Tailscale 并启用系统服务。sudo 密码只在本机终端输入。\n'
sudo --preserve-env=http_proxy,https_proxy,HTTP_PROXY,HTTPS_PROXY,all_proxy,ALL_PROXY,no_proxy,NO_PROXY \
  bash "$kit_dir/install-system.sh" "$(id -un)"
printf '\n请打开下面的登录链接，绑定你在安卓手机上使用的同一个 Tailscale 账号。\n'
if ! tailscale up --accept-dns=false --accept-routes=false --ssh=false --timeout=5m; then
  printf '\n账号绑定尚未完成。完成浏览器授权后可重新运行本脚本。\n' >&2
  exit 1
fi
bash "$kit_dir/verify.sh"
printf '\n接下来在安卓 Tailscale 中登录同一账号，在 Termius 中添加上面显示的地址。\n'
printf '长期无人值守：在 Tailscale 管理后台为这台电脑选择 Disable Key Expiry。\n'
