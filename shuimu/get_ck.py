#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_ck.py — DBus(keyring) 取 Chrome Safe Storage 密钥 → 解密 newsmth 登录 cookie → 写 .nf_cookie
在 ckprobe 容器里跑 (uid 1000, XDG_RUNTIME_DIR=/host-run-user)。密钥值不进 stdout。
"""
import sys, os, sqlite3, hashlib, struct

os.environ["XDG_RUNTIME_DIR"] = "/host-run-user"
sys.path.insert(0, "/usr/lib/python3/dist-packages")
import dbus
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OUT = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"

# 1) DBus 取密钥
bus = dbus.SessionBus()
service = dbus.Interface(bus.get_object("org.freedesktop.secrets", "/org/freedesktop/secrets"),
                         "org.freedesktop.Secret.Service")
props = dbus.Dictionary({dbus.String("description"): dbus.String("Chrome Safe Storage")},
                        signature="a{ss}")
attrs = dbus.Array(["org.freedesktop.Secret.Item"], signature="s")
found = service.SearchItems(props, attrs)
collection, items = found
print("keyring 匹配项: %d" % len(items))
key = None
for item in items:
    iface = dbus.Interface(item, "org.freedesktop.Secret.Item")
    value, _ = iface.GetSecret("text/plain")
    v = bytes(bytearray(value))
    n = struct.unpack(">I", v[:4])[0]
    key = v[4:4 + n]
    print("项: %s (key %d 字节)" % (iface.GetLabel(), len(key)))
    break
if not key:
    print("NO_KEY"); sys.exit(1)

# 2) 解 Chrome Cookies
db = "/home/mac/.config/google-chrome/Default/Cookies"
con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
rows = con.execute("select host_key, name, encrypted_value from cookies "
                   "where host_key like '%smth%'").fetchall()
con.close()
dk = hashlib.pbkdf2_hmac("sha1", key, b"saltysalt", 1, 16)
pairs = {}
for host, name, enc in rows:
    try:
        if enc[:3] == b"v11":
            pt = AESGCM(dk).decrypt(enc[3:15], enc[15:], None)
        else:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            c = Cipher(algorithms.AES(dk), modes.CBC(b" " * 16)).decryptor()
            pt = c.update(enc[19:]) + c.finalize()
            ln = struct.unpack(">I", pt[:4])[0]
            pt = pt[4:4 + ln]
        pairs["%s=%s" % (name, pt.decode("utf-8", "replace"))] = True
    except Exception as e:
        print("解 %s 失败: %s" % (name, type(e).__name__))

if not pairs:
    print("EMPTY"); sys.exit(2)
with open(OUT, "w") as f:
    f.write("; ".join(pairs))
os.chmod(OUT, 0o600)
print("OK 解密 %d 条: %s" % (len(pairs), [k.split("=")[0] for k in pairs]))
