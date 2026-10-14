#!/usr/bin/env python3
# v2rayN 08:29 autoswitch 成功通知 (订阅 diff + 节点切换)
# 只读订阅库(mode=ro, 不锁 GUI 在用的 sqlite) + 节点名快照 diff + deliver_feishu 直发
# 用法: python3 v2rayn_sub_notify.py [--dry-run]
#   --dry-run  只打印会发的消息, 不发送, 不更新快照
# 退出码: 0=无事可报(静默) 2=已发送/已演练 3=发送失败(调用方记日志, 仍静默收尾)
import json
import os
import sqlite3
import subprocess
import sys

# 路径自适应: Hermes 容器宿主挂载点 = /host-home; runner 容器内 = /home/mac
def snapshot_path(base, state_dir="/opt/data/state"):
    """Return a writable snapshot path in both container mount layouts."""
    if base == "/host-home":
        return os.path.join(state_dir, "v2rayn_node_snapshot.json")
    return os.path.join(base, "v2rayN-linux-64/autoswitch/node_snapshot.json")


_BASE = next((b for b in ("/home/mac", "/host-home")
              if os.path.exists(b + "/v2rayN-linux-64/guiConfigs/guiNDB.db")), None)
if _BASE is None:
    print("找不到 v2rayN 安装目录 (/home/mac 或 /host-home)")
    sys.exit(3)
AW = _BASE + "/v2rayN-linux-64/autoswitch"
DB = _BASE + "/v2rayN-linux-64/guiConfigs/guiNDB.db"
STATE_DIR = "/opt/data/state" if _BASE == "/host-home" else AW
SNAP = snapshot_path(_BASE, STATE_DIR)
FAILED_SNAP = os.path.join(STATE_DIR, "v2rayn_last_notify_failed.txt")
DELIV = next((p for p in (
    "/opt/data/scripts/shuimu_daily/deliver_feishu.py",
    "/home/mac/.hermes/scripts/shuimu_daily/deliver_feishu.py",
    "/host-home/.hermes/scripts/shuimu_daily/deliver_feishu.py")
    if os.path.exists(p)), None)
DRY = "--dry-run" in sys.argv


def main():
    try:
        res = json.load(open(os.path.join(AW, "last_result.json")))
    except Exception as e:
        print("last_result 读取失败: %s" % e)
        return 3
    if res.get("dry_run"):
        print("dry_run 结果, 不通知")
        return 0
    # 防陈旧: last_result 必须来自近 120 分钟内的正式运行 (flock 跳过/历史文件不误报)
    try:
        from datetime import datetime, timezone
        t = datetime.fromisoformat(res["ts"])
        age = (datetime.now(timezone.utc) - t).total_seconds()
        if age > 7200:
            print("last_result 过旧 (%.0f 分钟前), 不通知" % (age / 60))
            return 0
    except Exception:
        pass

    # 当前订阅节点名 (与 autoswitch.load_servers 同查询: IsSub=1)
    try:
        con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=5)
        rows = [r[0] for r in con.execute(
            "select Remarks from ProfileItem where IsSub=1")]
        con.close()
    except Exception as e:
        print("订阅库读取失败: %s" % e)
        return 3
    cur = sorted({r for r in rows if r})
    if not cur:
        print("订阅库无节点, 不通知")
        return 0

    sub_updated = bool(res.get("sub_updated"))
    final = res.get("final_server")
    selected = res.get("selected")
    if not sub_updated and not (final and final != selected):
        print("无订阅更新且无节点切换, 静默")
        return 0

    prev = []
    try:
        prev = sorted(set(json.load(open(SNAP))))
    except Exception:
        prev = []
    new = [n for n in cur if n not in prev]
    gone = [n for n in prev if n not in cur]

    def fmt(names, limit=12):
        names = [str(n) for n in names]
        if len(names) > limit:
            return ", ".join(names[:limit]) + " 等%d个" % len(names)
        return ", ".join(names)

    lines = ["### 📡 v2rayN 订阅/节点 更新完成 (北京 %s)" % res.get("ts", "?")[:16].replace("T", " "),
             "- 节点总数: **%d**" % len(cur)]
    if sub_updated:
        lines.append("- 订阅: 已更新")
        if new:
            lines.append("- 新增 %d 个: %s" % (len(new), fmt(new)))
        if gone:
            lines.append("- 移除 %d 个: %s" % (len(gone), fmt(gone)))
        if not new and not gone:
            lines.append("- 节点集合无变化")
    if final:
        lines.append("- 当前使用: **%s**" % final)
    if res.get("gentle"):
        lines.append("- 提醒: 你的 v2rayN GUI 在运行, 助手未动 GUI; 新节点需在 GUI 里刷新订阅/重开节点列表, 切节点需手动选一次")
    lines.append("- 日志: autoswitch/logs/auto-*.log")
    msg = "\n".join(lines)

    if DRY:
        print("=== dry-run 消息预览 (未发送, 快照未更新) ===")
        print(msg)
        return 2

    out = subprocess.run(["python3", DELIV, "-"], input=msg,
                         capture_output=True, text=True, timeout=60)
    ok = "OK success" in (out.stdout or "")
    if not ok:
        # 直发失败: 更新快照防止下轮误报大 diff, 消息文本落盘留证
        print("FEISHU_FAIL\n%s" % msg)
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            json.dump(cur, open(FAILED_SNAP, "w"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
        return 3
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    json.dump(cur, open(SNAP, "w"), ensure_ascii=False, indent=1)
    print("SENT")
    return 2


if __name__ == "__main__":
    sys.exit(main())
