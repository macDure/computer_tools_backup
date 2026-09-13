#!/usr/bin/env python3
"""backfill_range.py v3 — 范围补爬: 一次遍历读取 [start_day, end_day] 全部新帖+旧帖回复

用法: python backfill_range.py --start 2026-08-31 --end 2026-09-02
机制 (v3, 2026-09-03 修复 back_robust 误发 'e' 踢出版面导致的卡死):
  版面列表从最新一路 k 上扫, 列表行自带 Mon DD 日期(服务器=北京时间):
    日期 > end_day  -> move_up 快跳 (不读全文, ~1.7s/帖)
    日期 < start_day -> 停 (complete=True)
    range 内        -> r 读全文 (~3.2s/帖), 按日期分桶
  鲁棒性:
    - 宽容行解析 parse_sel_row (抗 ANSI 重绘残留)
    - 列表行丢失/卡死 -> 检测是否被踢回主选单; 是则重新 open_board
    - 重进版面后从顶部快速跳到 "最后已读 id" 续传 (seen 去重, 不重读)
  写入: 每天 root/YYYY/MM/DD/24/ 原帖+meta, 各一个 git commit
"""
import argparse, datetime as dt, json, os, random, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shuimu_telnet import BBS, parse_sel_row
import shuimu_run as R


def is_menu(b):
    """主选单判定 — 只看渲染屏前 3 行 (2026-09-03 修复: 80x160 网格
    下半部是上一屏残留, '主选单' 整屏搜索会把残留当命中)."""
    for ln in b.screen().split("\n")[:3]:
        if "主选单" in ln:
            return True
    return False


def is_in_board(b):
    # 2026-09-07 修复: 主选单顶栏第一行也带 "讨论区 [Test/Stock]"(当前区指示器),
    # 且页面翻转瞬态屏残留列表头片段(实测: "35/5049 [一般模式]" 出现在主选单前3行).
    # 权威标记 = 列表界面帮助行 "离开[←,e] 选择[↑,↓] 阅读[→,r]" (主选单永远没有).
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


def traverse_range(b, board, year, start_day, end_day, max_threads=800):
    """返回 (posts, complete). complete=False 表示没扫到 start 日之前."""
    posts, seen = [], set()
    complete = False
    no_row = 0
    stagnant = 0
    last_aid = None
    last_read_aid = None
    recoveries = 0
    last_recover_guard = 0
    stuck_recovers = 0   # 2026-09-07: 连续零进展恢复计数(硬惩罚窗口早停)
    i_skip = 0
    guard = 0
    while guard < max_threads * 3 + 400:
        guard += 1
        row = get_sel(b, year) if is_in_board(b) else None
        if row is None:
            no_row += 1
            if no_row <= 3:
                b._recv(1.0)          # 可能只是分页加载中
                continue
            # 卡住了: 诊断 + 恢复
            if is_menu(b):
                print("  [RECOVER %d] 被踢回主选单 (已扫%d步, 已读%d帖), 屏前3行=%r"
                      % (recoveries + 1, guard, len(posts), b.screen().split("\n")[:3]), flush=True)
                recoveries += 1
                if recoveries > 10:
                    print("  [STOP] 恢复次数超限, 标记 incomplete", flush=True)
                    break
                # 2026-09-07: 硬惩罚窗口早停 — 连续零进展恢复(每次<50步又被踢)
                # 计满 3 次即停. 硬窗口内 RECOVER 只会反复重连加深惩罚
                # (09-07 晚实测: 154步起每5步一踢, 烧 11 次×~90s 共16分钟, 0帖).
                if guard - last_recover_guard >= 50:
                    stuck_recovers = 1
                else:
                    stuck_recovers += 1
                if stuck_recovers >= 3:
                    print("  [STOP] 连续%d次零进展恢复(硬惩罚窗口), 提前停止等冷却"
                          % stuck_recovers, flush=True)
                    break
                time.sleep(90)
                b.open_board(board)
                no_row = 0
                # 有实际进度就重置恢复计数(限流波可多次, 不应累计到上限)
                if guard - last_recover_guard >= 50:
                    recoveries = 1
                last_recover_guard = guard
                # 断点续传: 从顶部快速跳回最后已读位置
                # 2026-09-07 修复: 内层跳跃独立计数, 不再消耗外层 guard 预算
                # (旧版共享 guard: 续传一跳就把外层预算吃光, 静默退出 complete=False)
                if last_read_aid:
                    jump = 0
                    while jump < max_threads * 3 + 400:
                        jump += 1
                        r2 = get_sel(b, year)
                        if not r2:
                            b._recv(1.0)
                            if not is_in_board(b):
                                break
                            continue
                        if int(r2[0]) >= int(last_read_aid):
                            b.move_up(); b._recv(0.25)
                            continue
                        break
                last_aid = None
                continue
            # 不在主选单也不在列表(滞留文章视图)
            b.send("q"); b._recv(1.2)
            if no_row > 40:
                print("  [RECOVER %d] 滞留 %d 次, 强制重进版面" % (recoveries + 1, no_row), flush=True)
                recoveries += 1
                if recoveries > 10:
                    print("  [STOP] 恢复次数超限, 标记 incomplete", flush=True)
                    break
                try:
                    b.send("q"); b.send("e"); b._recv(1.5)
                    if is_menu(b):
                        b.open_board(board)
                    no_row = 0
                    last_aid = None
                except Exception as e:
                    print("  [STOP] 恢复异常 %s" % e, flush=True)
                    break
            continue
        no_row = 0
        aid, author, date, title = row
        if last_aid is not None and aid == last_aid:
            stagnant += 1
            if stagnant > 8:
                # 光标不动(可能页面没翻过来) — 再等, 持续不动则重进版面
                if stagnant > 20:
                    print("  [RECOVER %d] 光标卡死 aid=%s, 重进版面" % (recoveries + 1, aid), flush=True)
                    recoveries += 1
                    if recoveries > 10:
                        print("  [STOP] 恢复次数超限, 标记 incomplete", flush=True)
                        break
                    b.open_board(board)
                    no_row = 0; stagnant = 0; last_aid = None
                    if last_read_aid:
                        # 2026-09-07: 无上限 while True 改独立计数上限(防死循环)
                        jump = 0
                        while jump < max_threads * 3 + 400:
                            jump += 1
                            r2 = get_sel(b, year)
                            if not r2:
                                b._recv(1.0)
                                if not is_in_board(b):
                                    break
                                continue
                            if int(r2[0]) >= int(last_read_aid):
                                b.move_up(); b._recv(0.25)
                                continue
                            break
                    continue
                b._recv(1.2)
                continue
            b._recv(1.0)
            continue
        stagnant = 0
        last_aid = aid
        if aid in seen:
            break
        seen.add(aid)
        if date > end_day:
            # move_up 内部已含拟人化停顿(0.5~1.3s + 2.5% 走神); 固定节奏已被打散
            b.move_up()
            b._recv(0.4)
            if i_skip % 20 == 19:
                # 每翻一页的"看完一屏"停顿随机化 1.5~3.5s
                time.sleep(random.uniform(1.5, 3.5))
            i_skip += 1
            # 2026-09-07: 跳过阶段心跳 — 此前跳过阶段零日志, 进程又 95% 时间
            # 在 sleep, 远看与挂死无异, 导致误判杀进程(实测两次误杀).
            if i_skip % 100 == 1:
                print("  [SKIP] 已跳过 %d 步 (当前最新 %s)" % (i_skip, date.isoformat()), flush=True)
            continue
        if date < start_day:
            complete = True
            break
        art = b.read_current_paged(max_pages=8)
        t = R.parse_ts_str(art.get("time_str")) if art.get("time_str") else None
        # 2026-09-03 数据质量加固 (证据纪律): 归档以文章屏精确发信时间为准.
        # 列表行宽容解析在重绘脏行上可能把日期看错(09-03 帖混入 09-02 实测案例).
        if t is not None and (t.month, t.day) != (date.month, date.day):
            print("  [SKIP] id=%s 列表行=%s 但文章屏=%s (日期不符, 不归档)"
                  % (aid, date, t.strftime("%m-%d")), flush=True)
            b.back_robust()
            b.move_up()
            continue
        if t is None:
            print("  [WARN] id=%s 文章屏无发信时间(可能未读全), 保留但标记" % aid, flush=True)
        posts.append({
            "id": aid, "author": author, "nick": art.get("nick"),
            "title": art.get("title") or title, "time_str": art.get("time_str"),
            "time_utc": (t or R.dt.datetime.combine(date, R.dt.time(0), R.TZ)).isoformat(),
            "body": art.get("body", ""), "post_date": date.isoformat(),
            "time_missing": t is None,
        })
        last_read_aid = aid
        if len(posts) % 10 == 0:
            print("  ...已读 %d 帖 (最新 %s)" % (len(posts), date), flush=True)
        b.back_robust()
        if len(posts) >= max_threads:
            break
        b.move_up()
    return posts, complete


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--commit", action="store_true", default=True)
    ap.add_argument("--no-commit", dest="commit", action="store_false")
    args = ap.parse_args()
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    cfg = R.load_config()
    year = start.year
    b = BBS(credentials=cfg["credentials"])
    b.login_with_retry()
    by_day = {}
    complete = False
    for board in cfg["boards"]:
        b.open_board(board)
        posts, complete = traverse_range(b, board, year, start, end)
        for p in posts:
            by_day.setdefault(p["post_date"], {}).setdefault(board, []).append(p)
    b.close()
    n_total = sum(len(v) for d in by_day.values() for v in d.values())
    print("TRAVERSE_DONE posts=%d complete=%s" % (n_total, complete), flush=True)

    now = R.bj_now()
    total = 0
    for day in sorted(by_day):
        d = os.path.join(cfg["root"], "%04d" % int(day[:4]), "%02d" % int(day[5:7]), "%02d" % int(day[8:10]), "24")
        os.makedirs(d, exist_ok=True)
        if day == start.isoformat() and not complete:
            print("DAY %s: 不完整(未扫到起点), 跳过归档" % day, flush=True)
            continue
        meta = {"slot": "24", "mode": "backfill_range", "complete": complete,
                "generated_bj": now.isoformat(), "target_day": day,
                "window_bj": "%s 00:00 ~ 24:00 (北京)" % day, "boards": {}}
        for board, posts in by_day[day].items():
            threads = R.classify(posts)
            pth, n = R.write_board_md(d, cfg, "24", now, dt.date.fromisoformat(day),
                                      R.window_start_utc(dt.date.fromisoformat(day)), board, threads)
            meta["boards"][board] = {
                "thread_count": len(threads), "post_count": n,
                "threads": [{"title": t["title"], "is_new_today": t["is_new_today"],
                             "post_count": len(t["posts"]),
                             "authors": sorted(set(x["author"] for x in t["posts"]))} for t in threads]}
            total += n
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        if args.commit:
            rev = R.git_commit(cfg, "shuimu backfill %s 全天" % day)
            meta["git_commit"] = rev
        print("DAY %s: posts=%d commit=%s" % (day, sum(v["post_count"] for v in meta["boards"].values()), rev if args.commit else "-"), flush=True)
    print("BACKFILL_DONE total=%d days=%d complete=%s" % (total, len(by_day), complete), flush=True)


if __name__ == "__main__":
    main()
