#!/usr/bin/env bash
# Invoked by setup.sh. No passwords, auth keys, or private keys are saved here.
set -euo pipefail
if (( EUID != 0 )); then
  printf '需要管理员权限；请运行 bash setup.sh。\n' >&2
  exit 1
fi
login_user=${1:?缺少 Linux 登录用户名}
id "$login_user" >/dev/null
if [[ $login_user == root ]]; then
  printf '请指定普通 Linux 用户。\n' >&2
  exit 1
fi
. /etc/os-release
if [[ $ID != ubuntu && $ID != debian ]]; then
  printf '本脚本适用于 Ubuntu 或 Debian；当前系统是 %s。\n' "$ID" >&2
  exit 1
fi
os_codename=${VERSION_CODENAME:?无法识别系统代号}
command -v curl >/dev/null || { printf '请先安装 curl。\n' >&2; exit 1; }
test -c /dev/net/tun || { printf '缺少 /dev/net/tun，请先检查内核 TUN 支持。\n' >&2; exit 1; }

# Back up only configuration. Never copy /var/lib/tailscale or SSH private keys.
backup_dir=$(mktemp -d /var/backups/tailscale-remote.XXXXXXXX)
chmod 700 "$backup_dir"
for config_file in /etc/apt/sources.list.d/tailscale.list /usr/share/keyrings/tailscale-archive-keyring.gpg; do
  if [[ -f $config_file ]]; then
    cp --parents -- "$config_file" "$backup_dir/"
  fi
done
systemctl is-enabled ssh >"$backup_dir/ssh-enabled.before" 2>&1 || true
systemctl is-enabled tailscaled >"$backup_dir/tailscaled-enabled.before" 2>&1 || true
printf '修改前配置备份：%s\n' "$backup_dir"

download_dir=$(mktemp -d)
trap 'rm -rf -- "$download_dir"' EXIT
repo_url="https://pkgs.tailscale.com/stable/$ID/$os_codename"
curl --fail --silent --show-error --location --connect-timeout 15 --max-time 90 --retry 2 \
  "$repo_url.noarmor.gpg" -o "$download_dir/tailscale-archive-keyring.gpg"
curl --fail --silent --show-error --location --connect-timeout 15 --max-time 90 --retry 2 \
  "$repo_url.tailscale-keyring.list" -o "$download_dir/tailscale.list"
install -d -m 0755 /usr/share/keyrings
install -m 0644 "$download_dir/tailscale-archive-keyring.gpg" /usr/share/keyrings/tailscale-archive-keyring.gpg
install -m 0644 "$download_dir/tailscale.list" /etc/apt/sources.list.d/tailscale.list

# Use an existing HTTP proxy for package downloads only, never for tailscaled.
apt_options=(-o Acquire::Retries=2 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30)
http_download_proxy=${http_proxy:-${HTTP_PROXY:-}}
https_download_proxy=${https_proxy:-${HTTPS_PROXY:-}}
[[ -z $http_download_proxy ]] || apt_options+=(-o "Acquire::http::Proxy=$http_download_proxy")
[[ -z $https_download_proxy ]] || apt_options+=(-o "Acquire::https::Proxy=$https_download_proxy")
# Refresh the Tailscale index without contacting unrelated third-party repositories.
apt-get "${apt_options[@]}" update \
  -o Dir::Etc::sourcelist=sources.list.d/tailscale.list \
  -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0
DEBIAN_FRONTEND=noninteractive apt-get "${apt_options[@]}" install -y tailscale openssh-server tmux
/usr/sbin/sshd -t
systemctl enable --now ssh tailscaled
systemctl is-active --quiet ssh
systemctl is-active --quiet tailscaled

# Allow this local user to perform the first browser login without another sudo.
tailscale set --operator="$login_user"

# Keep existing LAN access; add a tailnet interface rule only when UFW is active.
if command -v ufw >/dev/null && LC_ALL=C ufw status | grep -q '^Status: active'; then
  ufw allow in on tailscale0 to any port 22 proto tcp comment 'Tailscale SSH terminal'
fi
printf '\nSSH 与 Tailscale 已启用开机自启；还需要首次账号绑定。\n'
