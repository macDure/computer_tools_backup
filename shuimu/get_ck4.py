#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_ck4.py — 枚举 keyring 找 Chrome Safe Storage (零字典接口, 绕开 python-dbus 字典 bug)。
ckprobe 容器跑 (uid 1000, XDG_RUNTIME_DIR=/host-run-user)。值不进 stdout。"""
import sys, os, sqlite3, hashlib, struct
os.environ["XDG_RUNTIME_DIR"] = "/host-run-user"
import dbus
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OUT = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"
bus = dbus.SessionBus()
svc = dbus.Interface(bus.get_object("org.freedesktop.secrets", "/org/freedesktop/secrets"),
                     "org.freedesktop.Secret.Service")

key = None
try:
    # 真实集合路径 (从 Properties.Collections 实证): collection/login
    colo = bus.get_object("org.freedesktop.secrets",
                          "/org/freedesktop/secrets/collection/login")
    col = dbus.Interface(colo, "org.freedesktop.Secret.Collection")
    colp = dbus.Interface(colo, "org.freedesktop.DBus.Properties")
    items = colp.Get("org.freedesktop.Secret.Collection", "Items")
    print("Login 集合内 item 数: %d" % len(items))
    for it_path in items:
        try:
            ito = bus.get_object("org.freedesktop.secrets", str(it_path))
            it = dbus.Interface(ito, "org.freedesktop.Secret.Item")
            ip = dbus.Interface(ito, "org.freedesktop.DBus.Properties")
            label = str(ip.Get("org.freedesktop.Secret.Item", "Label"))
            if "chrome" in label.lower() or "safe storage" in label.lower():
                raw, _ = it.GetSecret(dbus.String("text/plain"))
                v = bytes(bytearray(raw))
                n = struct.unpack(">I", v[:4])[0]
                key = v[4:4 + n]
                print("命中: label=%s key=%d字节" % (label, len(key)))
                break
            else:
                print("  item:", label)
        except Exception as e:
            print("  item %s 跳过: %s" % (it_path, type(e).__name__))
except Exception as e:
    print("枚举失败:", type(e).__name__, str(e)[:200]); sys.exit(1)

if not key:
    print("NO_KEY"); sys.exit(1)

# 解 Chrome Cookies (v11 = AES-GCM)
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
