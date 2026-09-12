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
BATCH_DAYS = 90
BATCH_TIMEOUT = 16 * 3600
STALL_LIMIT = 3 * 3600
# 大活账号保护休息: 单轮请求量过高 -> tick 设 4h 休息, 看门狗 idle 门认账(休息期不起新爬),
# 当前运行跑完自然收尾不中断; 每批最多 REST_MAX_PER_BATCH 次 (2026-09-12 用户指令加)
REST_FILE = os.path.join(HERE, ".auto_rest.json")
AUTO_STATE = os.path.join(HERE, ".auto_state.json")
CRAWL_LOG = os.path.join(HERE, "logs", "nf_crawler.log")
REST_THRESHOLD = 10000    # 单轮请求数(列表页+全文+附件)超过即安排休息
REST_SECONDS = 0         # 09-12 用户指令: 4h 改 0h, 连续爬不休息(出问题用户担责); 队列/批次逻辑不变
REST_MAX_PER_BATCH = 3    # 每批最多休息次数 (REST_SECONDS=0 时不生效)
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
                       "rests": 0,
                       "total_windows": st["done_windows"]}
        st["fails"] = 0
        save_state(st)
        log("新批次 %s~%s: %d 窗入队, 等看门狗爬" % (start, end, len(labels)))
        feishu("🚀 回补批次开始: %s ~ %s (%d 窗)\n看门狗单账号串行爬, 爬完自动归档+发布+push, 我盯进度。" %
               (start, end, len(labels)))
        return 0

    # 检查活动批次 (爬虫在跑 = 有进展, 长列表扫描可能 2~3h 不出新窗, 不能按窗计数判 stall)
    crawler_running = False
    try:
        pid = int(open(os.path.join(HERE, ".auto_pid")).read().strip())
        os.kill(pid, 0)   # 信号0 = 存活探测
        crawler_running = True
    except Exception:
        crawler_running = False
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
    # 大活账号保护: 单轮请求量超阈值 -> 安排休息 (当前运行不中断, 跑完收尾后看门狗
    # idle 门认账停爬; 休息期通过把 last_prog 推到未来点来豁免 stall 误判)
    # 2026-09-12 用户指令: REST_SECONDS=0, 连续爬不休息, 此块直接跳过 (请求计数日志保留作观测)
    try:
        if crawler_running and REST_SECONDS > 0:
            st_auto = json.load(open(AUTO_STATE))
            off = int(st_auto.get("log_offset", 0) or 0)
            n_req = 0
            if off <= os.path.getsize(CRAWL_LOG):
                with open(CRAWL_LOG) as f:
                    f.seek(off)
                    for ln in f:
                        if "INFO: Fetched" in ln:
                            n_req += 1
            rests = batch.get("rests", 0)
            if n_req >= REST_THRESHOLD and rests < REST_MAX_PER_BATCH:
                with open(REST_FILE, "w") as f:
                    json.dump({"until": now + REST_SECONDS,
                               "reason": "round_requests=%d" % n_req}, f)
                batch["rests"] = rests + 1
                batch["last_prog"] = now + REST_SECONDS
                batch["t0"] += REST_SECONDS   # 休息时长顺延批次超时, 防休息期误判
                save_state(st)
                log("本轮请求 %d 次>=阈值 %d, 安排休息 %dh (本批第 %d/%d 次)" %
                    (n_req, REST_THRESHOLD, REST_SECONDS // 3600,
                     rests + 1, REST_MAX_PER_BATCH))
                feishu("💤 大活休息: 本轮已发 %d 次 API 请求(保护阈值 %d), 休息 %dh 防账号风控。当前这轮跑完自然收尾不中断, 休息后自动继续。" %
                       (n_req, REST_THRESHOLD, REST_SECONDS // 3600))
    except Exception as e:
        log("休息检查异常: %s: %s" % (type(e).__name__, e))
    stalled = (not crawler_running) and (now - batch["last_prog"] > STALL_LIMIT)
    timed_out = now - batch["t0"] > BATCH_TIMEOUT
    if stalled or timed_out:
        why = "8h 超时" if timed_out else "爬虫不在跑且 3h 无进展(疑似风控/槽满)"
        st["fails"] = st.get("fails", 0) + 1
        feishu("⚠️ 回补批次 %s~%s 卡住 (%d/%d, %s)。\n未爬完的窗保持 pending, 连续 2 次卡住会跳过本批继续后面日期(最后统一补洞)。" %
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
