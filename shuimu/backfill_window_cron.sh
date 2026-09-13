#!/bin/bash
# backfill_window_cron.sh — no_agent cron 入口: 每 2 小时 :30 (北京时间) 领队首 1 个 4 小时窗
# 铁律: 单会话锁由脚本内 login_with_retry 强制; 本 wrapper 只做环境固定 + 崩溃记账。
# no_agent 语义: stdout 非空=verbatim 发飞书, 空=静默。
# 脚本 stdout 只在"飞书直发失败需兜底"时输出, 平时静默(诊断落 logs/backfill_window.log)。
# 09-09 修复: 非零退出(脚本 crash)必须走 --mark-failed 记账, 否则 3 连败冷却永不触发。
export TZ=Asia/Shanghai
PY=/opt/data/venvs/shuimu/bin/python
DIR=/opt/data/scripts/shuimu_daily
rc=0
"$PY" "$DIR/backfill_window.py" "$@" || rc=$?
if [ "$rc" -ne 0 ] && [ -z "$1" ]; then
    # 仅正常运行模式(非 --status/--init)的 crash 才记账
    echo "[cron] backfill_window.py exit=$rc, 记账 MARK_FAILED" >&2
    "$PY" "$DIR/backfill_window.py" --mark-failed "脚本crash exit=$rc"
fi
exit "$rc"
