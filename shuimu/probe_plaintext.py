#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_plaintext.py — 打印可疑密钥解出的明文 hex, 判断是否"差一点"。ckprobe 跑。"""
import os, sys, glob, sqlite3, base64
os.environ.setdefault("XDG_RUNTIME_DIR", "/host-run-user")
import gi
gi.require_version("GLib", "2.0"); gi.require_version("Gio", "2.0")
from gi.repository import GLib, Gio
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SVC = "org.freedesktop.secrets"
COL = "/org/freedesktop/secrets/collection/login"
conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
res = conn.call_sync(SVC, "/org/freedesktop/secrets", "org.freedesktop.Secret.Service",
                     "OpenSession", GLib.Variant("(sv)", (("plain", GLib.Variant("s", "plain")))),
                     None, Gio.DBusCallFlags.NONE, 20000, None)
u = res.unpack()
sess_p = str(u[1]) if len(u) > 1 and str(u[1]).startswith("/") else str(u[0])

def item_secret(item_p):
    r = conn.call_sync(SVC, item_p, "org.freedesktop.Secret.Item", "GetSecret",
                       GLib.Variant("(o)", (sess_p,)),
                       None, Gio.DBusCallFlags.NONE, 15000, None).unpack()
    inner = r[0] if len(r) == 1 and isinstance(r[0], (tuple, list)) else r
    for x in inner:
        if isinstance(x, (list, tuple)) and x and isinstance(x[0], int):
            return bytes(x)
    return b""

items = list(conn.call_sync(SVC, COL, "org.freedesktop.DBus.Properties", "Get",
    GLib.Variant("(ss)", ("org.freedesktop.Secret.Collection", "Items")),
    None, Gio.DBusCallFlags.NONE, 10000, None).unpack()[0])

ss_secret = None
for it in items:
    it_p = str(it)
    lab = str(conn.call_sync(SVC, it_p, "org.freedesktop.DBus.Properties", "Get",
        GLib.Variant("(ss)", ("org.freedesktop.Secret.Item", "Label")),
        None, Gio.DBusCallFlags.NONE, 10000, None).unpack()[0])
    if lab == "Chrome Safe Storage":
        ss_secret = item_secret(it_p)
        print(f"Chrome Safe Storage secret: {len(ss_secret)}B 字符数 {len(ss_secret.decode('latin1'))}")
        break

encs = []
for db in sorted(glob.glob("/home/mac/.config/google-chrome/*/Cookies")):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for host, name, enc in con.execute(
            "select host_key,name,encrypted_value from cookies where host_key like '%newsmth%' and name like 'main[%'"):
        encs.append((name, enc))
encs.sort()
target = next((e for e in encs if e[0] == "main[UTMPUSERID]"), encs[0])
n, enc = target
iv, ct = enc[3:19], enc[19:]
print(f"目标 {n}: iv={iv.hex()} ctlen={len(ct)}")

def show(tag, key):
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    pl = d.update(ct) + d.finalize()
    # 不验证 padding, 直接看前 16 字节
    print(f"{tag:28s} -> {pl[:20].hex()}")
    try:
        print(f"{'':28s}    str: {pl[:20].decode('utf-8', 'replace')!r}")
    except Exception:
        pass

p1 = PBKDF2HMAC(hashes.SHA1(), 16, b"saltysalt", 1)
show("pbkdf2(sha1,1,raw24char)", p1.derive(ss_secret))
show("pbkdf2(sha1,1,b64dec16)", p1.derive(base64.b64decode(ss_secret)))
show("direct16(b64dec)", base64.b64decode(ss_secret))
show("pbkdf2(sha1,1003,raw24)", PBKDF2HMAC(hashes.SHA1(), 16, b"saltysalt", 1003).derive(ss_secret))
# 对照: 用错 key 时第一块应该是完全随机; 对 key 时是明文
