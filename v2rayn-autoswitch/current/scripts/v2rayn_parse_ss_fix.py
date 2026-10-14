#!/usr/bin/env python3
"""v2rayN autoswitch parse_ss 补丁(幂等): 兼容整段 base64 编码的老式 ss 链接(c1s1/c1s2)。

背景: 订阅里 c1s1/c1s2 是 b64(method:pass@host:port) 整段编码格式,
原 parse_ss 只认 b64(method:pass)@host:port, 导致这两节点每次更新订阅都被静默跳过。
宿主机存在按源版本还原该文件的行为(属主/mtime 均被还原), 故本脚本做成幂等,
由 wrapper 在每次运行前调用自愈。

用法: python3 v2rayn_parse_ss_fix.py [autoswitch.py 路径]
      默认 /home/mac/v2rayN-linux-64/autoswitch/autoswitch.py (runner 容器内路径)
输出: PATCHED / ALREADY_PATCHED (exit 0), ANCHOR_NOT_FOUND (exit 1)
"""
import sys
import re
import os
import shutil
import time

MARKER = "# PARSE_SS_B64_PATCH_V2"
OLD_MARKER = "# PARSE_SS_B64_PATCH_V1"
PATH = sys.argv[1] if len(sys.argv) > 1 else "/home/mac/v2rayN-linux-64/autoswitch/autoswitch.py"

NEW_FUNC = '''@@MARKER@@
def parse_ss(rest):
    remark = ""
    if "#" in rest:
        rest, remark = rest.rsplit("#", 1)
    if "?" in rest:
        rest = rest.split("?", 1)[0]
    core = rest
    if "@" not in core:
        # 兼容整段 base64 编码的老式 ss 链接: b64(method:pass@host:port)
        b64 = re.sub(r"\\s+", "", core)
        try:
            dec = base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-8", "replace")
        except Exception:
            dec = ""
        if "@" in dec and ":" in dec:
            mp, hostport = dec.rsplit("@", 1)
            method, password = "aes-256-gcm", ""
            if ":" in mp:
                method, password = mp.split(":", 1)
            else:
                password = mp
            host, port = split_hostport(hostport)
            if not host or not port or not password:
                return None
            return {"ConfigType": 3, "Address": host, "Port": int(port), "Id": password,
                    "Security": method, "Network": "", "StreamSecurity": "",
                    "Remarks": unquote(remark) or "%s:%s" % (host, port)}
    user = ""
    if "@" in core:
        user, hostport = core.rsplit("@", 1)
    else:
        hostport = core
    host, port = split_hostport(hostport)
    method, password = "aes-256-gcm", ""
    if user:
        u = user.strip()
        try:
            dec = base64.b64decode(u + "=" * (-len(u) % 4)).decode("utf-8", "replace")
            if ":" in dec:
                method, password = dec.split(":", 1)
            else:
                password = dec
        except Exception:
            if ":" in u:
                method, password = u.split(":", 1)
            else:
                password = u
    if not host or not port or not password:
        return None
    return {"ConfigType": 3, "Address": host, "Port": int(port), "Id": password,
            "Security": method, "Network": "", "StreamSecurity": "",
            "Remarks": unquote(remark) or "%s:%s" % (host, port)}
'''

NEW_FUNC = NEW_FUNC.replace("@@MARKER@@", MARKER)

src = open(PATH, encoding="utf-8").read()
if MARKER in src and 'if "@" not in core:' in src:
    print("ALREADY_PATCHED")
    sys.exit(0)

pat = re.compile(r"def parse_ss\(rest\):.*?(?=\ndef \w)", re.S)
if not pat.search(src):
    print("ANCHOR_NOT_FOUND")
    sys.exit(1)

# 清掉 V1 残留(只有标记没有逻辑的中间态)
src = src.replace(OLD_MARKER + "\n", "")
src = pat.sub(lambda m: NEW_FUNC, src, count=1)

bak = PATH + ".pre_patch_%s" % time.strftime("%Y%m%d_%H%M%S")
shutil.copy2(PATH, bak)
open(PATH, "w", encoding="utf-8").write(src)
try:
    os.chmod(PATH, 0o755)
    os.chown(PATH, 1000, 1000)
except Exception:
    pass
print("PATCHED")
