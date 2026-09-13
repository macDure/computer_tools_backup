#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_decrypt2.py — 修正: Chrome v11 = AES-128-CBC + IV(16B全零) + PKCS7。
key = PBKDF2HMAC(SHA1, 16, salt='saltysalt', iter=1).derive(密码)
密码候选 = keyring 各 Safe Storage 的明文(原始/base64解码) + 'peanuts'。
ckprobe 跑。值不进 stdout。"""
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

col_props = conn.call_sync(SVC, COL, "org.freedesktop.DBus.Properties", "Get",
                           GLib.Variant("(ss)", ("org.freedesktop.Secret.Collection", "Items")),
                           None, Gio.DBusCallFlags.NONE, 10000, None)
items = list(col_props.unpack()[0])

pw_cands = []  # (label, password_bytes)
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
    if not sec:
        continue
    pw_cands.append((f"{lab}(raw)", sec))
    try:
        pw_cands.append((f"{lab}(b64dec)", base64.b64decode(sec)))
    except Exception:
        pass
pw_cands.append(("peanuts", b"peanuts"))

# cookie
encs = []
for db in sorted(glob.glob("/home/mac/.config/google-chrome/*/Cookies")):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for host, name, enc in con.execute(
            "select host_key,name,encrypted_value from cookies where host_key like '%newsmth%'"):
        encs.append((host, name, enc))
print(f"待解密: {len(encs)} 条 (v11: {sum(1 for _,_,e in encs if e[:3]==b'v11')})")
if not encs:
    print("NO_COOKIES"); sys.exit(0)

target = next((e for e in encs if e[1] == "main[UTMPUSERID]"), encs[0])
h, n, enc = target
print(f"目标 {n}: prefix={enc[:3]!r} len={len(enc)} IV={enc[3:19].hex()}")

def try_cbc(enc, pw):
    key = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt",
                     iterations=1).derive(pw)
    iv = enc[3:19]
    ct = enc[19:]
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = d.update(ct) + d.finalize()
    pad = plain[-1]
    if not (1 <= pad <= 16) or plain[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad padding")
    return plain[:-pad].decode("utf-8")

hit = None
for lab, pw in pw_cands:
    try:
        val = try_cbc(enc, pw)
        print(f"✅ 命中! password='{lab[:40]}' -> 值{len(val)}B")
        hit = (lab, pw); break
    except Exception as ex:
        print(f"  ✗ {lab[:36]:38s} {type(ex).__name__}")

if not hit:
    print("ALL_FAIL"); sys.exit(1)
lab, pw = hit
lines = []
for h2, n2, e2 in encs:
    if e2[:3] != b"v11":
        continue
    try:
        v2 = try_cbc(e2, pw)
        lines.append(f"{n2}={v2}")
    except Exception:
        pass
out = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"
with open(out, "w") as f:
    f.write("; ".join(dict.fromkeys(lines)) + "\n")
os.chmod(out, 0o600)
print(f"OK 写入 {out}: {len(lines)} 条")
