#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2rayN autoswitch 温柔模式 V2 补丁 — 幂等

事故背景 (09-08 14:10~14:32, 代理断 ~20 分钟):
  V1 逻辑在 gentle 分支会 "停 root 兜底 xray 让出 10808 供 GUI 接管",
  假设 GUI 占着 10808。实测 (inode 反查) GUI 核心并未绑上 10808,
  杀掉兜底后端口裸奔; 看门狗每 5 分钟升级 run.sh 又触发同一段杀兜底
  代码, 连续 3 个 tick RECOVERY_FAILED, 直到用户手动重开 GUI 才恢复。

V2 行为 (安全优先):
  gentle 分支不再 kill 任何 xray 进程。
  - GUI 占着 10808   -> 一切照旧, 无冲突
  - 兜底占着 10808   -> 兜底继续保代理可用, GUI 核心抢不到端口也不影响
  - 新节点在 GUI 重启 / 用户手动切换后生效
  无论哪种情况, 一次 autoswitch 运行后 10808 绝不会被脚本弄成无人监听。

用法: python3 v2rayn_gentle_v2_fix.py <autoswitch.py路径>
输出: PATCHED / ALREADY_PATCHED / ANCHOR_NOT_FOUND / V1_MISSING
"""
import sys

MARK = "GENTLE_MODE_PATCH_V2"

OLD = '''    if result.get("gentle"):  # GENTLE_MODE_PATCH_V1
        log.info("GENTLE: 保留运行中的 v2rayN GUI 不重启; 停 root 兜底 xray 让出 10808 供 GUI 接管")
        for _p in os.listdir("/proc"):
            if not _p.isdigit():
                continue
            try:
                _exe = os.readlink("/proc/%s/exe" % _p)
            except Exception:
                continue
            if "xray" in _exe and _exe.startswith(vdir):
                try:
                    if os.stat("/proc/%s" % _p).st_uid == 0:
                        os.kill(int(_p), 15)
                        log.info("GENTLE: 已停 root 兜底 xray (pid=%s)" % _p)
                except Exception:
                    pass
        result["v2rayn_restarted"] = False
        result["proxy_restored"] = True
        return'''

NEW = '''    if result.get("gentle"):  # GENTLE_MODE_PATCH_V2
        # 09-08 事故修复: gentle 下不 kill 任何 xray (V1 的 "停兜底让出 10808"
        # 在 GUI 未绑端口时会把 10808 打成裸奔, 造成 ~20 分钟代理中断)。
        # 兜底 xray 继续保代理可用; 新节点在 GUI 重启/手动切换后生效。
        _gp = int(cfg.get("main_port") or 10808)
        try:
            import socket as _gsock
            _gs = _gsock.socket(); _gs.settimeout(1)
            _gs.connect(("127.0.0.1", _gp)); _gs.close()
            _gport_up = True
        except Exception:
            _gport_up = False
        log.info("GENTLE: 保留运行中的 v2rayN GUI (不杀不重启); 亦不停兜底 xray "
                 "(10808 当前: %s); 新节点在 GUI 重启或手动切换后生效"
                 % ("监听中" if _gport_up else "未监听! 将由 5 分钟看门狗补拉"))
        result["v2rayn_restarted"] = False
        result["proxy_restored"] = _gport_up
        return'''


def main():
    if len(sys.argv) < 2:
        print("用法: %s <autoswitch.py>" % sys.argv[0])
        return 2
    path = sys.argv[1]
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("ALREADY_PATCHED")
        return 0
    if OLD not in src:
        print("ANCHOR_NOT_FOUND (V1 块不存在, 可能被 EDR 还原成原始版本; "
              "需先跑 v2rayn_gentle_mode_fix.py 补 V1 再跑本补丁)")
        return 1
    src = src.replace(OLD, NEW, 1)
    open(path, "w", encoding="utf-8").write(src)
    print("PATCHED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
