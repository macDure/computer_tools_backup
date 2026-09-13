#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_ck2.py — 用 secret-service D-Bus API 取 Chrome Safe Storage 密钥并解密 newsmth cookie。
在 ckprobe 容器跑 (uid 1000, XDG_RUNTIME_DIR=/host-run-user)。密钥/cookie 值不进 stdout。"""
import sys, os, sqlite3, hashlib, struct
os.environ["XDG_RUNTIME_DIR"] = "/host-run-user"
import dbus
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OUT = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"

bus = dbus.SessionBus()
svc = dbus.Interface(bus.get_object("org.freedesktop.secrets", "/org/freedesktop/secrets"),
                     "org.freedesktop.Secret.Service")

props = dbus.Dictionary({"description": "Chrome Safe Storage"}, signature="a{ss}")
attrs = dbus.Array(["org.freedesktop.Secret.Item"], signature="s")
collection, items = svc.SearchItems(props, attrs)
print("keyring 匹配项: %d" % len(items))

key = None
for item in items:
    it = dbus.Interface(item, "org.freedesktop.Secret.Item")
    raw, _ = it.GetSecret(dbus.String("text/plain"))
    v = bytes(bytearray(raw))
    n = struct.unpack(">I", v[:4])[0]
    key = v[4:4 + n]
    print("label:", it.GetLabel(), "key字节:", len(key))
    break
if not key:
    print("NO_KEY"); sys.exit(1)

# 解 Chrome Cookies (v11 = AES-GCM, key = PBKDF2(sh1, keyring_key, 'saltysalt',1,16))
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
        elif enc[:3] == b"v10":
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            c = Cipher(algorithms.AES(dk), modes.CBC(b" " * 16)).decryptor()
            p = c.update(enc[3:19]) + c.finalize()
            ln = struct.unpack(">I", p[:4])[0]
            pt = p[4:4 + ln]
        else:
            pt = enc
        pairs["%s=%s" % (name, pt.decode("utf-8", "replace"))] = True
    except Exception as e:
        print("解 %s 失败: %s" % (name, type(e).__name__))

if not pairs:
    print("EMPTY"); sys.exit(2)
with open(OUT, "w") as f:
    f.write("; ".join(pairs))
os.chmod(OUT, 0o600)
print("OK %d 条: %s" % (len(pairs), [k.split("=")[0] for k in pairs]))
