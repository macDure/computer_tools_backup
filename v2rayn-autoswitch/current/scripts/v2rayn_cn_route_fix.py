#!/usr/bin/env python3
"""给 10808 兜底 xray 的 config.json 加 国内/内网直连 路由规则。
背景: 当前配置 0 条 routing = 全流量走海外节点 → 国内慢 + 内网 10.x 不通(503)。
规则: geoip:private(内网) + geosite:cn + geoip:cn → direct; 其余 → proxy。
幂等: 已有 direct outbound + routing 则跳过。备份 .bak-cnroute。
"""
import json, shutil, sys

p = '/home/mac/v2rayN-linux-64/guiConfigs/config.json'
c = json.load(open(p))

tags = [o.get('tag') for o in c.get('outbounds', [])]
if 'direct' in tags and c.get('routing', {}).get('rules'):
    print("ALREADY_PATCHED")
    sys.exit(0)

shutil.copy(p, p + '.bak-cnroute')
if 'direct' not in tags:
    c['outbounds'].append({"tag": "direct", "protocol": "freedom"})
c['routing'] = {
    "domainStrategy": "AsIs",
    "rules": [
        {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
        {"type": "field", "domain": ["geosite:cn"], "outboundTag": "direct"},
        {"type": "field", "ip": ["geoip:cn"], "outboundTag": "direct"},
        {"type": "field", "domain": ["geosite:geolocation-!cn"], "outboundTag": "proxy"},
    ],
}
with open(p, 'w') as f:
    json.dump(c, f, indent=1, ensure_ascii=False)
print("PATCHED: +direct outbound + 4 routing rules (cn/private→direct, else→proxy)")
