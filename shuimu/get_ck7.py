#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_ck7.py — 枚举 keyring login 集合全部 item, 逐个取 secret, 16B 候选试解密 newsmth cookie。
ckprobe 容器跑 (uid 1000, XDG_RUNTIME_DIR=/host-run-user)。值不进 stdout。"""
import os, sys, glob, sqlite3, hashlib, base64
os.environ.setdefault("XDG_RUNTIME_DIR", "/host-run-user")
sys.path.insert(0, "/usr/lib/python3/dist-packages")
import gi
gi.require_version("GLib", "2.0"); gi.require_version("Gio", "2.0")
from gi.repository import GLib, Gio
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SVC_NAME = "org.freedesktop.secrets"
COL = "/org/freedesktop/secrets/collection/login"

conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
def call(path, iface, method, *args):
    res = conn.call_sync(SVC_NAME, path, iface, method,
                         GLib.Variant("(av)", (list(args),)),
                         None, Gio.DBusCallFlags.NONE, 20000, None)
    return res.unpack()[0]

# 打开会话 (返回 (o,o), 实测路径在 index 1)
res = conn.call_sync(SVC_NAME, "/org/freedesktop/secrets", "org.freedesktop.Secret.Service",
                     "OpenSession", GLib.Variant("(sv)", (("plain", GLib.Variant("s", "plain")))),
                     None, Gio.DBusCallFlags.NONE, 20000, None)
_unpacked = res.unpack()
sess_p = str(_unpacked[1]) if len(_unpacked) > 1 and str(_unpacked[1]).startswith("/") else str(_unpacked[0])
print(f"session: {sess_p}")

def item_secret(item_p):
    """非标准 keyring: GetSecret 直接返回 (o session, ay 明文字节), 无需 GetSecrets"""
    r = conn.call_sync(SVC_NAME, item_p, "org.freedesktop.Secret.Item", "GetSecret",
                       GLib.Variant("(o)", (sess_p,)),
                       None, Gio.DBusCallFlags.NONE, 15000, None).unpack()
    inner = r[0] if len(r) == 1 and isinstance(r[0], (tuple, list)) else r
    for x in inner:
        if isinstance(x, (list, tuple)) and x and isinstance(x[0], int):
            return bytes(x)
    return b""

# 枚举集合 items
col_props = conn.call_sync(SVC_NAME, COL, "org.freedesktop.DBus.Properties", "Get",
                           GLib.Variant("(ss)", ("org.freedesktop.Secret.Collection", "Items")),
                           None, Gio.DBusCallFlags.NONE, 10000, None)
items = list(col_props.unpack()[0])
print(f"items: {len(items)}")

candidates = []  # (label, secret_bytes)
for it in items:
    it_p = str(it)
    try:
        lab = conn.call_sync(SVC_NAME, it_p, "org.freedesktop.DBus.Properties", "Get",
                             GLib.Variant("(ss)", ("org.freedesktop.Secret.Item", "Label")),
                             None, Gio.DBusCallFlags.NONE, 10000, None).unpack()[0]
    except Exception:
        lab = "?"
    try:
        sec = item_secret(it_p)
    except Exception:
        sec = b""
    print(f"  [{str(lab)[:50]}] secret={len(sec)}B")
    # keyring 存的是 base64 文本; 解码后才是 16B 原始密钥
    raw = None
    if sec:
        try:
            raw = base64.b64decode(sec)
        except Exception:
            raw = None
    for cand in filter(None, [raw, sec]):
        if len(cand) in (16, 32):
            candidates.append((str(lab), cand))

print(f"候选密钥: {len(candidates)}")

def try_decrypt(enc, key):
    if key == b"peanuts":
        k = hashlib.sha1(b"saltysalt").digest()
    else:
        k = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt",
                       iterations=1).derive(key)
    try:
        return AESGCM(k).decrypt(enc[3:15], enc[15:], None).decode("utf-8")
    except Exception:
        return None

found = []
for db in sorted(glob.glob("/home/mac/.config/google-chrome/*/Cookies")):
    if os.path.getsize(db) < 1000:
        continue
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for host, name, enc in con.execute(
            "select host_key,name,encrypted_value from cookies where host_key like '%newsmth%'"):
        if enc[:3] != b"v11":
            continue
        for lab, key in candidates:
            val = try_decrypt(enc, key)
            if val:
                print(f"解密成功! {host} {name} (key={lab[:30]})")
                found.append(f"main[{name}]={val}" if name.startswith("main[") else f"{name}={val}")
if not found:
    print("NO_MATCH (可能还没登录, 无完整 cookie)")
else:
    ck = "; ".join(dict.fromkeys(found))
    out = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"
    with open(out, "w") as f:
        f.write(ck + "\n")
    os.chmod(out, 0o600)
    print(f"OK 写入 {out} ({len(ck)}B, {len(found)} 条)")
