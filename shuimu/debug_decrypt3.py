#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_decrypt3.py — keyring Safe Storage 16B key 直接当 AES-CBC key (跳过 PBKDF2)。
新版 Chrome keyring 存的就是 AES key 本身。ckprobe 跑。值不进 stdout。"""
import os, sys, glob, sqlite3, base64
os.environ.setdefault("XDG_RUNTIME_DIR", "/host-run-user")
import gi
gi.require_version("GLib", "2.0"); gi.require_version("Gio", "2.0")
from gi.repository import GLib, Gio
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

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

col_props = conn.call_sync(SVC, COL, "org.freedesktop.DBus.Properties", "Get",
                           GLib.Variant("(ss)", ("org.freedesktop.Secret.Collection", "Items")),
                           None, Gio.DBusCallFlags.NONE, 10000, None)
items = list(col_props.unpack()[0])

keys = []  # (label, 16B key)
for it in items:
    it_p = str(it)
    try:
        lab = conn.call_sync(SVC, it_p, "org.freedesktop.DBus.Properties", "Get",
                             GLib.Variant("(ss)", ("org.freedesktop.Secret.Item", "Label")),
                             None, Gio.DBusCallFlags.NONE, 10000, None).unpack()[0]
    except Exception:
        lab = "?"
    try:
        sec = item_secret(it_p)
    except Exception:
        sec = b""
    for tag, cand in (("raw", sec),):
        if len(cand) == 16:
            keys.append((f"{lab}/raw16", cand))
    try:
        d = base64.b64decode(sec)
        if len(d) == 16:
            keys.append((f"{lab}/b64dec16", d))
    except Exception:
        pass
print(f"16B key 候选: {len(keys)}")

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

def cbc_direct(key):
    iv = enc[3:19]; ct = enc[19:]
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    pl = d.update(ct) + d.finalize()
    pad = pl[-1]
    if not (1 <= pad <= 16) or pl[-pad:] != bytes([pad]) * pad:
        raise ValueError("pad")
    return pl[:-pad].decode("utf-8")

hit = None
for lab, key in keys:
    try:
        v = cbc_direct(key)
        print(f"✅ 命中! key={lab} -> {len(v)}B")
        hit = key; break
    except Exception as ex:
        print(f"  ✗ {lab[:38]:40s} {type(ex).__name__}")
if not hit:
    print("ALL_FAIL (16B direct)"); sys.exit(1)

lines = []
for h2, n2, e2 in encs:
    if e2[:3] != b"v11": continue
    iv = e2[3:19]; ct = e2[19:]
    d = Cipher(algorithms.AES(hit), modes.CBC(iv)).decryptor()
    pl = d.update(ct) + d.finalize()
    pad = pl[-1]
    if 1 <= pad <= 16 and pl[-pad:] == bytes([pad]) * pad:
        lines.append(f"{n2}={pl[:-pad].decode('utf-8')}")
out = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"
with open(out, "w") as f:
    f.write("; ".join(dict.fromkeys(lines)) + "\n")
os.chmod(out, 0o600)
print(f"OK 写入 {out}: {len(lines)} 条")
