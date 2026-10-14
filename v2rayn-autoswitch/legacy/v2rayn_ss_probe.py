#!/usr/bin/env python3
"""Standalone ss-proxy test via xray: prove whether c1s1/c1s2 actually tunnel traffic.
Usage: v2rayn_ss_probe.py <addr> <port> <password> <method> <socks_port> <label>
"""
import sys, os, time, json, subprocess, tempfile, signal, shutil

addr, port, password, method, socks_port, label = sys.argv[1:7]
port = int(port); socks_port = int(socks_port)
xray = "/home/mac/v2rayN-linux-64/bin/xray/xray"

cfg = {
    "log": {"loglevel": "warning"},
    "inbounds": [{"tag": "socks", "port": socks_port, "listen": "127.0.0.1",
                  "protocol": "socks", "settings": {"auth": "noauth", "udp": True}}],
    "outbounds": [{"tag": "proxy", "protocol": "shadowsocks",
                   "settings": {"method": method, "password": password,
                                 "servers": [{"address": addr, "port": port}]}}],
}
fd, path = tempfile.mkstemp(suffix=".json", prefix="ssprobe-", dir="/tmp")
os.write(fd, json.dumps(cfg).encode()); os.close(fd)

proc = subprocess.Popen([xray, "run", "-c", path],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        start_new_session=True)
ok = False; http = "n/a"; t = None
try:
    for _ in range(20):
        time.sleep(0.5)
        if proc.poll() is not None:
            err = proc.stderr.read().decode("utf-8", "replace")[:300]
            print("%s: xray exited early: %s" % (label, err))
            break
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:%d/%s" % (socks_port, ""),
                                         headers={"Proxy-Connection": "close"})
            # use socks via python not available; fallback: curl
            break
        except Exception:
            pass
    # use curl for the actual proxy test (socks5)
    for attempt in range(4):
        t0 = time.time()
        r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                            "-m", "8", "-x", "socks5h://127.0.0.1:%d" % socks_port,
                            "https://www.google.com/generate_204"],
                           capture_output=True, text=True)
        t = time.time() - t0
        http = r.stdout.strip()
        if http == "204":
            ok = True
            break
        time.sleep(1)
finally:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    proc.wait()
    try:
        os.remove(path)
    except Exception:
        pass

print("%s: addr=%s:%d method=%s => http=%s time=%.2fs %s"
      % (label, addr, port, method, http, (t or 0), "OK" if ok else "FAIL"))
sys.exit(0 if ok else 1)
