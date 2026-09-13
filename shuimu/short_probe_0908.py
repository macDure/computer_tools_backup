#!/usr/bin/env python3
"""short_probe_0908.py — 限流冷却后短爬试探 (2026-09-08 00:00~08:00 北京)

用户 09-08 早晨指令: 不补爬(放一边), 只按常规计划短爬一次,
验证"短爬一小段时间的数据"在冷却后是否可行。

安全边界 (硬约束):
  - 单会话, 走 login_with_retry (flock 单会话锁, 抢不到 SessionBusy 退出码 0)
  - 仅 Stock 版, 从最新帖向上读到 2026-09-08 00:00(北京) 为止
  - 步数上限 40 步 (09-07 19:03 探测 120 步 PASS; 这里留足余量)
  - 时间预算 25 分钟, 到点收手
  - 数据照常写盘 + git 提交 (目录 2026-09-08/24/ 与常规流水线同构,
    后续 08:00 档重跑同窗口会幂等覆盖, 不冲突)
"""
import datetime as dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shuimu_run as R
from shuimu_telnet import BBS, SessionBusy

TZ = dt.timezone(dt.timedelta(hours=8))
TARGET = dt.date(2026, 9, 8)
MAX_STEPS = 40
TIME_BUDGET_S = 25 * 60
T0 = time.time()


def main():
    cfg = R.load_config()
    now_bj = R.bj_now()
    win_start = R.window_start_utc(TARGET)
    d = R.slot_dirname(cfg, "24", TARGET)
    os.makedirs(d, exist_ok=True)
    print("START bj=%s win_start=%s dir=%s" % (
        now_bj.isoformat(), win_start.isoformat(), d), flush=True)

    b = BBS(credentials=cfg["credentials"])
    b.login_with_retry()
    print("LOGIN_OK", flush=True)
    b.open_board("Stock")
    print("BOARD_OPEN steps=0", flush=True)

    posts, seen, steps = [], set(), 0
    hit_start = False
    kicked = False
    try:
        while steps < MAX_STEPS and time.time() - T0 < TIME_BUDGET_S:
            steps += 1
            scr = b.screen()
            row = _first_sel_row(scr, now_bj.year)
            if row is None:
                b.move_up(); b._recv(0.5)
                print("STEP %d no-row" % steps, flush=True)
                continue
            aid = row[0]
            if aid in seen:
                break
            seen.add(aid)
            art = b.read_current_paged(max_pages=8)
            b._recv(0.3)
            t = R.parse_ts_str(art["time_str"]) if art.get("time_str") else None
            if t is None:
                print("STEP %d no-time id=%s" % (steps, aid), flush=True)
                b.back_robust(); b.move_up(); continue
            if t < win_start:
                hit_start = True
                b.back_robust()
                break
            posts.append({
                "id": aid, "author": art.get("author"), "nick": art.get("nick"),
                "title": art.get("title"), "time_utc": t.isoformat(),
                "time_str": art.get("time_str"), "body": art.get("body", ""),
            })
            print("STEP %d id=%s t=%s title=%s" % (
                steps, aid, t.strftime("%m-%d %H:%M:%S"),
                (art.get("title") or "")[:40]), flush=True)
            b.back_robust()
            if steps % 5 == 0:
                print("STEP %d posts=%d elapsed=%.0fs" % (
                    steps, len(posts), time.time() - T0), flush=True)
            # 被踢检测: 主选单顶栏出现在列表区 = 被踢回主选单
            # (09-07 硬窗口内每 ~5 步被踢; 二次确认防瞬态渲染误报)
            top = b.screen().split("\n")[:4]
            if any("主选单" in ln for ln in top):
                b._recv(2.0)
                top = b.screen().split("\n")[:4]
                if any("主选单" in ln for ln in top):
                    kicked = True
                    print("KICKED at step %d (主选单 top=%r) elapsed=%.0fs"
                          % (steps, top[:2], time.time() - T0), flush=True)
                    break
            b.move_up()
    except Exception as e:
        kicked = True
        print("EXCEPTION at step %d: %r (elapsed=%.0fs)" % (
            steps, e, time.time() - T0), flush=True)
    finally:
        try:
            b.close()
        except Exception:
            pass

    elapsed = time.time() - T0
    if not kicked:
        threads = R.classify(posts)
        meta = {"slot": "24", "generated_bj": R.bj_now().isoformat(),
                "target_day": TARGET.isoformat(),
                "window_start_bj": R.to_bj(win_start).isoformat(),
                "probe": True, "max_steps": MAX_STEPS,
                "steps_used": steps, "elapsed_s": round(elapsed),
                "boards": {}}
        total = 0
        if posts:
            path, n = R.write_board_md(d, cfg, "24", R.bj_now(), TARGET,
                                       win_start, "Stock", threads)
            total = n
            meta["boards"]["Stock"] = {
                "thread_count": len(threads), "post_count": n,
                "threads": [
                    {"title": t["title"], "is_new_today": t["is_new_today"],
                     "first_time_bj": R.to_bj(dt.datetime.fromisoformat(t["first_time"])).isoformat(),
                     "post_count": len(t["posts"]),
                     "authors": sorted(set(p["author"] for p in t["posts"]))}
                    for t in sorted(threads, key=lambda x: x["first_time"])
                ]}
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        rev = R.git_commit(cfg, "shuimu probe 2026-09-08 00:00~08:00 短爬试探")
        print("WROTE posts=%d threads=%d git=%s" % (total, len(threads), rev),
              flush=True)

    print("RESULT=%s" % ("OK" if (not kicked and hit_start)
                          else "OK_PARTIAL" if not kicked else "FAILED_KICKED"),
          flush=True)
    print("STATS steps=%d posts=%d hit_window_start=%s kicked=%s elapsed=%.0fs" % (
        steps, len(posts), hit_start, kicked, elapsed), flush=True)


def _first_sel_row(scr, year):
    from shuimu_telnet import parse_sel_row
    for ln in scr.split("\n"):
        row = parse_sel_row(ln, year=year)
        if row:
            return row
    return None


if __name__ == "__main__":
    try:
        main()
    except SessionBusy as e:
        print("SKIPPED_SESSION_BUSY: %s" % e, flush=True)
        sys.exit(0)
