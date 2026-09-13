import re
data=open('/opt/data/scripts/shuimu_daily/_pack.js','r',encoding='utf-8',errors='replace').read() if False else None
# re-fetch handled by shell; here just parse if file present
import os
p='/opt/data/scripts/shuimu_daily/_pack.js'
data=open(p,encoding='utf-8',errors='replace').read() if os.path.exists(p) else ""
print("chars", len(data))
# session timeout value
for m in re.finditer(r"session\s*:\s*[^}]*?timeout[^,\}]*", data):
    print("SESSION:", m.group(0)[:120])
for m in re.finditer(r"timeout\s*:\s*\d+", data):
    print("timeout:", m.group(0))
# any message strings about login failure / 过多 / 在线 / 失败 / 密码
for kw in ["过多","在线","登录失败","密码","错误","频繁","次数","IP","封"]:
    idxs=[m.start() for m in re.finditer(kw,data)]
    if idxs:
        print(f"\n## {kw} ({len(idxs)})")
        for i in idxs[:3]:
            print("   ", data[max(0,i-30):i+40].replace("\n"," "))
