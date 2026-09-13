#!/opt/data/venvs/shuimu/bin/python
"""stock_runner.py — 健壮版 Stock 分窗补爬 (09-09 11:30 用户指令版)
复用: BBS 客户端(shuimu_telnet) + 归档管线(shuimu_run) + 队列/归档/飞书(backfill_window)
修复生产脚本卡死 bug: 列表行解析失败时也 move_up (不原地读 31 次)。
断点续跳: 每轮把"快跳达到的最小 aid"存进队列; 0 帖且未完 → 保持 pending, 下轮从断点续跳。
安全: 主档整点(00/08/12/16)前 10 分钟自动收手; SessionBusy 直接让位。
用法: stock_runner.py [--window LABEL] [--budget-min N]
"""
import datetime as dt
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shuimu_telnet import BBS, parse_sel_row, SessionBusy
import shuimu_run as R
import backfill_window as BW  # 复用 archive / notify_feishu / 队列IO (main 不自动跑)

TZ = BW.TZ
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "logs", "stock_runner.log")
STOP_HOURS = (0, 8, 12, 16)  # 主档整点, 前 10 分钟让路

# 09-07 全天缺口 (当日 08/12/16/24 四档全挂, 目录无 meta)。倒序插队首优先补。
# 09-08 不在此列: 当晚 16:00/24:00 主档从当天 00:00 重读全天 (12 点档解析挂死
# bug 已修, 预期成功); 若 24 档仍失败再手动补窗。
GAP_DAYS = ["2026-09-07"]


def ensure_gap_windows(q):
    """幂等: 把缺口窗插到队首(当天新窗在前), 然后全体重编号 seq。"""
    have = set((t["day"], t["slot"]) for t in q["tasks"])
    new_tasks = []
    for day in GAP_DAYS:
        for h in (20, 16, 12, 8, 4, 0):
            if (day, "w%02d" % h) in have:
                continue
            ws = dt.datetime.fromisoformat("%sT%02d:00:00" % (day, h))
            we = ws + dt.timedelta(hours=4)
            new_tasks.append({
                "seq": 0, "day": day,
                "win_start": ws.isoformat(), "win_end": we.isoformat(),
                "slot": "w%02d" % h,
                "label": "%s %02d:00-%02d:00" % (day, h, min(h + 4, 24)),
                "status": "pending", "posts": None, "commit": None,
                "ts": None, "attempt": 0,
            })
    if new_tasks:
        q["tasks"] = new_tasks + q["tasks"]
        for i, t in enumerate(q["tasks"], 1):
            t["seq"] = i
        log("GAP_WINDOWS 队首插入 %d 个缺口窗 (09-07), 队列共 %d" % (len(new_tasks), len(q["tasks"])))
    return q


def now():
    return dt.datetime.now(TZ)


def log(m):
    line = "[%s] %s" % (now().strftime("%m-%d %H:%M:%S"), m)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def near_stop():
    n = now()
    # minute < 10: 主档整点 0-9 分让路; :10 整是补爬开跑点, 不算临近
    return n.hour in STOP_HOURS and n.minute < 10


def is_in_board(b):
    return any(("离开[" in ln and "阅读[" in ln) for ln in b.screen().split("\n")[:6])


def is_menu(b):
    return any("主选单" in ln for ln in b.screen().split("\n")[:3])


def get_sel(b, year):
    for ln in b.screen().split("\n"):
        if not ln.strip():
            continue
        if ln.strip().startswith("[提示]"):
            continue
        r = parse_sel_row(ln, year=year)
        if r:
            return r
    return None


def jump_back_to(b, year, target_aid, max_steps=4200, deadline=None):
    """从版面顶部快跳, 跳到 aid < target_aid 的第一行。返回 (步数, 达到的最小aid)。"""
    steps = 0
    min_aid = None
    while steps < max_steps:
        if deadline and time.time() > deadline:
            break
        if near_stop():
            log("  [jump] 临近主档, 提前止跳 (已跳%d步 达到aid=%s)" % (steps, min_aid))
            break
        steps += 1
        if not is_in_board(b):
            break
        row = get_sel(b, year)
        if row:
            try:
                ai = int(row[0])
                if min_aid is None or ai < min_aid:
                    min_aid = ai
            except (TypeError, ValueError):
                pass
            if min_aid is not None and ai < int(target_aid):
                break
            b.move_up(); b._recv(0.4); time.sleep(random.uniform(1.2, 2.6))
            continue
        b.move_up(); b._recv(0.4); time.sleep(random.uniform(1.2, 2.6))
    return steps, min_aid


AID_TIME_CACHE = os.path.join(HERE, "logs", "aid_time_cache.json")


def cache_load():
    try:
        return json.load(open(AID_TIME_CACHE, encoding="utf-8"))
    except Exception:
        return {}


def cache_save(c):
    try:
        with open(AID_TIME_CACHE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)
    except Exception:
        pass


def full_post_time(b, aid, cache):
    """09-10 根修: 读帖全文取发信时间, 跨窗缓存共享。
    返回 (t, from_cache, art)。t 可能为 None(拿不到)。
    命中缓存直接返回(不读全文)——多窗续扫时同一帖只读一次全文,
    避免 4 个 09-09 窗重复读同一批 ldate=次日 的帖烧 2-3 小时。"""
    if aid in cache:
        v = cache[aid]
        return (R.parse_ts_str(v) if v else None), True, None
    art = b.read_current_paged(max_pages=10)
    t = R.parse_ts_str(art.get("time_str")) if art.get("time_str") else None
    if t is not None:
        cache[aid] = art.get("time_str")
        cache_save(cache)
    return t, False, art


def crawl(b, board, win_start, win_end, year, deadline, resume_aid=None, aid_cache=None):
    """返回 (posts, complete, aborted, min_aid_seen, min_date_seen)。健壮: 解析失败也 move_up。"""
    if aid_cache is None:
        aid_cache = {}
    posts, seen = [], set()
    complete = False
    aborted = False
    no_row_streak = 0
    old_streak = 0
    min_aid_seen = None
    min_date_seen = None
    guard = 0
    max_guard = 8000
    while guard < max_guard:
        if time.time() > deadline:
            log("  [TIMEOUT] 预算耗尽 (已扫%d步 已收%d帖 达到aid=%s)" % (guard, len(posts), min_aid_seen))
            break
        if near_stop():
            log("  [YIELD] 临近主档整点, 主动收手 (已收%d帖 达到aid=%s)" % (len(posts), min_aid_seen))
            break
        guard += 1
        if not is_in_board(b):
            if is_menu(b):
                log("  [KICK] 掉回主选单 (第%d步), 重进版面" % guard)
                try:
                    b.open_board(board)
                except Exception as e:
                    log("  [ABORT] 重进版面失败 %r" % e)
                    aborted = True
                    break
            else:
                b._recv(2.0)
                if not is_in_board(b):
                    log("  [ABORT] 界面丢失, 收手")
                    aborted = True
                    break
            continue
        row = get_sel(b, year)
        if row is None:
            no_row_streak += 1
            log("  [UNPARSE x%d] 行不可解析, move_up 继续" % no_row_streak)
            b.move_up()
            b._recv(0.6)
            time.sleep(random.uniform(1.5, 3.0))
            if no_row_streak > 60:
                log("  [ABORT] 连续 60 次不可解析, 收手")
                aborted = True
                break
            continue
        no_row_streak = 0
        aid, author, ldate, title = row
        try:
            ai = int(aid)
            if min_aid_seen is None or ai < min_aid_seen:
                min_aid_seen = ai
            if ldate is not None and (min_date_seen is None or ldate < min_date_seen):
                min_date_seen = ldate
        except (TypeError, ValueError):
            pass
        if aid in seen:
            # 09-09 修复: move_up 后 _recv(0.4) 过短, 屏幕未刷新时读到同一旧行,
            # 曾单次重复即判"列表尽头"(09-08 w08/w12 假空窗, 51秒判空事故)。
            # 加长等待复核: 仍重复=真卡住(列表顶部); 变了=屏幕滞后, 继续。
            b._recv(3.0)
            time.sleep(2.5)
            row2 = get_sel(b, year)
            if row2 is not None and row2[0] == aid:
                log("  [END] 重复 aid=%s 确认卡住, 已达 date=%s aid_min=%s" % (aid, min_date_seen, min_aid_seen))
                complete = True
                break
            log("  [REPEAT-RETRY] 疑似屏幕滞后(旧行 aid=%s), 重读继续" % aid)
            continue
        seen.add(aid)
        if ldate > win_start.date():
            # 09-10 根修③: 列表日期=窗口日+1 的行(次日被回复)不能跳过——
            # 发帖时间可能仍在窗口内。09-08 12-16 窗 21.5min 判假空的根因:
            # 窗内帖 09-09 被回复 → 列表日期 09-09 → 被跳过 → 整窗漏判空。
            # 读全文, 窗内照收; 日期 >= 窗口日+2 仍跳过(逐行读全文太慢, 残留缺口已记录)。
            if ldate <= win_start.date() + dt.timedelta(days=1):
                t, from_cache, art = full_post_time(b, aid, aid_cache)
                if from_cache:
                    # 缓存命中没读全文, 节奏降档(3-8s)保持拟人; 正文拿不到→不收
                    time.sleep(random.uniform(3, 8))
                    b.move_up(); b._recv(0.4)
                    continue
                time.sleep(random.uniform(15, 35) if random.random() >= 0.05 else random.uniform(20, 60))
                b.back_robust()
                if not is_in_board(b):
                    continue
                if t is not None and win_start <= t < win_end:
                    posts.append({"id": aid, "author": art.get("author") or author,
                                  "nick": art.get("nick"), "title": art.get("title") or title,
                                  "time_str": art.get("time_str"), "time_utc": t.isoformat(),
                                  "body": art.get("body", ""), "post_date": ldate.isoformat(),
                                  "time_missing": False})
                    log("  ...收 %d 帖 (次日回复, 全文 %s, 列表日期 %s)" % (len(posts), t.strftime("%m-%d %H:%M"), ldate))
            b.move_up(); b._recv(0.4); time.sleep(random.uniform(1.2, 2.6))
            continue
        if ldate < win_start.date():
            # 边界候选: 列表行日期不可信(ANSI 脏行污染, 见 skill 坑#4),
            # 必须读全文发信时间(权威)确认; 2026-09-09 实测 3 窗因此误判空。
            t, from_cache, art = full_post_time(b, aid, aid_cache)
            if from_cache:
                time.sleep(random.uniform(3, 8))
                b.move_up(); b._recv(0.4)
                # 缓存命中的旧帖: 按已知时间判定边界(不读正文, 正文早于窗口不用收)
                if t is not None and t < win_start:
                    old_streak += 1
                    log("  [BOUNDARY x%d] 全文(缓存) %s < 窗口起 %s" % (old_streak, t.strftime("%m-%d %H:%M"), win_start.strftime("%m-%d %H:%M")))
                    if old_streak >= 2:
                        complete = True
                        break
                continue
            time.sleep(random.uniform(15, 35) if random.random() >= 0.05 else random.uniform(20, 60))
            b.back_robust()
            if not is_in_board(b):
                continue
            if t is None:
                body = art.get("body", "")
                if "刊 登 者" in body or "文章标题" in body:
                    # 09-10 根修⑥: 屏幕错位读到列表屏当正文, 弃收防垃圾归档
                    log("  [JUNK] 全文实为列表屏(屏幕错位), 弃收 aid=%s" % aid)
                    b.move_up(); b._recv(0.4); time.sleep(random.uniform(1.2, 2.6))
                    continue
                # 全文时间拿不到: 保守归档(标 time_missing), 不宣布边界
                posts.append({"id": aid, "author": author, "nick": art.get("nick"),
                              "title": art.get("title") or title, "time_str": art.get("time_str"),
                              "time_utc": win_start.isoformat(), "body": body,
                              "post_date": ldate.isoformat(), "time_missing": True})
                log("  ...收(全文时间缺失, 列表日期 %s)" % ldate)
                continue
            if t >= win_start:
                # 列表日期脏行误判: 实际在窗口内(或更晚), 按正常逻辑处理
                if t < win_end:
                    posts.append({"id": aid, "author": art.get("author") or author,
                                  "nick": art.get("nick"), "title": art.get("title") or title,
                                  "time_str": art.get("time_str"), "time_utc": t.isoformat(),
                                  "body": art.get("body", ""), "post_date": ldate.isoformat(),
                                  "time_missing": False})
                    log("  ...收 %d 帖 (全文修正, 列表日期 %s)" % (len(posts), ldate))
                else:
                    log("  [SKIP-NEW] %s 晚于窗口 (列表日期 %s)" % (t.strftime("%m-%d %H:%M"), ldate))
                continue
            # 真旧: 连续 2 帖全文早于窗口起点 = 边界
            old_streak += 1
            log("  [BOUNDARY x%d] 全文 %s < 窗口起 %s" % (old_streak, t.strftime("%m-%d %H:%M"), win_start.strftime("%m-%d %H:%M")))
            if old_streak >= 2:
                complete = True
                break
            continue
        old_streak = 0
        # 同一天: 读全文拿精确时间
        # 09-10 缓存优化: 已知时间在窗外→ 不读全文直接处理; 在窗口内→ 必须读全文拿正文
        t, from_cache, art = full_post_time(b, aid, aid_cache)
        if not from_cache:
            # 刚读了全文, 拟人停顿后返回列表
            time.sleep(random.uniform(15, 35) if random.random() >= 0.05 else random.uniform(20, 60))
            b.back_robust()
            if not is_in_board(b):
                continue
        else:
            if t is not None and t >= win_end:
                # 窗口更晚: 不读正文, 快速跳过
                time.sleep(random.uniform(3, 8))
                b.move_up(); b._recv(0.4)
                continue
            elif t is not None and t < win_start:
                # 同日期但早于窗口起点 = 边界(原语义), 连续 2 帖确认
                old_streak += 1
                log("  [BOUNDARY x%d] 全文(缓存) %s < 窗口起 %s" % (old_streak, t.strftime("%m-%d %H:%M"), win_start.strftime("%m-%d %H:%M")))
                if old_streak >= 2:
                    complete = True
                    break
                time.sleep(random.uniform(3, 8))
                b.move_up(); b._recv(0.4)
                continue
            elif t is None:
                # 时间未知(上次也没解析出来), 重读一次全文
                art = b.read_current_paged(max_pages=10)
                t = R.parse_ts_str(art.get("time_str")) if art.get("time_str") else None
                time.sleep(random.uniform(15, 35) if random.random() >= 0.05 else random.uniform(20, 60))
                b.back_robust()
                if not is_in_board(b):
                    continue
            else:
                # 窗口内但缓存没存正文: 重读全文拿 body
                art = b.read_current_paged(max_pages=10)
                time.sleep(random.uniform(15, 35) if random.random() >= 0.05 else random.uniform(20, 60))
                b.back_robust()
                if not is_in_board(b):
                    continue
        if not is_in_board(b):
            continue
        if t is None:
            body = art.get("body", "")
            if "刊 登 者" in body or "文章标题" in body:
                # 09-10 根修⑥: 屏幕错位读到列表屏当正文(17:16 w08 垃圾归档实证), 弃收
                log("  [JUNK] 全文实为列表屏(屏幕错位), 弃收 aid=%s" % aid)
                b.move_up(); b._recv(0.4); time.sleep(random.uniform(1.2, 2.6))
                continue
            posts.append({"id": aid, "author": author, "nick": art.get("nick"),
                          "title": art.get("title") or title, "time_str": art.get("time_str"),
                          "time_utc": win_start.isoformat(), "body": body,
                          "post_date": ldate.isoformat(), "time_missing": True})
        elif t < win_start:
            complete = True
            break
        elif t < win_end:
            posts.append({"id": aid, "author": art.get("author") or author,
                          "nick": art.get("nick"), "title": art.get("title") or title,
                          "time_str": art.get("time_str"), "time_utc": t.isoformat(),
                          "body": art.get("body", ""), "post_date": ldate.isoformat(),
                          "time_missing": False})
            log("  ...收 %d 帖 (%s %s)" % (len(posts), ldate, t.strftime("%H:%M")))
        else:
            log("  [SKIP-NEW] %s 晚于窗口" % t.strftime("%m-%d %H:%M"))
        if len(posts) >= 400:
            break
        b.move_up(); b._recv(0.4)
        time.sleep(random.uniform(2.0, 5.0))
    return posts, complete, aborted, min_aid_seen, min_date_seen


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default=None)
    ap.add_argument("--budget-min", type=int, default=30)
    args = ap.parse_args()

    q = BW.load_queue()
    ensure_gap_windows(q)  # 幂等: 09-07 缺口窗插队首 (只增不改, 无竞态)
    cfg = R.load_config()
    if args.window:
        task = next((t for t in q["tasks"] if t["label"] == args.window), None)
        if task is None:
            log("窗口 %s 不在队列" % args.window); return 1
    else:
        task = next((t for t in q["tasks"] if t["status"] == "pending"), None)
        if task is None:
            log("QUEUE_EMPTY"); return 0
    if task["status"] != "pending":
        log("窗口 %s 状态=%s, 不重复跑" % (task["label"], task["status"])); return 0

    board = "Stock"
    win_start = dt.datetime.fromisoformat(task["win_start"])
    win_end = dt.datetime.fromisoformat(task["win_end"])
    # 09-10 根修: 队列中部分窗 win_start 是 naive 串(09-09 深夜插队漏带时区),
    # naive 与 aware 比较直接 TypeError 崩进程(08:36-11:14 每轮崩 7 次, 一帖未存)。
    # 统一按北京时间补时区, 根治。
    if win_start.tzinfo is None:
        win_start = win_start.replace(tzinfo=TZ)
    if win_end.tzinfo is None:
        win_end = win_end.replace(tzinfo=TZ)
    year = win_start.year
    deadline = time.time() + args.budget_min * 60
    stop_hours = set(STOP_HOURS) - {now().hour}  # 当前小时的主档若正在跑, 靠 SessionBusy 让位, 不截断
    for h in stop_hours:
        c = now().replace(hour=h, minute=0, second=0, microsecond=0)
        if c <= now():
            c += dt.timedelta(days=1)
        stop_at = c - dt.timedelta(minutes=10)
        if stop_at < dt.datetime.fromtimestamp(deadline, TZ):
            deadline = stop_at.timestamp()
    log("TASK %s 窗=%s 预算至 %s resume_aid=%s" % (
        task["seq"], task["label"],
        dt.datetime.fromtimestamp(deadline, TZ).strftime("%H:%M"), task.get("resume_aid")))
    # 09-10: 整点让路窗口内预算可能已过期(如 11:52 跑 11:50 截止的预算),
    # 之前照样 telnet 登录再秒退, 11:50-12:00 间白登录 8 次。过期直接跳过不连 BBS。
    if time.time() > deadline:
        log("  [SKIP] 预算已过期(%s 截止), 不连 BBS, 下轮再跑"
            % dt.datetime.fromtimestamp(deadline, TZ).strftime("%H:%M"))
        return 0

    b = BBS(credentials=cfg["credentials"])
    posts_all = []
    complete = False
    min_aid = None
    min_date2 = None
    try:
        b.login_with_retry()
        time.sleep(random.uniform(3, 8))
        b.open_board(board)
        resume_aid = task.get("resume_aid")
        if resume_aid:
            log("断点续跳: 目标 aid=%s" % resume_aid)
            js, min_aid = jump_back_to(b, year, resume_aid, deadline=deadline)
            log("续跳跳了 %d 步, 达到 aid=%s" % (js, min_aid))
        aid_cache = cache_load()  # 09-10 根修: 跨轮/跨窗共享 aid→发信时间缓存
        posts, complete, aborted, min_aid2, min_date2 = crawl(b, board, win_start, win_end, year, deadline, aid_cache=aid_cache)
        posts_all = posts
        if min_aid2 is not None and (min_aid is None or min_aid2 < min_aid):
            min_aid = min_aid2
        # 断点: 未完 → 记"快跳达到的最小 aid"供下轮续跳
        # 09-09 不变量: 0帖+complete 必须真到达窗口日期。若最小列表日期仍晚于
        # 窗口日(只翻到次日的帖就"到底"), 判假空窗, 回退 pending 下轮重爬。
        if complete and min_date2 is not None and min_date2 > win_start.date():
            # 09-10 根修④: 不变量对任意帖数生效(原仅 0 帖)。声明 complete 但列表从未
            # 翻到窗口日 => 假空窗 或 屏幕滞后误判列表顶部(09-10 18:14 实证), 回退 pending。
            log("  [INVARIANT] complete 但列表只到 %s (窗口日 %s, 已收%d帖), 回退 pending"
                % (min_date2, win_start.date(), len(posts_all)))
            complete = False
        if not complete:
            # 09-10 根修⑤: 已收帖但未完(TIMEOUT/ABORT) => 保持 pending, 断点取
            # min(最深到达 min_aid, 最旧已收帖-1) = 最深点, 下轮从断点续扫(幂等)。
            # done_partial 是终态陷阱(08-12 窗被永久放弃), 从此不再产生。
            cands = []
            if min_aid:
                cands.append(int(min_aid))
            if posts_all:
                cands.append(min(int(p["id"]) for p in posts_all) - 1)
            if cands:
                task["resume_aid"] = str(min(cands))
        elif "resume_aid" in task:
            task.pop("resume_aid", None)
    except SessionBusy:
        log("SESSION_BUSY 让位 (主档占用), 下轮再试"); return 2
    finally:
        try:
            b.close()
        except Exception:
            pass

    total, nthreads, rev = 0, 0, None
    if posts_all:
        total, nthreads = BW.archive(cfg, task, posts_all, complete, now())
        log("归档 %d 帖 / %d 主题 -> %s (complete=%s)" % (total, nthreads, task["label"], complete))
        # 09-10 根修⑤: 未完保持 pending 下轮续爬(归档幂等整窗重写, 重跑不重复)。
        task["status"] = "done" if complete else "pending"
        task["posts"] = total
        task["commit"] = rev
    elif not complete:
        task["status"] = "pending"  # 0 帖且未完 = 还没跳到目标窗, 保持 pending 下轮续跳
        log("快跳未到目标窗 (达到 aid=%s), 保持 pending 下轮续" % task.get("resume_aid"))
    else:
        task["status"] = "done"  # 0 帖且 complete = 窗口确认为空, 标 done 防不停车循环死循环
        task["posts"] = 0
        log("窗口确认为空 (complete=True 0 帖) 已达 date=%s aid=%s, 标记 done" % (min_date2, min_aid))
    task["ts"] = now().isoformat()
    q["consec_fails"] = 0
    remaining = sum(1 for t in q["tasks"] if t["status"] == "pending")
    BW.save_queue(q)
    if total and complete:
        BW.notify_feishu("✅ 水木补爬 %s: %s 帖 / %s 主题 (complete=%s)\n剩余 %d/40 窗"
                         % (board, total, nthreads, complete, remaining))
    log("TASK_DONE posts=%d threads=%d complete=%s status=%s remaining=%d"
        % (total, nthreads, complete, task["status"], remaining))
    return 0


if __name__ == "__main__":
    sys.exit(main())
