#!/usr/bin/env bash
# Read-only checks. Exit 0 only when the local prerequisites are ready.
set -uo pipefail
problems=0
printf '检查时间：%s\n主机：%s\nLinux 用户：%s\n\n' "$(date -Is)" "$(hostname)" "$(id -un)"
for service_name in ssh tailscaled; do
  enabled=$(systemctl is-enabled "$service_name" 2>/dev/null) || true
  active=$(systemctl is-active "$service_name" 2>/dev/null) || true
  printf '%s：开机启动=%s，运行状态=%s\n' "$service_name" "${enabled:-unknown}" "${active:-unknown}"
  if [[ $enabled != enabled || $active != active ]]; then
    problems=$((problems + 1))
  fi
done
printf '\nSSH 主机指纹（手机首次连接时核对）：\n'
for public_key in /etc/ssh/ssh_host_*_key.pub; do
  [[ ! -r $public_key ]] || ssh-keygen -lf "$public_key"
done
printf '\n'
if command -v tailscale >/dev/null; then
  tailscale version
  # Filter JSON in memory; never save account names, peers, or authentication URLs.
  status_summary=$(tailscale status --json 2>/dev/null | python3 -c '
import json, sys
data = json.load(sys.stdin)
state = data.get("BackendState", "Unknown")
node = data.get("Self") or {}
print("Tailscale 状态：" + state)
print("设备在线：" + str(node.get("Online", False)))
print("设备密钥已过期：" + str(node.get("Expired", False)))
print("设备授权到期：" + str(node.get("KeyExpiry") or "未设置到期时间"))
for health in data.get("Health") or []:
    print("健康提示：" + health)
for address in data.get("TailscaleIPs") or []:
    if ":" not in address:
        print("Termius 地址：" + address)
        print("SSH 命令：ssh " + __import__("getpass").getuser() + "@" + address)
sys.exit(0 if state == "Running" and node.get("Online") and not node.get("Expired") and data.get("TailscaleIPs") else 1)
')
  status_result=$?
  printf '%s\n' "${status_summary:-无法读取 Tailscale 状态，请检查 tailscaled 或执行 tailscale up。}"
  if (( status_result != 0 )); then
    problems=$((problems + 1))
  else
    # Verify the ordinary OpenSSH endpoint is reachable through the tailnet IP.
    tail_ip=$(tailscale ip -4)
    if python3 - "$tail_ip" <<'PY'
import socket, sys
with socket.create_connection((sys.argv[1], 22), timeout=5) as sock:
    banner = sock.recv(256).decode("ascii", errors="replace").strip()
    print("SSH 握手：" + banner)
    if not banner.startswith("SSH-2.0-"):
        sys.exit(1)
PY
    then
      printf 'Tailscale IP 上的 SSH 端口可达。\n'
    else
      problems=$((problems + 1))
    fi
  fi
else
  printf 'Tailscale 尚未安装。请运行 bash setup.sh。\n'
  problems=$((problems + 1))
fi
printf '\nTermius 端口：22；用户名：%s；密码：本机 Linux 用户密码。\n' "$(id -un)"
if (( problems > 0 )); then
  printf '本机检查未通过，共 %s 项。\n' "$problems" >&2
  exit 1
fi
printf '本机服务检查通过。请再用手机移动数据连接，并核实后台已禁用本机设备密钥过期。\n'
