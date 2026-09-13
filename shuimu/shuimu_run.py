#!/usr/bin/env python3
"""shuimu_run.py — 水木论坛每日定时爬虫主流水线 (确定性部分, 不碰 LLM)

职责:
  1. 登录 telnet, 逐个打开配置版面
  2. 从最新帖往上遍历 (k), 逐篇读全文 (r + 长帖 space 翻页),
     读到时间戳早于 "目标日 00:00 (北京)" 即停
  3. 按主题归组 (去 Re: 前缀归一), 区分 今日新帖 / 旧帖今日回复
  4. 写 原帖_<board>.md + meta.json 到  root/YYYY/MM/DD/HH/
  5. 本地 git 提交 (无变更则跳过)

时间口径:
  水木服务器时间戳是 UTC。"当日 0 点" 按北京时间 (UTC+8) 界定,
  window_start_utc = 北京 target_day 00:00 - 8h。
  slot 24 (00:00 跑) 覆盖 "昨天"(北京), 其余 slot 覆盖 "今天"。
"""
import argparse
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shuimu_telnet import BBS, parse_list, parse_sel_row

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
TZ = dt.timezone(dt.timedelta(hours=8))
WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def bj_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(TZ)


def target_day_for_slot(slot, now_bj):
    if slot == "24":
        return (now_bj - dt.timedelta(days=1)).date()
    return now_bj.date()


def window_start_utc(target_day):
    # 窗口起点 = 北京 target_day 00:00 (tz=+8)。服务器时间戳即北京时间, 直接比较
    return dt.datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=TZ)


def parse_ts_str(ts_str):
    """'Thu Sep  3 00:40:35 2026' -> aware UTC datetime (服务器时间=UTC)."""
    try:
        naive = dt.datetime.strptime(ts_str, "%a %b %d %H:%M:%S %Y")
    except Exception:
        return None
    return naive.replace(tzinfo=TZ)


def to_bj(d):
    # 水木服务器时间戳 = 北京时间(2026-09-03 实测: 服务器显示 02:37 == 容器北京 02:37)
    # 故 parse_ts_str 已按 +8 解析, 此处恒等返回, 保留函数名兼容调用点
    return d


def thread_key(title):
    t = (title or "").strip()
    t = re.sub(r"^(re:\s*)+", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).lower()


def fmt(d_utc):
    return to_bj(d_utc).strftime("%m-%d %H:%M:%S")


def traverse_board(b, board, win_start_utc, max_threads, read_pause, win_end_utc=None):
    posts = []
    seen = set()
    guard = 0
    skipped_new = 0
    unparse_streak = 0  # 连续列表行不可解析计数 (09-09 修复: 防 ANSI 脏行静默死循环)
    while guard < max_threads * 2 + 30:
        guard += 1
        scr = b.screen()
        row = None
        _yr = dt.datetime.now(TZ).year
        for ln in scr.split("\n"):
            if re.match(r"\s*>?\s*\[提示\]", ln):
                continue
            row = parse_sel_row(ln, year=_yr)
            if row:
                break
        if row is None:
            unparse_streak += 1
            print("  [UNPARSE x%d] 列表行不可解析, move_up 继续 (guard=%d)" % (unparse_streak, guard), flush=True)
            b.move_up(); b._recv(0.5); time.sleep(random.uniform(1.0, 2.5))
            if unparse_streak > 60:
                # 连续 60 步无有效行 = 界面卡死/被踢, 收手 (上层按零产出处理, 后续 slot 兜底)
                print("  [ABORT] 连续 60 步列表行不可解析, 收手 (guard=%d)" % guard, flush=True)
                break
            continue
        unparse_streak = 0
        aid = row[0]
        if aid in seen:
            break
        seen.add(aid)
        art = b.read_current_paged(max_pages=8)
        b._recv(0.3)
        t_utc = parse_ts_str(art["time_str"]) if art.get("time_str") else None
        if t_utc is None:
            b.back_robust(); b.move_up(); continue
        if t_utc < win_start_utc:
            b.back_robust()
            break
        # 上界过滤(补爬): 比 win_end 新的帖跳过(不收录), 但继续往旧读
        if win_end_utc is not None and t_utc >= win_end_utc:
            skipped_new += 1
            b.back_robust()
            if len(posts) >= max_threads:
                break
            b.move_up()
            continue
        posts.append({
            "id": aid, "author": art.get("author"), "nick": art.get("nick"),
            "title": art.get("title"), "time_utc": t_utc.isoformat(),
            "time_str": art.get("time_str"), "body": art.get("body", ""),
        })
        b.back_robust()
        if len(posts) >= max_threads:
            break
        b.move_up()
    return posts


def classify(posts):
    threads = {}
    order = []
    for p in sorted(posts, key=lambda x: x["time_utc"]):
        k = thread_key(p["title"])
        if k not in threads:
            clean = re.sub(r"^(re:\s*)+", "", (p["title"] or ""), flags=re.I).strip() or (p["title"] or "")
            threads[k] = {"title": clean, "first_id": p["id"],
                          "first_time": p["time_utc"], "posts": []}
            order.append(k)
        threads[k]["posts"].append(p)
    out = []
    for k in order:
        t = threads[k]
        t["is_new_today"] = not (t["posts"][0]["title"] or "").lower().startswith("re:")
        out.append(t)
    return out


def slot_dirname(cfg, slot, target_day):
    return os.path.join(cfg["root"], "%04d" % target_day.year,
                        "%02d" % target_day.month, "%02d" % target_day.day, slot)


def write_board_md(d, cfg, slot, now_bj, target_day, win_start_utc, board, threads):
    n_posts = sum(len(t["posts"]) for t in threads)
    L = []
    L.append("# 水木 %s 版 原帖归档" % board)
    L.append("")
    L.append("- 生成时间 (北京): %s" % now_bj.strftime("%Y-%m-%d %H:%M:%S"))
    L.append("- 时段: %s (%s)" % (slot, cfg["slots"].get(slot, slot)))
    L.append("- 统计窗口: %s (北京) 起" % to_bj(win_start_utc).strftime("%Y-%m-%d %H:%M:%S"))
    L.append("- 主题数: %d | 帖子数: %d" % (len(threads), n_posts))
    L.append("")
    for i, t in enumerate(sorted(threads, key=lambda x: x["first_time"]), 1):
        tag = "今日新帖" if t["is_new_today"] else "旧帖今日回复"
        L.append("---")
        L.append("")
        L.append("## %d. %s" % (i, t["title"]))
        L.append("")
        L.append("> 类型: %s | 首帖: %s | 楼层数: %d" % (
            tag, to_bj(dt.datetime.fromisoformat(t["first_time"])).strftime("%m-%d %H:%M"),
            len(t["posts"])))
        L.append("")
        for p in t["posts"]:
            pj = to_bj(dt.datetime.fromisoformat(p["time_utc"]))
            L.append("### [%s] %s" % (pj.strftime("%m-%d %H:%M:%S"), p["author"]))
            if p.get("nick"):
                L[-1] += " (%s)" % p["nick"]
            L.append("")
            L.append(p["body"] if p["body"].strip() else "(正文为空)")
            L.append("")
    path = os.path.join(d, "原帖_%s.md" % board)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path, n_posts


def git_commit(cfg, msg):
    root = cfg["root"]
    env = dict(os.environ, GIT_AUTHOR_NAME="shuimu-bot", GIT_AUTHOR_EMAIL="shuimu@local",
               GIT_COMMITTER_NAME="shuimu-bot", GIT_COMMITTER_EMAIL="shuimu@local")
    if not os.path.exists(os.path.join(root, ".git")):
        subprocess.run(["git", "init"], cwd=root, env=env, capture_output=True)
        subprocess.run(["git", "config", "user.email", "shuimu@local"], cwd=root, env=env, capture_output=True)
        subprocess.run(["git", "config", "user.name", "shuimu-bot"], cwd=root, env=env, capture_output=True)
        with open(os.path.join(root, ".gitignore"), "w") as f:
            f.write(".DS_Store\n*.tmp\n")
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, capture_output=True)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root, env=env, capture_output=True)
    if r.returncode == 0:
        return None
    subprocess.run(["git", "commit", "-m", msg], cwd=root, env=env, capture_output=True, text=True)
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, env=env,
                         capture_output=True, text=True)
    return rev.stdout.strip()


def feishu_send(text):
    ENV = "/opt/data/.env"
    CHAT_ID = "oc_3f03c1c9f05b59bb247d65c90fa1cca1"
    vals = {}
    for line in open(ENV):
        line = line.strip()
        if line.startswith("FEISHU_APP_ID="):
            vals["id"] = line.split("=", 1)[1]
        elif line.startswith("FEISHU_APP_SECR"):
            vals["sec"] = line.split("=", 1)[1]
    if not vals.get("id") or not vals.get("sec"):
        return False
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": vals["id"], "app_secret": vals["sec"]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        token = json.loads(r.read()).get("tenant_access_token", "")
    if not token:
        return False
    body = {"receive_id": CHAT_ID, "msg_type": "text",
            "content": json.dumps({"text": text})}
    req2 = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
    with urllib.request.urlopen(req2, timeout=15) as r:
        d = json.loads(r.read())
    return d.get("code") == 0


def run(slot, now_bj=None, commit=True, dry_run=False, date_str=None):
    cfg = load_config()
    now_bj = now_bj or bj_now()
    if date_str:  # 补爬: 指定日期(窗口起点=该天 00:00 北京), slot 用作目录名
        target_day = dt.date.fromisoformat(date_str)
    else:
        target_day = target_day_for_slot(slot, now_bj)
    win_start_utc = window_start_utc(target_day)
    win_end_utc = (win_start_utc + dt.timedelta(days=1)) if date_str else None
    d = slot_dirname(cfg, slot, target_day)
    os.makedirs(d, exist_ok=True)
    all_threads = {}
    b = BBS(credentials=cfg["credentials"])
    b.login_with_retry()
    for board in cfg["boards"]:
        b.open_board(board)
        posts = traverse_board(b, board, win_start_utc, cfg["max_threads"], cfg.get("read_pause", 0.7), win_end_utc)
        threads = classify(posts)
        all_threads[board] = threads
        print("[board %s] posts=%d threads=%d" % (board, len(posts), len(threads)))
    b.close()
    # 写文件
    meta = {"slot": slot, "generated_bj": now_bj.isoformat(),
            "target_day": target_day.isoformat(),
            "window_start_bj": to_bj(win_start_utc).isoformat(),
            "boards": {}}
    total = 0
    for board in cfg["boards"]:
        threads = all_threads.get(board, [])
        if not threads and not dry_run:
            continue
        path, n = write_board_md(d, cfg, slot, now_bj, target_day, win_start_utc, board, threads)
        total += n
        meta["boards"][board] = {
            "thread_count": len(threads), "post_count": n,
            "threads": [
                {"title": t["title"], "is_new_today": t["is_new_today"],
                 "first_time_bj": to_bj(dt.datetime.fromisoformat(t["first_time"])).isoformat(),
                 "post_count": len(t["posts"]),
                 "authors": sorted(set(p["author"] for p in t["posts"]))}
                for t in sorted(threads, key=lambda x: x["first_time"])
            ],
        }
    if not dry_run:
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        if commit:
            rev = git_commit(cfg, "shuimu %s %s (%s)" % (target_day.isoformat(), slot, meta.get("generated_bj", "")[:16]))
            meta["git_commit"] = rev
    print("OUTPUT_DIR=%s" % d)
    print("TOTAL_POSTS=%d" % total)
    print("META=%s" % json.dumps({bd: {"threads": v["thread_count"], "posts": v["post_count"]}
                                   for bd, v in meta["boards"].items()}, ensure_ascii=False))
    return {"dir": d, "meta": meta, "total": total}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True, choices=["08", "12", "16", "24"])
    ap.add_argument("--date", default=None, help="补爬: 指定目标日期 YYYY-MM-DD (窗口=该天 00:00~次日 00:00 北京)")
    ap.add_argument("--commit", dest="commit", action="store_true", default=True)
    ap.add_argument("--no-commit", dest="commit", action="store_false")
    ap.add_argument("--dry-run", action="store_true", help="只遍历不写文件不提交")
    args = ap.parse_args()
    run(args.slot, commit=args.commit, dry_run=args.dry_run, date_str=args.date)
