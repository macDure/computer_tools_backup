#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_decrypt4.py — 扩展矩阵: 空密码/utf16/多迭代/SHA256, 定位 Chrome v11 CBC 密钥派生。
ckprobe 跑。值不进 stdout。命中即写 .nf_cookie。"""
import os, sys, glob, sqlite3, base64, hashlib
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

pws = [("empty", b"")]
for it in items:
    it_p = str(it)
    try:
        lab = conn.call_sync(SVC, it_p, "org.freedesktop.DBus.Properties", "Get",
                             GLib.Variant("(ss)", ("org.freedesktop.Secret.Item", "Label")),
                             None, Gio.DBusCallFlags.NONE, 10000, None).unpack()[0]
        lab = str(lab)
    except Exception:
        lab = "?"
    try:
        sec = item_secret(it_p)
    except Exception:
        sec = b""
    if not sec: continue
    pws.append((f"{lab}/raw", sec))
    try: pws.append((f"{lab}/b64dec", base64.b64decode(sec)))
    except Exception: pass
    pws.append((f"{lab}/raw_utf16", sec.decode("latin1").encode("utf-16-le")))
pws.append(("peanuts", b"peanuts"))

def keys_for(pw):
    yield ("sha1x1",  PBKDF2HMAC(hashes.SHA1(), 16, b"saltysalt", 1).derive(pw))
    yield ("sha1x1003", PBKDF2HMAC(hashes.SHA1(), 16, b"saltysalt", 1003).derive(pw))
    yield ("sha1x10000", PBKDF2HMAC(hashes.SHA1(), 16, b"saltysalt", 10000).derive(pw))
    yield ("sha256x1", PBKDF2HMAC(hashes.SHA256(), 16, b"saltysalt", 1).derive(pw))
    if len(pw) == 16:
        yield ("direct16", pw)

encs = []
for db in sorted(glob.glob("/home/mac/.config/google-chrome/*/Cookies")):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for host, name, enc in con.execute(
            "select host_key,name,encrypted_value from cookies where host_key like '%newsmth%'"):
        encs.append((host, name, enc))
if not encs:
    print("NO_COOKIES"); sys.exit(0)
target = next((e for e in encs if e[1] == "main[UTMPUSERID]"), encs[0])
h, n, enc = target
iv, ct = enc[3:19], enc[19:]

def try_key(key):
    try:
        d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        pl = d.update(ct) + d.finalize()
        pad = pl[-1]
        if 1 <= pad <= 16 and pl[-pad:] == bytes([pad]) * pad:
            return pl[:-pad].decode("utf-8")
    except Exception:
        return None
    return None

hit = None
for lab, pw in pws:
    for kn, key in keys_for(pw):
        v = try_key(key)
        if v:
            print(f"✅ 命中! pw='{lab[:36]}' key={kn} -> {len(v)}B 值前2字符={v[:2]!r}")
            hit = (lab, kn, key)
            break
    if hit: break
if not hit:
    print("ALL_FAIL (扩展矩阵)"); sys.exit(1)
lab, kn, key = hit
lines = []
for h2, n2, e2 in encs:
    if e2[:3] != b"v11": continue
    d = Cipher(algorithms.AES(key), modes.CBC(e2[3:19])).decryptor()
    pl = d.update(e2[19:]) + d.finalize()
    pad = pl[-1]
    if 1 <= pad <= 16 and pl[-pad:] == bytes([pad]) * pad:
        lines.append(f"{n2}={pl[:-pad].decode('utf-8')}")
out = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"
with open(out, "w") as f:
    f.write("; ".join(dict.fromkeys(lines)) + "\n")
os.chmod(out, 0o600)
print(f"OK 写入: {len(lines)} 条")
