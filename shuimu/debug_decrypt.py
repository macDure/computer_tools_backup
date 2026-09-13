#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_decrypt.py — 密钥×派生方法矩阵测试, 定位能解密 newsmth cookie 的组合。
ckprobe 跑。值不进 stdout。"""
import os, sys, glob, sqlite3, hashlib, base64, copy
os.environ.setdefault("XDG_RUNTIME_DIR", "/host-run-user")
import gi
gi.require_version("GLib", "2.0"); gi.require_version("Gio", "2.0")
from gi.repository import GLib, Gio
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
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

secrets = {}
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
    secrets[str(lab)] = sec

def pbd(key, iters):
    return PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt",
                      iterations=iters).derive(key)

def variants(keytext):
    """一个 keyring 明文 -> 若干 AES key 候选"""
    out = []
    raw = keytext
    out.append(("raw16direct", raw if len(raw) == 16 else None))
    try:
        dec = base64.b64decode(keytext)
        out.append(("b64direct", dec if len(dec) == 16 else None))
        out.append(("b64+pbkdf2x1", pbd(dec, 1)))
        out.append(("b64+pbkdf2x1003", pbd(dec, 1003)))
        out.append(("b64+sha1", hashlib.sha1(dec).digest()))
    except Exception:
        pass
    out.append(("raw+pbkdf2x1", pbd(raw, 1)))
    out.append(("raw+pbkdf2x1003", pbd(raw, 1003)))
    if keytext == b"peanuts":
        out.append(("peanuts", hashlib.sha1(b"saltysalt").digest()))
    return [(n, k) for n, k in out if k]

# 取 cookie
encs = []
for db in sorted(glob.glob("/home/mac/.config/google-chrome/*/Cookies")):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for host, name, enc in con.execute(
            "select host_key,name,encrypted_value from cookies where host_key like '%newsmth%' and name like 'main[%'"):
        encs.append((host, name, enc))
print(f"待解密 cookie: {len(encs)} 条")

if not encs:
    print("NO_COOKIES"); sys.exit(0)

target = None
for h, n, e in encs:
    if n == "main[UTMPUSERID]":
        target = (h, n, e); break
target = target or encs[0]
h, n, enc = target
print(f"目标: {n} prefix={enc[:3]!r} len={len(enc)}")

# 矩阵
ok = False
for lab, keytext in secrets.items():
    if not keytext or len(keytext) < 8:
        continue
    for vname, vkey in variants(keytext):
        try:
            val = AESGCM(vkey).decrypt(enc[3:15], enc[15:], None)
            print(f"✅ 命中! keyring='{lab[:40]}' variant={vname} -> 值长度={len(val)}B")
            ok = True
            # 全部解
            lines = []
            for h2, n2, e2 in encs:
                v2 = AESGCM(vkey).decrypt(e2[3:15], e2[15:], None).decode("utf-8")
                lines.append(f"{n2}={v2}")
            out = "/home/mac/.hermes/scripts/shuimu_daily/.nf_cookie"
            with open(out, "w") as f:
                f.write("; ".join(dict.fromkeys(lines)) + "\n")
            os.chmod(out, 0o600)
            print(f"OK 全部 {len(encs)} 条解密并写入 .nf_cookie ({len(lines)} 条)")
            sys.exit(0)
        except Exception as ex:
            print(f"  ✗ {lab[:30]:32s} {vname:16s} {type(ex).__name__}")
if not ok:
    print("ALL_FAIL")
