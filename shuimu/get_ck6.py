#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_ck6.py — GLib.Variant + Gio.DBusConnection 取 Chrome 密钥 + 解 newsmth cookie。
ckprobe 容器跑 (uid 1000, XDG_RUNTIME_DIR=/host-run-user)。值不进 stdout。"""
import sys, os, sqlite3, hashlib, struct
os.environ["XDG_RUNTIME_DIR"] = "/host-run-user"
import gi
gi.require_version("Gio", "2.0"); gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OUT = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"
SECRETS = "org.freedesktop.secrets"
SVC = "/org/freedesktop/secrets"

conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
def call(path, iface, method, variant):
    res = conn.call_sync(SECRETS, path, iface, method, variant, None,
                         Gio.DBusCallFlags.NONE, -1, None)
    return res.unpack()

# 1) OpenSession("plain", "") -> (o, v)
session, _out = call(SVC, "org.freedesktop.Secret.Service", "OpenSession",
                     GLib.Variant("(sv)", ("plain", GLib.Variant("s", ""))))
print("session:", str(session))

# 2) SearchItems(a{ss}) -> (ao, ao)
unlocked, locked = call(SVC, "org.freedesktop.Secret.Service", "SearchItems",
                        GLib.Variant("(a{ss})", ({"description": "Chrome Safe Storage"},)))
items = list(unlocked) + list(locked)
print("items: %d (unlocked=%d locked=%d)" % (len(items), len(unlocked), len(locked)))
if not items:
    print("NO_ITEMS"); sys.exit(1)

key = None
for it in items:
    ito = str(it)
    label = conn.call_sync(SECRETS, ito, "org.freedesktop.DBus.Properties", "Get",
                           GLib.Variant("(ss)", ("org.freedesktop.Secret.Item", "Label")),
                           None, -1, None).unpack()[0]
    if "chrome safe storage" not in str(label).lower():
        continue
    ref, fmt = call(ito, "org.freedesktop.Secret.Item", "GetSecret",
                    GLib.Variant("(s)", ("text/plain",)))
    secrets = call(SVC, "org.freedesktop.Secret.Service", "GetSecrets",
                   GLib.Variant("(oa{o(oayays)})", (session, {ito: ref})))
    rep, repfmt = list(secrets.values())[0]
    v = bytes(bytearray(rep[1]))
    n = struct.unpack(">I", v[:4])[0]
    key = v[4:4 + n]
    print("密钥 %d 字节" % len(key))
    break
if not key:
    print("NO_CHROME_KEY"); sys.exit(1)

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
    nkey = len([k for k in pairs if "UTMPKEY" in k or "PASSWORD" in k])
    print("WROTE %d 条 (核心登录cookie %s/2)" % (len(pairs), nkey))
else:
    print("EMPTY")
