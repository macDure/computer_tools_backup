#!/usr/bin/env python3
"""verify_key.py — 验证 keyring 取到的 Chrome Safe Storage 密钥能解密真实 cookie。
ckprobe 容器跑 (uid 1000, XDG_RUNTIME_DIR=/host-run-user)。值打码。"""
import os, sys, glob, sqlite3, hashlib, base64
os.environ.setdefault("XDG_RUNTIME_DIR", "/host-run-user")
sys.path.insert(0, "/usr/lib/python3/dist-packages")
import gi
gi.require_version("GLib", "2.0"); gi.require_version("Gio", "2.0")
from gi.repository import GLib, Gio
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

S = "org.freedesktop.secrets"
conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)

def call(path, iface, method, variant):
    return conn.call_sync(S, path, iface, method, variant,
                          None, Gio.DBusCallFlags.NONE, 15000, None).unpack()

# 打开会话: 返回 (o,o) 套一层, 路径含 "session"
u = call("/org/freedesktop/secrets", "org.freedesktop.Secret.Service", "OpenSession",
         GLib.Variant("(sv)", (("plain", GLib.Variant("s", "plain")))))
flat = [str(x) for x in (u[0] if isinstance(u[0], (list, tuple)) else u)]
sess = next((x for x in flat if "session" in x), str(u[-1]))
print("session:", sess)

def get_secret_bytes(item_p):
    r = call(item_p, "org.freedesktop.Secret.Item", "GetSecret", GLib.Variant("(o)", (sess,)))
    inner = r[0] if len(r) == 1 and isinstance(r[0], (list, tuple)) else r
    for x in inner:
        if isinstance(x, (list, tuple)) and x and isinstance(x[0], int):
            return bytes(x)
    return b""

# 找 Chrome Safe Storage item
items = list(conn.call_sync(S, "/org/freedesktop/secrets/collection/login",
                            "org.freedesktop.DBus.Properties", "Get",
                            GLib.Variant("(ss)", ("org.freedesktop.Secret.Collection", "Items")),
                            None, Gio.DBusCallFlags.NONE, 10000, None).unpack()[0])
key = None
for it in items:
    lab = str(conn.call_sync(S, str(it), "org.freedesktop.DBus.Properties", "Get",
                             GLib.Variant("(ss)", ("org.freedesktop.Secret.Item", "Label")),
                             None, Gio.DBusCallFlags.NONE, 10000, None).unpack()[0])
    if lab == "Chrome Safe Storage":
        b = get_secret_bytes(str(it))
        try:
            key = base64.b64decode(b)
        except Exception:
            key = None
        print(f"Chrome Safe Storage: {len(b)}B, base64-> {len(key) if key else 0}B")
        break

def dec(enc, key):
    k = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt",
                   iterations=1).derive(key)
    return AESGCM(k).decrypt(enc[3:15], enc[15:], None)

if key:
    # 验证: 解密 m.newsmth.net 的匿名 cookie (证明 key 正确)
    n = 0
    for db in glob.glob("/home/mac/.config/google-chrome/*/Cookies"):
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute("select host_key,name,length(encrypted_value) from cookies "
                           "where host_key like '%newsmth%' or host_key like '%mysmth%'").fetchall()
        for host, name, ln in rows:
            enc = con.execute("select encrypted_value from cookies where host_key=? and name=?",
                              (host, name)).fetchone()[0]
            try:
                v = dec(enc, key).decode()
                n += 1
                shown = v[:2] + "***"
                print(f"  ✓ 解密成功: {host} {name} (val={shown}, len={len(v)})")
            except Exception as e:
                print(f"  ✗ {host} {name}: {type(e).__name__}")
    print(f"\n结论: 密钥解密 {'成功' if n else '失败'} ({n} 条) — 链路 "
          f"{'100% live, 登录后即可抽 5 条登录 cookie' if n else '需排查'}")
else:
    print("NO_KEY")
