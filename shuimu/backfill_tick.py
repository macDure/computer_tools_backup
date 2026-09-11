#!/usr/bin/env python3
# backfill_tick.py — 水木大回补 tick 状态机 (no_agent cron 每 10min, 断点自愈)
# 计划: 2026-01-01~08-31 (243天/1458窗) -> 2025 全年 (365天/2190窗), 每批 20 天 (120 窗)。
# 机制: 本 tick 只做一步 — 无活动批次则入队一批; 有则检查进度, 全 done 则里程碑飞书+下一批。
#       实际爬取由看门狗 (e2598086, 每2min) 自动完成: 队列有 pending 就单账号串行开爬,
#       爬完自动归档+发布 stock_research_mac+push+飞书。本脚本绝不自己开爬虫进程。
# 自愈: 容器/进程重启不丢进度 (.backfill_state.json 断点); 批次 8h 超时/3h 无进展 -> 告警+跳过(未爬窗留 pending 后续补)。
import json, os, time, datetime as dt, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PYV = os.environ.get("SHUIMU_PYTHON", "/opt/data/venvs/scrapling/bin/python")
QUEUE = os.path.join(HERE, "backfill_queue.json")
STATE = os.path.join(HERE, ".backfill_state.json")
LOGF = os.path.join(HERE, "logs", "backfill_tick.log")
TZ = dt.timezone(dt.timedelta(hours=8))
BATCH_DAYS = 10
BATCH_TIMEOUT = 8 * 3600
STALL_LIMIT = 3 * 3600
PHASES = [("2026", dt.date(2026, 1, 1), dt.date(2026, 8, 31)),
          ("2025", dt.date(2025, 1, 1), dt.date(2025, 12, 31))]

def now_bj():
    return dt.datetime.now(TZ)

def log(m):
    line = "[%s] %s" % (now_bj().strftime("%Y-%m-%d %H:%M:%S"), m)
    os.makedirs(os.path.dirname(LOGF), exist_ok=True)
    with open(LOGF, "a") as f:
        f.write(line + "\n")

def feishu(text):
    try:
        p = subprocess.run([PYV, os.path.join(HERE, "deliver_feishu.py"), "-"],
                           input=text.encode(), capture_output=True, timeout=60)
        log("feishu %s: %s" % ("OK" if p.returncode == 0 else "FAIL", text[:80]))
        return p.returncode == 0
    except Exception as e:
        log("feishu 异常: %s" % e)
        return False

def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}

def save_state(st):
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)

def batch_labels(start, end):
    out, d = [], start
    while d <= end:
        for i in range(6):
            out.append("%s %02d:00-%02d:00" % (d.isoformat(), i*4, i*4+4))
        d += dt.timedelta(days=1)
    return out

def main():
    st = load_state()
    phase_name, ph_from, ph_to = None, None, None
    for name, f_, t_ in PHASES:
        if st.get("phase") == name:
            phase_name, ph_from, ph_to = name, f_, t_
            break
    if not phase_name and not st.get("phase"):
        phase_name, ph_from, ph_to = "2026", dt.date(2026, 1, 1), dt.date(2026, 8, 31)
    if not phase_name:
        return 0   # done

    st.setdefault("cursor", ph_from.isoformat())
    st.setdefault("done_windows", 0)
    cursor = dt.date.fromisoformat(st["cursor"])
    if cursor > ph_to:
        # 当前 phase 完成
        st["phase"] = "done" if phase_name == "2025" else "2025"
        if phase_name == "2026":
            st["cursor"] = "2025-01-01"
            st["batch"] = None
        save_state(st)
        log(">>> %s 区间完成" % phase_name)
        feishu("🏁 %s 回补完成 (累计 %d 窗已归档)!%s" %
               (phase_name, st["done_windows"],
                " 开始 2025 全年回补 (365 天, 约 19 批)" if phase_name == "2026" else ""))
        return 0

    batch = st.get("batch")
    if not batch:
        # 入队新批次
        start = cursor
        end = min(start + dt.timedelta(days=BATCH_DAYS - 1), ph_to)
        r = subprocess.run([PYV, os.path.join(HERE, "make_backfill_range.py"),
                            "--start", start.isoformat(), "--end", end.isoformat()],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            st["fails"] = st.get("fails", 0) + 1
            save_state(st)
            log("入队失败: %s" % (r.stderr or r.stdout)[:120])
            if st["fails"] >= 3:
                feishu("❌ 回补入队连续失败 %d 次, 驱动暂停等我介入。" % st["fails"])
            return 0
        labels = batch_labels(start, end)
        st["batch"] = {"start": start.isoformat(), "end": end.isoformat(),
                       "labels": labels, "t0": time.time(),
                       "last_prog": time.time(), "last_done": -1,
                       "total_windows": st["done_windows"]}
        st["fails"] = 0
        save_state(st)
        log("新批次 %s~%s: %d 窗入队, 等看门狗爬" % (start, end, len(labels)))
        feishu("🚀 回补批次开始: %s ~ %s (%d 窗)\n看门狗单账号串行爬, 爬完自动归档+发布+push, 我盯进度。" %
               (start, end, len(labels)))
        return 0

    # 检查活动批次
    done = 0
    try:
        q = json.load(open(QUEUE))
        m = {t.get("label"): t.get("status") for t in q["tasks"]}
        done = sum(1 for l in batch["labels"] if m.get(l) == "done")
    except Exception as e:
        log("读队列失败: %s" % e); return 0
    tot = len(batch["labels"])
    now = time.time()
    if done != batch["last_done"]:
        batch["last_done"], batch["last_prog"] = done, now
        log("批次 %s~%s 进度 %d/%d" % (batch["start"], batch["end"], done, tot))
        save_state(st)
    if done >= tot:
        st["done_windows"] = batch["total_windows"] + done
        st["batch"] = None
        st["cursor"] = (dt.date.fromisoformat(batch["end"]) + dt.timedelta(days=1)).isoformat()
        save_state(st)
        feishu("✅ 回补批次完成: %s ~ %s (%d 窗)\n累计归档 %d 窗, 文档已发布 stock_research_mac 并 push。下一批即将入队。" %
               (batch["start"], batch["end"], done, st["done_windows"]))
        return 0
    if now - batch["t0"] > BATCH_TIMEOUT or now - batch["last_prog"] > STALL_LIMIT:
        why = "8h 超时" if now - batch["t0"] > BATCH_TIMEOUT else "3h 无进展(疑似风控/槽满)"
        st["fails"] = st.get("fails", 0) + 1
        feishu("⚠️ 回补批次 %s~%s 未完成 (%d/%d, %s)。\n未爬完的窗保持 pending, 我每 10 分钟检查, 连续 2 次失败会跳过本批继续后面日期(最后统一补洞), 并通知你。" %
               (batch["start"], batch["end"], done, tot, why))
        log("批次异常: %s (%d/%d)" % (why, done, tot))
        if st["fails"] >= 2:
            # 跳过本批 (失败窗留 pending, 游标前进), 继续后续日期; 最后由手动补洞收口
            st["cursor"] = (dt.date.fromisoformat(batch["end"]) + dt.timedelta(days=1)).isoformat()
            st["batch"] = None
            st["fails"] = 0
            save_state(st)
            log("跳过本批, 游标 -> %s" % st["cursor"])
        else:
            # 首次失败: 重置计时重试本批 (pending 还在, 看门狗会重爬)
            batch["t0"] = now; batch["last_prog"] = now
            save_state(st)
    return 0

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("FATAL: %s: %s" % (type(e).__name__, e))
        try:
            feishu("❌ 回补 tick 自身异常: %s — 已停止, 等我介入。" % str(e)[:120])
        except Exception:
            pass
