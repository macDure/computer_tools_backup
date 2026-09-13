#!/usr/bin/env python3
"""backfill_window.py — 分窗补爬 (2026-09-08 新策略, 替代 backfill_range 整段爬)

背景: 09-08 整段补爬 (backfill_range) 两轮均在 ~230 步 (09-07 数据区) 被踢,
账号处于服务器侧惩罚窗口, 长会话必死。用户指令改为"一口吃大象拆碎":

  1. 任务粒度 = 1 个 4 小时窗 (00-04/04-08/08-12/12-16/16-20/20-24)
  2. 08-31 ~ 09-06 共 7 天 x 6 窗 = 42 任务, 按时间倒序排队
     (09-06 20-24 最先, 08-31 00-04 最后)
  3. 每次运行 (cron 每小时 :30, 错开 08/12/16/00 四档) 只登录一次,
     只爬队首一个窗, 绝不贪多
  4. 拟人慢速: 每帖读完停留 ~30s (18~45s 抖动, 6% 概率走神 1~2 分钟),
     帖间额外间隔 2~5s, 跳过阶段翻页随机 1.5~3.5s — 全部随机, 无固定节律
  5. 被踢最多恢复 2 次; 连续 2 次恢复均 <30 步进展 = 惩罚窗口, 放弃本任务
     (拿到手的帖仍归档, 标记 complete=false)
  6. 连续 3 个任务失败 -> 队列整体冷却 6 小时 (不再试探)

用法:
  backfill_window.py                 # 领队首任务执行
  backfill_window.py --mark-failed "timeout"   # 外部失败(超时被杀)记账
  backfill_window.py --init          # (重)生成 42 任务队列
  backfill_window.py --status        # 打印队列进度, 不登录

输出 (最后一行, 供 agent 解析):
  TASK_DONE day=... window=20:00-24:00 posts=N threads=M complete=true commit=... remaining=k/42
  TASK_ABORT reason=... posts_archived=N
  QUEUE_EMPTY
  COOLDOWN_NEW until=... / COOLDOWN_ACTIVE until=...
  SKIPPED_SESSION_BUSY
"""
import argparse
import datetime as dt
import json
import os
import random
import re
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shuimu_telnet import BBS, parse_sel_row, SessionBusy
import shuimu_run as R

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE_PATH = os.path.join(HERE, "backfill_queue.json")
LOG_DIR = os.path.join(HERE, "logs")
LOG_PATH = os.path.join(LOG_DIR, "backfill_window.log")
TZ = dt.timezone(dt.timedelta(hours=8))
DAYS = ["2026-09-06", "2026-09-05", "2026-09-04",
        "2026-09-03", "2026-09-02", "2026-09-01", "2026-08-31"]  # 倒序
WINDOW_STARTS = [20, 16, 12, 8, 4, 0]  # 天内从最新窗开始


def log(msg, flush=True):
    # no_agent 模式: stdout 会被 cron verbatim 交付飞书(每小时一条=轰炸),
    # 故诊断只落日志文件 + stderr, stdout 保持静默(no_agent 空 stdout=静默)。
    # flush 为兼容参数(历史调用点带 flush=True), 文件每行即写即刷。
    line = "[%s] %s" % (bj_now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, file=sys.stderr, flush=True)


def notify_feishu(text):
    """关键事件直发飞书(不走 cron auto-delivery, 规避 #47056 静默失败缺陷)。
    返回 True=已直发; False=直发失败(调用方可 stdout 兜底, 走 cron 交付双保险)."""
    try:
        return bool(R.feishu_send(text))
    except Exception as e:
        log("notify_feishu 异常: %s" % e)
        return False


def remaining_windows(q):
    return sum(1 for t in q["tasks"] if t["status"] == "pending")


def bj_now():
    return R.bj_now()


def build_queue():
    tasks = []
    idx = 0
    for day in DAYS:
        d = dt.date.fromisoformat(day)
        for h in WINDOW_STARTS:
            idx += 1
            ws = dt.datetime(d.year, d.month, d.day, h, 0, 0, tzinfo=TZ)
            we = ws + dt.timedelta(hours=4)
            tasks.append({
                "seq": idx, "day": day,
                "win_start": ws.isoformat(), "win_end": we.isoformat(),
                "slot": "w%02d" % h,
                "label": "%s %02d:00-%02d:00" % (day, h, h + 4),
                "status": "pending", "posts": None, "commit": None,
                "ts": None, "attempt": 0,
            })
    return {"created": bj_now().isoformat(),
            "consec_fails": 0, "cooldown_until": None, "tasks": tasks}


def load_queue():
    if not os.path.exists(QUEUE_PATH):
        q = build_queue()
        save_queue(q)
        log("QUEUE_INIT created %d tasks" % len(q["tasks"]))
    with open(QUEUE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_queue(q):
    tmp = QUEUE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    os.replace(tmp, QUEUE_PATH)


def queue_stats(q):
    s = {}
    for t in q["tasks"]:
        s[t["status"]] = s.get(t["status"], 0) + 1
    return s


# ---------- 屏幕判定 (与 backfill_range 同款, 已验证) ----------

def is_menu(b):
    for ln in b.screen().split("\n")[:3]:
        if "主选单" in ln:
            return True
    return False


def is_in_board(b):
    for ln in b.screen().split("\n")[:6]:
        if "离开[" in ln and "阅读[" in ln:
            return True
    return False


def get_sel(b, year):
    scr = b.screen()
    for ln in scr.split("\n"):
        if re.match(r"\s*>?\s*\[提示\]", ln):
            continue
        r = parse_sel_row(ln, year=year)
        if r:
            return r
    return None


# ---------- 拟人节奏 ----------

def human_dwell():
    """读完全帖后'停留'— 模拟人看完一篇 (用户指令: 正常浏览一帖约 30s).
    18~45s 抖动, 6% 概率'走神' 45~120s (喝口水/看别处)."""
    if random.random() < 0.06:
        time.sleep(random.uniform(45, 120))
    else:
        time.sleep(random.uniform(18, 45))


def skip_pause():
    """跳过阶段翻页后停顿, 随机 1.5~3.5s (无固定节律)."""
    time.sleep(random.uniform(1.5, 3.5))


def read_pause_extra():
    """读完一帖回到列表后, 帖与帖之间再停 2~5s."""
    time.sleep(random.uniform(2.0, 5.0))


# ---------- 单窗爬取 ----------

def crawl_window(b, board, win_start, win_end, year,
                 max_steps=400, max_posts=120, deadline=None):
    """返回 (posts, complete, aborted, timed_out).
    complete=False 且 aborted=True = 被踢放弃 (posts 里拿到的仍有效).
    timed_out=True = wall-clock 预算耗尽 (posts 里拿到的仍有效, 任务保持 pending 下小时重试)."""
    posts, seen = [], set()
    complete = False
    aborted = False
    guard = 0
    no_row = 0
    stagnant = 0
    last_aid = None
    last_read_aid = None
    recoveries = 0
    stuck_recovers = 0
    last_recover_guard = 0
    skip_i = 0

    while guard < max_steps:
        if deadline is not None and time.time() > deadline:
            log("[TIMEOUT] wall-clock 预算耗尽 (已扫%d步, 已收%d帖), 本任务下小时重试"
                % (guard, len(posts)), flush=True)
            return posts, complete, False, True
        guard += 1
        if not is_in_board(b):
            # 被踢出列表 (回主选单或滞留)
            recoveries += 1
            progressed = guard - last_recover_guard
            last_recover_guard = guard
            # 有实质进展(>=30步) = 限流波, 计数重置; 无进展 = 硬惩罚特征
            stuck_recovers = 0 if progressed >= 30 else stuck_recovers + 1
            log("[RECOVER %d] 被踢出列表 (已扫%d步, 已读%d帖, 上次以来进展%d步)"
                % (recoveries, guard, len(posts), progressed), flush=True)
            if recoveries > 2 or stuck_recovers >= 2:
                log("[ABORT] 恢复超限/连续零进展恢复(惩罚窗口), 放弃本任务, 不硬扛", flush=True)
                aborted = True
                break
            log("  冷却 120s 后重进版面 (单次任务最多 2 次恢复)...", flush=True)
            time.sleep(120)
            try:
                b.open_board(board)
            except Exception as e:
                log("[ABORT] 重进版面失败: %s" % e, flush=True)
                aborted = True
                break
            # 断点续传: 从顶部快跳回最后已读位置
            if last_read_aid:
                jump = 0
                while jump < max_steps:
                    jump += 1
                    if not is_in_board(b):
                        break
                    r2 = get_sel(b, year)
                    if not r2:
                        b._recv(1.0)
                        continue
                    if int(r2[0]) >= int(last_read_aid):
                        b.move_up(); b._recv(0.3)
                        continue
                    break
            no_row = 0
            stagnant = 0
            last_aid = None
            continue

        row = get_sel(b, year)
        if row is None:
            no_row += 1
            b._recv(1.2)
            if no_row > 30:
                log("[ABORT] 列表行持续不可解析 %d 次(疑似卡死), 放弃本任务" % no_row, flush=True)
                aborted = True
                break
            continue
        no_row = 0
        aid, author, ldate, title = row
        if last_aid == aid:
            stagnant += 1
            if stagnant > 30:
                log("[ABORT] 光标卡死 aid=%s %d 次, 放弃本任务" % (aid, stagnant), flush=True)
                aborted = True
                break
            b._recv(1.5)
            continue
        stagnant = 0
        last_aid = aid
        if aid in seen:
            # 光标回绕 = 到列表尾部边界
            complete = True
            break
        seen.add(aid)

        # 按列表行日期(只有天)先分流 — 6 个窗口都严格落在 win_start 当天内
        # (20-24 的 win_end 虽跨到次日 00:00, 但 00:00 整点无帖, 无需读次日行)
        if ldate > win_start.date():
            # 更新的日期: 快跳, 不读全文
            b.move_up()
            skip_pause()
            skip_i += 1
            if skip_i % 100 == 1:
                log("[SKIP] 已跳过 %d 步 (当前最新 %s)" % (skip_i, ldate.isoformat()), flush=True)
            continue
        if ldate < win_start.date():
            complete = True
            break

        # 同一天: 必须读全文拿精确发信时间 (拟人慢速)
        art = b.read_current_paged(max_pages=10)
        t = R.parse_ts_str(art.get("time_str")) if art.get("time_str") else None
        human_dwell()          # 读完停留 ~30s
        b.back_robust()
        if t is None:
            log("  [WARN] id=%s 无发信时间, 保留但标记 time_missing" % aid, flush=True)
            posts.append({
                "id": aid, "author": author, "nick": art.get("nick"),
                "title": art.get("title") or title,
                "time_str": art.get("time_str"),
                "time_utc": win_start.isoformat(),
                "body": art.get("body", ""), "post_date": ldate.isoformat(),
                "time_missing": True,
            })
        elif t < win_start:
            complete = True
            break
        elif t < win_end:
            posts.append({
                "id": aid, "author": art.get("author") or author,
                "nick": art.get("nick"), "title": art.get("title") or title,
                "time_str": art.get("time_str"), "time_utc": t.isoformat(),
                "body": art.get("body", ""), "post_date": ldate.isoformat(),
                "time_missing": False,
            })
            log("  ...已收 %d 帖 (最新 %s %s)" % (len(posts), ldate, t.strftime("%H:%M")), flush=True)
        else:
            log("  [SKIP-NEW] id=%s %s 晚于窗口, 不收录" % (aid, t.strftime("%m-%d %H:%M")), flush=True)
        last_read_aid = aid
        if len(posts) >= max_posts:
            break
        b.move_up()
        read_pause_extra()
    return posts, complete, aborted, False


# ---------- 归档 (复用 shuimu_run 已验证管线) ----------

def archive(cfg, task, posts, complete, now_bj):
    day = dt.date.fromisoformat(task["day"])
    ws = dt.datetime.fromisoformat(task["win_start"])
    d = os.path.join(cfg["root"], "%04d" % day.year, "%02d" % day.month,
                     "%02d" % day.day, task["slot"])
    os.makedirs(d, exist_ok=True)
    total = 0
    meta = {"slot": task["slot"], "mode": "backfill_window", "complete": complete,
            "generated_bj": now_bj.isoformat(), "target_day": task["day"],
            "window_bj": task["label"], "boards": {}}
    for board in cfg["boards"]:
        threads = R.classify(posts)
        if not threads:
            continue
        pth, n = R.write_board_md(d, cfg, task["slot"], now_bj, day, ws, board, threads)
        meta["boards"][board] = {
            "thread_count": len(threads), "post_count": n,
            "threads": [{"title": t["title"], "is_new_today": t["is_new_today"],
                         "first_time_bj": R.to_bj(dt.datetime.fromisoformat(t["first_time"])).isoformat(),
                         "post_count": len(t["posts"]),
                         "authors": sorted(set(p["author"] for p in t["posts"]))}
                        for t in sorted(threads, key=lambda x: x["first_time"])]}
        total += n
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    rev = R.git_commit(cfg, "shuimu backfill %s (%s)" % (task["label"], "partial" if not complete else "full"))
    meta["git_commit"] = rev
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    first_board = cfg["boards"][0]
    nthreads = len(meta["boards"].get(first_board, {}).get("threads", []))
    return total, nthreads


# ---------- 主流程 ----------

def mark_failed(reason):
    q = load_queue()
    q["consec_fails"] = q.get("consec_fails", 0) + 1
    if q["consec_fails"] >= 3 and not q.get("cooldown_until"):
        q["cooldown_until"] = (bj_now() + dt.timedelta(hours=6)).isoformat()
        save_queue(q)
        log("MARK_FAILED reason=%s consec=%d -> 进入 6 小时冷却 until=%s"
            % (reason, q["consec_fails"], q["cooldown_until"]))
        ok = notify_feishu("⚠️ 水木补爬分窗: 连续 3 个任务被踢/失败，判定仍在惩罚窗口，"
                           "队列冷却 6 小时 (%s 北京时间前不再登录)，保护账号。" % q["cooldown_until"][11:16])
        if not ok:
            print("⚠️ 水木补爬分窗进入 6 小时冷却至 %s (飞书直发失败, 本消息走 cron 兜底)" % q["cooldown_until"][:16], flush=True)
    else:
        save_queue(q)
        log("MARK_FAILED reason=%s consec=%d" % (reason, q["consec_fails"]))


def _sigterm_handler(signum, frame):
    # 被外部强杀(SIGTERM, 如 cron 超时): 快速记账后退出
    try:
        mark_failed("被SIGTERM强杀")
    except Exception:
        pass
    os._exit(124)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--mark-failed", default=None, metavar="REASON")
    args = ap.parse_args()

    if args.init:
        q = build_queue()
        save_queue(q)
        log("QUEUE_INIT %d tasks" % len(q["tasks"]))
        return

    q = load_queue()

    if args.status:
        s = {"pending": 0, "done": 0, "done_partial": 0}
        for t in q["tasks"]:
            s[t["status"]] = s.get(t["status"], 0) + 1
        log("QUEUE_STATUS %s consec_fails=%s cooldown_until=%s"
            % (json.dumps(s), q.get("consec_fails"), q.get("cooldown_until")))
        for t in q["tasks"][:8]:
            log("  #%d %s [%s] posts=%s" % (t["seq"], t["label"], t["status"], t["posts"]))
        log("  ...")
        return

    if args.mark_failed:
        mark_failed(args.mark_failed)
        return

    now = bj_now()
    signal.signal(signal.SIGTERM, _sigterm_handler)  # 外部强杀时记账

    # 让路规则: 主爬虫四档在北京 00/08/12/16 整点跑, 其后的 :30 时段若补爬登录,
    # 可能拖过整点占住单会话锁, 挡掉主档 (尤其 00:00 slot24 全天兜底).
    # 故"下一个整点是主档"时本小时安静让路 (不登录), 每天让 4 个时段, 爬 20 个.
    nxt_hour = (now.hour + 1) % 24
    if nxt_hour in (0, 8, 12, 16):
        log("DEFER: 下一整点 %02d:00 是主爬虫档, 本小时不登录让路 (单会话锁纪律)" % nxt_hour)
        return
    if q.get("cooldown_until") and now < dt.datetime.fromisoformat(q["cooldown_until"]):
        log("COOLDOWN_ACTIVE until=%s (静默)" % q["cooldown_until"][:16])
        return

    task = next((t for t in q["tasks"] if t["status"] == "pending"), None)
    if task is None:
        s = {}
        for t in q["tasks"]:
            s[t["status"]] = s.get(t["status"], 0) + 1
        log("QUEUE_EMPTY %s" % json.dumps(s, ensure_ascii=False))
        # 全部完成: 一次性直发总结 (只发这一次)
        if not q.get("notified_done"):
            q["notified_done"] = True
            save_queue(q)
            ok = notify_feishu("✅ 水木分窗补爬 08-31~09-06 全部 42 个 4 小时窗完成。\n"
                               "统计: %s\n详见 git /opt/data/shuimu_daily (shuimu backfill 提交)。"
                               % json.dumps(s, ensure_ascii=False))
            if not ok:
                print("✅ 水木分窗补爬 08-31~09-06 全部 42 窗完成 %s (飞书直发失败, 走 cron 兜底)"
                      % json.dumps(s, ensure_ascii=False), flush=True)
        return

    # 记录本任务开始前, 其所属"天"还剩几个 pending (用于判断该天是否补齐)
    day_pending_before = sum(1 for t in q["tasks"]
                             if t["status"] == "pending" and t["day"] == task["day"])

    task["attempt"] = task.get("attempt", 0) + 1
    task["ts"] = now.isoformat()
    save_queue(q)
    log("TASK_START #%d/%d %s attempt=%d" % (task["seq"], len(q["tasks"]),
                                              task["label"], task["attempt"]))

    cfg = R.load_config()
    year = int(task["day"][:4])
    win_start = dt.datetime.fromisoformat(task["win_start"])
    win_end = dt.datetime.fromisoformat(task["win_end"])
    deadline = time.time() + 45 * 60   # 单窗 wall-clock 预算 45 分钟

    b = BBS(credentials=cfg["credentials"])
    timed_out = False
    try:
        b.login_with_retry()
        time.sleep(random.uniform(3, 8))  # 进版面后先"站住看一眼"
        board = cfg["boards"][0]
        b.open_board(board)
        posts, complete, aborted, timed_out = crawl_window(
            b, board, win_start, win_end, year, deadline=deadline)
    except SessionBusy as e:
        log("SKIPPED_SESSION_BUSY: %s" % e)
        return
    finally:
        try:
            b.close()
        except Exception:
            pass

    total, nthreads = 0, 0
    rev = None
    if posts:
        total, nthreads = archive(cfg, task, posts, complete, bj_now())

    # 被踢/超时且零产出: 任务保持 pending, 下小时重试; 记账失败 (可能触发 6h 冷却)
    if (aborted or timed_out) and not posts:
        q["consec_fails"] = q.get("consec_fails", 0) + 1
        reason = "超时零产出" if timed_out else "被踢零产出"
        if q["consec_fails"] >= 3 and not q.get("cooldown_until"):
            q["cooldown_until"] = (bj_now() + dt.timedelta(hours=6)).isoformat()
            save_queue(q)
            log("TASK_ABORT reason=%s consec_fails=%d -> 6h冷却" % (reason, q["consec_fails"]))
            ok = notify_feishu("⚠️ 水木分窗补爬: 连续 3 个窗 %s，判定仍在惩罚窗口，冷却 6 小时 "
                               "至 %s (北京时间)。保护账号，不再试探。"
                               % (reason, q["cooldown_until"][11:16]))
            if not ok:
                print("⚠️ 水木分窗补爬进入 6 小时冷却至 %s (%s)" % (q["cooldown_until"][:16], reason), flush=True)
        else:
            save_queue(q)
            log("TASK_ABORT reason=%s consec_fails=%d 下小时重试" % (reason, q["consec_fails"]))
        return

    # 拿到帖子(无论 complete 与否): 记成功, 清零失败计数
    q["consec_fails"] = 0
    q["cooldown_until"] = None
    task["status"] = "done" if complete else "done_partial"
    task["posts"] = total
    task["commit"] = rev
    task["ts"] = bj_now().isoformat()

    # 判断该天是否补齐 (本任务做完后, 该天无 pending)
    day_pending_after = sum(1 for t in q["tasks"]
                            if t["status"] == "pending" and t["day"] == task["day"])
    day_full = day_pending_after == 0 and day_pending_before > 0

    save_queue(q)
    log("TASK_DONE day=%s window=%02d:00-%02d:00 posts=%d threads=%d complete=%s commit=%s "
        "remaining=%d/42%s" % (task["day"], int(task["win_start"][11:13]),
                               int(task["win_end"][11:13]), total, nthreads,
                               complete, rev or "-",
                               sum(1 for t in q["tasks"] if t["status"] == "pending"),
                               "  [该天补齐]" if day_full else ""))

    if day_full:
        # 该天 6 窗全部完成: 直发一次当天汇总
        ok = notify_feishu("✅ 水木分窗补爬 %s 全天 6 个 4 小时窗补齐 (含部分窗)。"
                           "本窗: %02d:00-%02d:00, %d 帖 / %d 主题。\n"
                           "队列剩余 %d/42 窗。"
                           % (task["day"], int(task["win_start"][11:13]),
                              int(task["win_end"][11:13]), total, nthreads,
                              sum(1 for t in q["tasks"] if t["status"] == "pending")))
        if not ok:
            print("✅ 水木分窗补爬 %s 全天补齐, 本窗 %d 帖 (飞书直发失败, 走 cron 兜底)"
                  % (task["day"], total), flush=True)


if __name__ == "__main__":
    main()
