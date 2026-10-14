#!/usr/bin/env python3
"""10808 端口持有者归属判定 (09-08 事故修复地基: 任何"让出/抢占"决策前先反查 inode)。

用法: v2rayn_owner.py [port]   默认 10808
输出单行 (可 grep):
  OWNER=gui|fallback|none pid=<pid|-> uid=<uid|-> [conf=high|low]
判定:
  - 10808 无 LISTEN socket → none (高置信)
  - 持有 LISTEN socket inode 的是 uid=0 的 xray → fallback (高置信, inode 精确)
  - inode 无法 fd 反查 (runner 容器 cgroup 看不到宿主进程 fd) 但存在 uid!=0
    的 xray → gui (低置信: 依赖"唯一非 root xray 就是 GUI 核心"的域知识,
    该 xray 与持有进程为同一实例, 竞态风险极低)
  - 其余 → other (保守: 按 none 处理并记 other)
必须用 docker exec -u 0 (host pid ns) 运行。
"""
import glob
import os
import subprocess
import sys


def listen_inodes(port):
    out = []
    hx = "%04X" % port
    for t in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = open(t).readlines()[1:]
        except OSError:
            continue
        for line in lines:
            p = line.split()
            if len(p) >= 10 and p[1].endswith(":" + hx) and p[3] == "0A":
                out.append(p[9])
    return sorted(set(out))


def xray_procs():
    """返回 [(pid, uid, cmdline)] —— pgrep -ax xray 拿 cmdline (不依赖 /proc/exe,
    容器 root 无 CAP_SYS_PTRACE 时跨 uid readlink exe 会 EACCES, 09-08 实测)。
    Uid 从 /proc/pid/status 读 (任何用户可读)。"""
    procs = []
    try:
        out = subprocess.run(
            ["pgrep", "-ax", "xray"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return procs
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        pid = parts[0].strip()
        if not pid.isdigit():
            continue
        cmdline = parts[1] if len(parts) > 1 else ""
        if "xray" not in os.path.basename(cmdline.split(None, 1)[0] if cmdline else ""):
            continue
        try:
            uid = None
            for l in open("/proc/%s/status" % pid):
                if l.startswith("Uid:"):
                    uid = l.split()[1]
                    break
            procs.append((pid, uid if uid is not None else "-", cmdline))
        except OSError:
            continue
    return procs


def holds_inode(pid, inode):
    d = "/proc/%s/fd" % pid
    try:
        fds = os.listdir(d)
    except OSError:
        return None  # 看不到 (cgroup 隔离)
    for f in fds:
        try:
            if os.readlink(d + "/" + f) == "socket:[%s]" % inode:
                return True
        except OSError:
            pass  # EACCES: 容器 root 无 SYS_PTRACE, 跨 uid fd readlink 被拒 (09-08 实测)
    return False


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 10808
    inos = listen_inodes(port)
    if not inos:
        print("OWNER=none pid=- uid=-")
        return 0
    ino = inos[0]
    seen = {}
    for pid, uid, cmd in xray_procs():
        seen[pid] = (uid, cmd)
    # 1) inode 精确匹配 (同 cgroup 的兜底 xray 必能反查)
    for pid, (uid, exe) in seen.items():
        h = holds_inode(pid, ino)
        if h:
            owner = "fallback" if uid == "0" else "gui"
            print("OWNER=%s pid=%s uid=%s conf=high" % (owner, pid, uid))
            return 0
        if h is None:
            continue  # fd 不可见, 走低置信路径
        # h is False: 该 xray 不持有 (可能有别的实例)
    # 2) fd 反查全部不可见 (或无 xray 可查) → 用 uid 推断
    guis = [(p, u, e) for p, (u, e) in seen.items() if u != "0"]
    fallbacks = [(p, u, e) for p, (u, e) in seen.items() if u == "0"]
    if guis:
        p, u, e = guis[0]
        print("OWNER=gui pid=%s uid=%s conf=low" % (p, u))
        return 0
    if fallbacks:
        p, u, e = fallbacks[0]
        print("OWNER=fallback pid=%s uid=%s conf=low" % (p, u))
        return 0
    print("OWNER=other pid=- uid=-")
    return 0


if __name__ == "__main__":
    sys.exit(main())
