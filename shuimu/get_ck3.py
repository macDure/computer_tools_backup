#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_ck3.py — 手工构造 secret-service D-Bus 消息取 Chrome 密钥 (绕开 python-dbus 字典坑)。
ckprobe 容器跑 (uid 1000, XDG_RUNTIME_DIR=/host-run-user)。值不进 stdout。"""
import sys, os, sqlite3, hashlib, struct
os.environ["XDG_RUNTIME_DIR"] = "/host-run-user"
import dbus
from dbus import String, Array, Dictionary
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OUT = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"

conn = dbus.SessionBus()

def call(path, iface, method, args, sig):
    msg = dbus.message.MethodCallMessage(iface, method, path)
    for a in args:
        msg.append(a)
    msg.set_signature(sig)
    r = conn.send_message_with_reply_blocking(msg, timeout=10000)
    return r.get_args(True)

# 1) SearchItems(a{ss}props, sattrs) -> (o collection, ao items)
props = Dictionary({}, signature="a{ss}")
try:
    props["description"] = "Chrome Safe Storage"
except Exception:
    props = {dbus.String("description"): dbus.String("Chrome Safe Storage")}
res = call("/org/freedesktop/secrets", "org.freedesktop.Secret.Service",
           "SearchItems", [props, Array([String("org.freedesktop.Secret.Item")], signature="s")],
           "a{ss}s")
collection, items = res[0], res[1]
print("keyring 匹配项: %d" % len(items))

key = None
for obj_path in items:
    # GetSecret(o owner, s format) -> (o rep, s repfmt)
    raw = call(obj_path, "org.freedesktop.Secret.Item", "GetSecret",
               [String("text/plain")], "s")
    repdata = bytes(bytearray(raw[0]))
    n = struct.unpack(">I", repdata[:4])[0]
    key = repdata[4:4 + n]
    print("拿到密钥, %d 字节" % len(key))
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
