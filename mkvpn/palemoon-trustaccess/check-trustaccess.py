#!/usr/bin/env python3
"""Read-only checks. Direct LAN access must never be reported as VPN success."""
import argparse
import datetime
import ipaddress
import json
import socket
import subprocess
import time
from pathlib import Path

GATEWAY = '111.202.232.70'
TARGET = '172.20.149.216'


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or ' '.join(args))
    return result.stdout


def tcp(host, port):
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def classify(tunnel, internal, direct, gateway):
    if direct:
        return 'LAN_ACCESS_VPN_UNPROVEN'
    if tunnel and internal and gateway:
        return 'VPN_CANDIDATE_NEEDS_EXTERNAL_ACCEPTANCE'
    if not gateway:
        return 'GATEWAY_UNREACHABLE'
    if tunnel:
        return 'TUNNEL_PRESENT_INTERNAL_UNREACHABLE'
    return 'VPN_NOT_CONNECTED'


def check():
    interfaces = json.loads(run('ip', '-j', '-4', 'address', 'show'))
    routes = json.loads(run('ip', '-j', '-4', 'route', 'show', 'table', 'main'))
    gateway_route = json.loads(run('ip', '-j', '-4', 'route', 'get', GATEWAY))[0]
    target_route = json.loads(run('ip', '-j', '-4', 'route', 'get', TARGET))[0]
    tunnel = [f"{iface['ifname']}:{addr['local']}" for iface in interfaces
              for addr in iface.get('addr_info', [])
              if ipaddress.ip_address(addr['local']) in ipaddress.ip_network('172.20.70.0/24')]
    # Connected company LAN routes can mask a broken or absent VPN.
    direct = [r for r in routes if r.get('protocol') == 'kernel'
              and r.get('dst', 'default') != 'default'
              and ipaddress.ip_address(TARGET) in ipaddress.ip_network(r['dst'])]
    # Company Wi-Fi can reach the target through a router even without a
    # connected target-subnet route. Flag physical company-LAN addresses too.
    company_interfaces = [
        {'interface': iface['ifname'], 'address': addr['local']}
        for iface in interfaces
        if (Path('/sys/class/net') / iface['ifname'] / 'device').exists()
        for addr in iface.get('addr_info', [])
        if ipaddress.ip_address(addr['local']) in ipaddress.ip_network('172.20.0.0/16')
        and ipaddress.ip_address(addr['local']) not in ipaddress.ip_network('172.20.70.0/24')
    ]
    gateway = tcp(GATEWAY, 1443)
    internal = tcp(TARGET, 80)
    backend = {}
    for name in ('secvpnMonitord', 'secvpnServerd', 'pluto', 'scsProxyd'):
        result = subprocess.run(['pgrep', '-x', name], capture_output=True, text=True)
        backend[name] = result.stdout.split()
    return {
        'time': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'status': classify(tunnel, internal, direct or company_interfaces, gateway),
        'gateway_tcp_1443': gateway,
        'gateway_route': gateway_route,
        'tunnel_addresses': tunnel,
        'internal_tcp_80': internal,
        'internal_route': target_route,
        'direct_company_routes': direct,
        'possible_company_interfaces': company_interfaces,
        'backend_pids': backend,
        'plugin_socket': Path('/var/run/secvpn/secvpn.fox').is_socket(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=1, help='number of bounded samples')
    parser.add_argument('--interval', type=float, default=30, help='seconds between samples')
    parser.add_argument('--json', action='store_true', help='one JSON object per sample')
    parser.add_argument('--pause', action='store_true', help='keep desktop terminal open')
    args = parser.parse_args()
    if not 1 <= args.samples <= 1440 or args.interval < 1:
        parser.error('samples must be 1..1440 and interval must be >= 1 second')
    all_candidate = True
    for index in range(args.samples):
        try:
            result = check()
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            result = {'status': 'CHECK_FAILED', 'error': str(error)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        else:
            messages = {
                'LAN_ACCESS_VPN_UNPROVEN': '公司网络可直接访问目标，当前结果不能证明 VPN 可用。',
                'VPN_CANDIDATE_NEEDS_EXTERNAL_ACCEPTANCE': '有 VPN 地址且目标端口可达；仍需在外网确认隧道实际承载流量。',
                'GATEWAY_UNREACHABLE': 'VPN 网关不可达，请先检查普通网络。',
                'TUNNEL_PRESENT_INTERNAL_UNREACHABLE': 'VPN 地址仍在，但目标端口不可达；可能需要重新登录或检查目标服务。',
                'VPN_NOT_CONNECTED': '尚未取得 VPN 地址，请在专用浏览器中登录。',
                'CHECK_FAILED': '检查未完成，详见 error；请在本机终端运行。',
            }
            print(messages[result['status']], flush=True)
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        all_candidate &= result['status'] == 'VPN_CANDIDATE_NEEDS_EXTERNAL_ACCEPTANCE'
        if index + 1 < args.samples:
            time.sleep(args.interval)
    if args.pause:
        try:
            input('\n按 Enter 关闭。LAN_ACCESS_VPN_UNPROVEN 表示公司直连，尚未证明 VPN 可用。')
        except EOFError:
            pass
    # 0 = candidate only; packet/counter evidence is still needed for acceptance.
    return 0 if all_candidate else 2


if __name__ == '__main__':
    raise SystemExit(main())
