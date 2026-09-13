#!/usr/bin/env python3
"""entry.py — cron 入口: 按当前北京时间自动判定 slot 并跑爬虫

cron schedule `0 0,4,8,16 * * *` (UTC) = 北京 08/12/16/00 整点。
agent 唤醒后跑本脚本, 脚本按北京时间选 slot:
  08 -> slot 08 (今天)
  12 -> slot 12 (今天)
  16 -> slot 16 (今天)
  00 -> slot 24 (昨天, 即"午夜"收尾)
用法: entry.py            # 自动判定
      entry.py --slot 16  # 手动指定 (调试/补跑)
输出: shuimu_run 的 stdout (OUTPUT_DIR=... META=...), 供 agent 读取。
"""
import argparse
import datetime as dt
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shuimu_run as R
from shuimu_telnet import SessionBusy

TZ = dt.timezone(dt.timedelta(hours=8))
HOUR_TO_SLOT = {8: "08", 12: "12", 16: "16", 0: "24"}


def auto_slot(now_bj):
    h = now_bj.hour
    if h in HOUR_TO_SLOT:
        return HOUR_TO_SLOT[h]
    # 容错: 落在非整点 (agent 唤醒延迟/手动), 取最近的一个
    cands = sorted(HOUR_TO_SLOT.items(), key=lambda kv: min(abs(h - kv[0]), 24 - abs(h - kv[0])))
    return cands[0][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["08", "12", "16", "24"])
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args()
    now_bj = R.bj_now()
    slot = args.slot or auto_slot(now_bj)
    print("SLot=%s (auto=%s) now_bj=%s" % (slot, args.slot or "yes", now_bj.strftime("%Y-%m-%d %H:%M:%S")))
    try:
        R.run(slot, commit=not args.no_commit)
    except SessionBusy as e:
        # 2026-09-07 用户指令: 限流期禁止并发会话. 补爬/其他会话持锁时,
        # 本 slot 安静跳过(不硬抢不等待) — 不丢数据: 后续 slot(16/24)从当天
        # 00:00 重新全读, slot 24(午夜)兜底覆盖整天. 退出码 0: 这不是故障,
        # 不该触发看门狗告警, 只记录一条跳过说明.
        print("SKIPPED_SESSION_BUSY: %s" % e, flush=True)
        print("说明: 另一个水木会话正持锁(补爬/手动), 本次 %s 档跳过; 当天数据由后续 slot 补全." % slot, flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
