#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_ck5.py — secret-service 标准两段式取 Chrome 密钥 + 解 newsmth cookie。
ckprobe 容器跑 (uid 1000, XDG_RUNTIME_DIR=/host-run-user)。值不进 stdout。
流程: OpenSession("plain") -> item.GetSecret(session, fmt)->(ref,fmt) -> Service.GetSecrets(session,{item:ref})->明文
"""
import sys, os, sqlite3, hashlib, struct
os.environ["XDG_RUNTIME_DIR"] = "/host-run-user"
import dbus
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OUT = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"
bus = dbus.SessionBus()
svc_path = "/org/freedesktop/secrets"

# 1) OpenSession("plain") -> (session_path, output)
openmsg = dbus.Interface(bus.get_object("org.freedesktop.secrets", svc_path),
                         "org.freedesktop.Secret.Service")
session_path, _ = openmsg.OpenSession(dbus.String("plain"), dbus.String(""))
print("session:", str(session_path))

# 2) 定位 Chrome Safe Storage item
colo = bus.get_object("org.freedesktop.secrets", "/org/freedesktop/secrets/collection/login")
colp = dbus.Interface(colo, "org.freedesktop.DBus.Properties")
items = colp.Get("org.freedesktop.Secret.Collection", "Items")
chrome_item = None
for p in items:
    try:
        d = dbus.Interface(bus.get_object("org.freedesktop.secrets", str(p)),
                           "org.freedesktop.DBus.Properties").GetAll("org.freedesktop.Secret.Item")
        if "chrome safe storage" in str(d.get("Label", "")).lower():
            chrome_item = str(p); break
    except Exception:
        continue
if not chrome_item:
    print("NO_CHROME_ITEM"); sys.exit(1)

# 3) GetSecret -> (ref, fmt)  (ref 是密文引用 objectpath)
it = dbus.Interface(bus.get_object("org.freedesktop.secrets", chrome_item),
                    "org.freedesktop.Secret.Item")
ref, fmt = it.GetSecret(dbus.String("text/plain"))
print("ref:", str(ref), "fmt:", str(fmt))

# 4) GetSecrets(session, {item: ref}) -> {item: (rep, repfmt)}
GetSecrets = dbus.Interface(bus.get_object("org.freedesktop.secrets", svc_path),
                            "org.freedesktop.Secret.Service")
res = GetSecrets.GetSecrets(session_path, {chrome_item: ref})
rep, repfmt = list(res.values())[0]
v = bytes(bytearray(rep))
n = struct.unpack(">I", v[:4])[0]
key = v[4:4 + n]
print("密钥 %d 字节" % len(key))

# 5) 解 Chrome Cookies
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
            p = c.update(enc[3:19]) + c.finalize()
            ln = struct.unpack(">I", p[:4])[0]; pt = p[4:4 + ln]
        pairs["%s=%s" % (name, pt.decode("utf-8", "replace"))] = True
    except Exception as e:
        print("解 %s 失败: %s" % (name, type(e).__name__))
print("解密 cookie: %s" % list(pairs.keys()))
if pairs:
    with open(OUT, "w") as f:
        f.write("; ".join(pairs))
    os.chmod(OUT, 0o600)
    print("WROTE %d 条" % len(pairs))
else:
    print("EMPTY")
