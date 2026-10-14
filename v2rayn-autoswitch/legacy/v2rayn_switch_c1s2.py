# 闭环: 探 c1s2 -> 不通则经 c1s3 更新订阅 -> 复测 -> 通则切兜底 xray 到 c1s2
# 失败保持现状(c1s3 兜底不断网)。全部动作在 runner 容器内。
import sys, os, json, time, sqlite3, subprocess
sys.path.insert(0, '/home/mac/v2rayN-linux-64/autoswitch')
import autoswitch as aw

vdir = '/home/mac/v2rayN-linux-64'
db = vdir + '/guiConfigs/guiNDB.db'
gui_cfg = vdir + '/guiConfigs/guiNConfig.json'
xray_bin = vdir + '/bin/xray/xray'
cfg_path = vdir + '/guiConfigs/config.json'
log = aw.Log(vdir + '/autoswitch/logs/manual-c1s2-switch.log')

sub_id, sub_url, sub_remark = aw.load_sub(db)

def get(name):
    rows = [x for x in aw.load_servers(db, sub_id) if aw.server_name(x['Remarks']) == name]
    return rows[0] if rows else None

def probe_one(row, tag):
    ports = aw.pick_ports(12350, 1, log)
    res = aw.probe_servers([row], xray_bin, 12350, 'https://www.google.com/generate_204', 8, log, tag)
    n = aw.server_name(row['Remarks'])
    return n, res[n]

c2 = get('c1s2')
print('c1s2 当前: %s:%s' % (c2['Address'], c2['Port']))
n, r = probe_one(c2, 'pre')
print('STEP1 c1s2 探测: %s %s ms' % ('OK' if r['ok'] else 'FAIL', r.get('latency_ms')))

if not r['ok']:
    print('STEP2 c1s2 不通 -> 经 c1s3 更新订阅')
    c3 = get('c1s3')
    sp = aw.pick_ports(12360, 1, log)[0]
    proc = aw.start_probe(aw.build_probe_config([c3], [sp]), xray_bin, [sp], log, 'subupd')
    assert proc is not None, 'c1s3 探测核心启动失败'
    raw = aw.fetch_sub(sub_url, sp, 30, log)
    aw.stop_probe(proc, log)
    content = aw.decode_maybe_b64(raw)
    servers, skipped = aw.parse_links(content)
    print('订阅解析: %d 节点, 跳过 %d' % (len(servers), len(skipped)))
    servers.sort(key=lambda s: (aw.server_order(aw.server_name(s['Remarks'])), aw.server_name(s['Remarks'])))
    aw.apply_sub_to_db(db, sub_id, servers, 5, log)
    print('STEP2 订阅已更新')
    c2 = get('c1s2')
    print('c1s2 新地址: %s:%s' % (c2['Address'], c2['Port']))
    n, r = probe_one(c2, 'postsub')
    print('STEP3 c1s2 复测: %s %s ms' % ('OK' if r['ok'] else 'FAIL', r.get('latency_ms')))

if not r['ok']:
    print('ABORT: c1s2 更新订阅后仍不通, 保持 c1s3 兜底供网')
    sys.exit(1)

print('STEP4 切兜底 xray -> c1s2')
# 4a. 精确杀旧兜底 xray (config.json 当前是 c1s3 的; 找所有 uid0 的 xray run 进程)
import glob
killed = []
for fd_pid in glob.glob('/proc/[0-9]*'):
    try:
        pid = fd_pid.split('/')[2]
        cmd = open('/proc/%s/cmdline' % pid, 'rb').read().replace(b'\0', b' ').decode('replace')
        if 'xray run' in cmd or 'xray/xray' in cmd:
            uid = [l for l in open('/proc/%s/status' % pid) if l.startswith('Uid:')][0].split()[1]
            if uid == '0':
                os.kill(int(pid), 15)
                killed.append(pid)
    except Exception:
        pass
print('已杀旧兜底 xray pid:', killed)
# 等端口释放
deadline = time.time() + 10
while time.time() < deadline:
    try:
        s = __import__('socket').socket(); s.bind(('127.0.0.1', 10808)); s.close()
        break
    except OSError:
        time.sleep(1)
else:
    print('WARN: 10808 未释放, 尝试 SIGKILL')
    for pid in killed:
        try:
            os.kill(int(pid), 9)
        except Exception:
            pass
    time.sleep(3)

# 4b. 写 c1s2 配置 + 起新兜底
aw.backup(cfg_path, 5, log)
cfg = {
    'log': {'loglevel': 'warning'},
    'inbounds': [{
        'tag': 'socks', 'port': 10808, 'listen': '127.0.0.1', 'protocol': 'socks',
        'settings': {'auth': 'noauth', 'udp': True, 'allowTransparent': False},
    }],
    'outbounds': [aw.build_outbound('proxy', c2)],
}
tmp = cfg_path + '.tmp'
json.dump(cfg, open(tmp, 'w'), indent=2, ensure_ascii=False)
os.replace(tmp, cfg_path)
subprocess.Popen([xray_bin, 'run', '-c', cfg_path], cwd=vdir + '/guiConfigs',
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, start_new_session=True)
up = aw.wait_port(10808, 15)
print('STEP4 新兜底 xray(c1s2) 10808 UP=%s' % up)
sys.exit(0 if up else 1)
