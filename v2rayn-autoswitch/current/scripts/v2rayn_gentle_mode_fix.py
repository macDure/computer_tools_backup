#!/usr/bin/env python3
"""v2rayn_gentle_mode_fix.py — 幂等补丁: autoswitch.py 温柔模式 (不杀运行中的 GUI)

背景 (09-08): 用户在自己宿主 TTY 里 ./v2rayN 跑 GUI, 要求自动脚本更新订阅/切节点时
不杀他的进程。检测方式: pgrep ./v2rayN 或 <vdir>/v2rayN (GUI 二进制级精确, 不含 xray 核心)。

补丁:
  R1 load_config 默认加 respect_running=True
  R2 main() 开头探测 GUI 在跑 → result["gentle"]; 打 GENTLE 日志
  R3 停止 v2rayN 段: gentle 时整段跳过 (含"残留确认", 否则会中止)
  R4 _restart_and_verify: gentle 时不重启/不拉起, 仅停 root 身份的兜底 xray 让出 10808

幂等: 标记 GENTLE_MODE_PATCH_V1; 已打→ALREADY_PATCHED; 锚点失配→ANCHOR_MISS exit 3
退出码: 0=完成 3=锚点失配/失败
"""
import sys

MARK = "GENTLE_MODE_PATCH_V1"


def main():
    path = sys.argv[1]
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("ALREADY_PATCHED")
        return 0

    def sub(old, new, label):
        nonlocal src
        n = src.count(old)
        if n != 1:
            print("ANCHOR_MISS %s (count=%d)" % (label, n))
            return False
        src = src.replace(old, new, 1)
        return True

    ok = True

    # R1: load_config 默认项
    ok &= sub(
        '        "prefer_after_update": "c1s1,c1s2",\n',
        '        "prefer_after_update": "c1s1,c1s2",\n'
        '        "respect_running": True,  # GENTLE_MODE_PATCH_V1: 不杀运行中的 GUI\n',
        "load_config",
    )

    # R2: main() 开头探测 (此锚点处 cfg/vdir/result 均已定义)
    old2 = '    log.info("=== autoswitch 开始 (dry_run=%s, no_restart=%s) ===" % (args.dry_run, args.no_restart))\n'
    new2 = (
        '    # GENTLE_MODE_PATCH_V1: 探测 v2rayN GUI 是否运行中 (用户 TTY 手动启动, 不杀不重启)\n'
        '    def _gui_pids():\n'
        '        _pids = []\n'
        '        for _pat in (r"\\./v2rayN([[:space:]]|$)", re.escape(vdir) + r"/v2rayN([[:space:]]|$)"):\n'
        '            _pids.extend(_pgrep(_pat))\n'
        '        return sorted(set(_pids))\n'
        '    respect = bool(cfg.get("respect_running", True))\n'
        '    v2rayn_running = bool(_gui_pids())\n'
        '    result["gentle"] = bool(respect and v2rayn_running)\n'
        '    if result["gentle"]:\n'
        '        log.info("GENTLE: 检测到运行中的 v2rayN GUI (pid=%s), 本次不杀不重启" % ",".join(map(str, _gui_pids())))\n'
        '\n'
        + old2
    )
    ok &= sub(old2, new2, "main head")

    # R3: 停止段整体包进 else (真实锚点: 分隔符是 ",".join)
    old3 = (
        '    # ---- 2. 停 v2rayN\n'
        '    pids = find_v2rayn_pids(vdir)\n'
        '    if pids:\n'
        '        log.info("停止 v2rayN (pid=%s)" % ",".join(map(str, pids)))\n'
        '        if not stop_v2rayn(vdir, log):\n'
        '            log.error("无法停止 v2rayN, 放弃本次操作 (未修改任何文件)")\n'
        '            result["exit_code"] = 2\n'
        '            finish(log, result)\n'
        '            return 2\n'
        '        log.info("v2rayN 已全部退出")\n'
        '    else:\n'
        '        log.info("v2rayN 未在运行")\n'
        '\n'
        '    # 写文件前再次确认无残留进程 (吸取孤儿核心教训)\n'
        '    if find_v2rayn_pids(vdir):\n'
        '        log.error("v2rayN 进程确认未退净, 放弃本次操作")\n'
        '        result["exit_code"] = 2\n'
        '        finish(log, result)\n'
        '        return 2\n'
    )
    new3 = (
        '    # ---- 2. 停 v2rayN (GENTLE_MODE_PATCH_V1: GUI 在运行则不杀)\n'
        '    if respect and v2rayn_running:\n'
        '        log.info("GENTLE: v2rayN GUI 运行中 (pid=%s), 本次跳过停止" % ",".join(map(str, _gui_pids())))\n'
        '    else:\n'
        '        pids = find_v2rayn_pids(vdir)\n'
        '        if pids:\n'
        '            log.info("停止 v2rayN (pid=%s)" % ",".join(map(str, pids)))\n'
        '            if not stop_v2rayn(vdir, log):\n'
        '                log.error("无法停止 v2rayN, 放弃本次操作 (未修改任何文件)")\n'
        '                result["exit_code"] = 2\n'
        '                finish(log, result)\n'
        '                return 2\n'
        '            log.info("v2rayN 已全部退出")\n'
        '        else:\n'
        '            log.info("v2rayN 未在运行")\n'
        '\n'
        '        # 写文件前再次确认无残留进程 (吸取孤儿核心教训)\n'
        '        if find_v2rayn_pids(vdir):\n'
        '            log.error("v2rayN 进程确认未退净, 放弃本次操作")\n'
        '            result["exit_code"] = 2\n'
        '            finish(log, result)\n'
        '            return 2\n'
    )
    ok &= sub(old3, new3, "stop block")

    # R4: _restart_and_verify 温柔分支 (vdir 是该函数形参; xray 只杀 root 身份的)
    old4 = (
        '    if no_restart:\n'
        '        log.info("--no-restart: 跳过重启 v2rayN")\n'
        '        return\n'
        '    if cfg["restart_v2rayn"]:\n'
    )
    new4 = (
        '    if no_restart:\n'
        '        log.info("--no-restart: 跳过重启 v2rayN")\n'
        '        return\n'
        '    if result.get("gentle"):  # GENTLE_MODE_PATCH_V1\n'
        '        log.info("GENTLE: 保留运行中的 v2rayN GUI 不重启; 停 root 兜底 xray 让出 10808 供 GUI 接管")\n'
        '        for _p in os.listdir("/proc"):\n'
        '            if not _p.isdigit():\n'
        '                continue\n'
        '            try:\n'
        '                _exe = os.readlink("/proc/%s/exe" % _p)\n'
        '            except Exception:\n'
        '                continue\n'
        '            if "xray" in _exe and _exe.startswith(vdir):\n'
        '                try:\n'
        '                    if os.stat("/proc/%s" % _p).st_uid == 0:\n'
        '                        os.kill(int(_p), 15)\n'
        '                        log.info("GENTLE: 已停 root 兜底 xray (pid=%s)" % _p)\n'
        '                except Exception:\n'
        '                    pass\n'
        '        result["v2rayn_restarted"] = False\n'
        '        result["proxy_restored"] = True\n'
        '        return\n'
        '    if cfg["restart_v2rayn"]:\n'
    )
    ok &= sub(old4, new4, "restart verify")

    if not ok:
        print("FAILED (锚点失配, 文件未修改)")
        return 3

    open(path, "w", encoding="utf-8").write(src)
    print("PATCHED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
