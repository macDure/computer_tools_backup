# 手动: c1s3 当通道更新订阅 -> 复查 c1s1/c1s2 -> c1s1 通则切换
import sys, json
sys.path.insert(0, '/home/mac/v2rayN-linux-64/autoswitch')
import autoswitch as aw

vdir = '/home/mac/v2rayN-linux-64'
db = vdir + '/guiConfigs/guiNDB.db'
gui_cfg = vdir + '/guiConfigs/guiNConfig.json'
xray_bin = vdir + '/bin/xray/xray'
log = aw.Log(vdir + '/autoswitch/logs/manual-20260910-c1s3.log')

sub_id, sub_url, sub_remark = aw.load_sub(db)
print('SUB: %s' % sub_remark)
servers = aw.load_servers(db, sub_id)
smap = {aw.server_name(s['Remarks']): s for s in servers}

# 1) c1s3 当通道拉订阅
c3 = smap['c1s3']
port = aw.pick_ports(12301, 1, log)[0]
proc = aw.start_probe(aw.build_probe_config([c3], [port]), xray_bin, [port], log, 'sub-c3')
assert proc is not None, 'c1s3 probe core failed'
raw = aw.fetch_sub(sub_url, port, 30, log)
aw.stop_probe(proc, log)
content = aw.decode_maybe_b64(raw)
new_servers, skipped = aw.parse_links(content)
print('PARSE: %d nodes, %d skipped' % (len(new_servers), len(skipped)))
new_servers.sort(key=lambda s: (aw.server_order(aw.server_name(s['Remarks'])), aw.server_name(s['Remarks'])))
aw.apply_sub_to_db(db, sub_id, new_servers, 5, log)
print('SUB_UPDATED via c1s3')

# 2) 复查 c1s1 / c1s2
servers2 = aw.load_servers(db, sub_id)
m2 = {aw.server_name(s['Remarks']): s for s in servers2}
cands = [m2[n] for n in ('c1s1', 'c1s2') if n in m2]
res = aw.probe_servers(cands, xray_bin, 12301, 'https://www.google.com/generate_204', 8, log, 'manual')
for n, r in res.items():
    print('CHECK %s %s -> %s %s ms' % (n, aw.server_name(r) if hasattr(r, 'Remarks') else n,
                                       'OK' if r['ok'] else 'FAIL', r.get('latency_ms')))

c1_ok = res.get('c1s1', {}).get('ok')
print('C1S1_OK=%s' % c1_ok)

# 3) c1s1 通 -> 切换 IndexId
if c1_ok:
    aw.set_index_id(gui_cfg, m2['c1s1']['IndexId'], 5, log)
    v = json.load(open(gui_cfg))['IndexId']
    print('SWITCHED_TO c1s1 IndexId=%s verified=%s' % (v, v == str(m2['c1s1']['IndexId'])))
else:
    print('c1s1 not ok, keep current')
