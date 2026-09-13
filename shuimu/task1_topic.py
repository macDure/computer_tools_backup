#!/usr/bin/env python3
"""task1_topic.py v3 — 专题: 爬取指定主题的全部讨论(列表驱动, 全干净数据)

机制 (2026-09-03 实测):
  主题阅读翻屏有 ANSI 差分重绘串扰(短行覆盖长行不清尾, 作者/时间行污染).
  但 版面列表行(screen) + 单帖 r 读(screen) 两条路径在 08:00 流水线中
  已验证 16/16 干净. 故改为列表驱动:
    k 上移遍历 → 标题归一(去 Re:) 匹配目标主题 → 逐篇 r 读全文
    → 读到"原帖"(无 Re: 前缀)后再遇 5 个非主题帖即停
    → 按 id 升序写 MD (原帖+全部楼层, 元数据+正文全干净)
"""
import argparse, datetime as dt, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shuimu_telnet import BBS

TZ = dt.timezone(dt.timedelta(hours=8))
SEL_RE = re.compile(r"\s*>\s*(\d{6,7})\s+\*?\s*(\S+)\s+(\S{3})\s+(\d{1,2})\s+(.*)$")


def thread_key(title):
    t = (title or "").strip()
    t = re.sub(r"^(re:\s*)+", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).lower()


def is_hint(ln):
    return bool(re.match(r"\s*>?\s*\[提示\]", ln))


def find_and_collect(b, keyword, max_scan):
    """k 上移遍历: 收集所有 thread_key 匹配 keyword 归一主题的帖.
    返回 (posts, scanned). 读到原帖后连续 5 个非主题帖停."""
    # 先用首页选中行确定目标 key (若首页就是本主题帖); 否则边扫边定
    target_key = None
    posts, seen = [], set()
    nonthread_after_orig = 0
    orig_seen = False
    scanned = 0
    while scanned < max_scan:
        scr = b.screen()
        sel = None
        for ln in scr.split("\n"):
            if is_hint(ln):
                continue
            m = SEL_RE.match(ln)
            if m:
                sel = m
                break
        if sel is None:
            b.move_up(); time.sleep(0.3)
            scanned += 1
            if scanned > max_scan:
                break
            continue
        aid, author, mon, day, title = sel.groups()
        scanned += 1
        if aid in seen:
            break
        seen.add(aid)
        if target_key is None:
            tk = thread_key(title)
            if keyword.lower() in tk:
                target_key = tk
            else:
                b.move_up(); time.sleep(0.4)
                continue
        if target_key is not None and thread_key(title) == target_key:
            art = b.read_current_paged(max_pages=8)
            b.back_robust()
            posts.append({
                "id": aid, "author": author,  # 列表行作者(干净), 不用文章屏(可能 ANSI 残留)
                "nick": art.get("nick"),
                "title": art.get("title") or title, "time_str": art.get("time_str"),
                "time_list": "%s %s" % (mon, day), "body": art.get("body", ""),
            })
            is_orig = not (title or "").strip().lower().startswith("re:")
            if is_orig:
                orig_seen = True
                nonthread_after_orig = 0
            print("  +id=%s %s %s orig=%s" % (aid, author, (art.get("time_str") or "")[-19:], is_orig), flush=True)
            if orig_seen:
                nonthread_after_orig = 0
        else:
            if orig_seen:
                nonthread_after_orig += 1
                if nonthread_after_orig >= 5:
                    break
        b.move_up(); time.sleep(0.4)
    return posts, scanned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="Stock")
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--max_scan", type=int, default=600)
    args = ap.parse_args()

    b = BBS()
    b.login_with_retry()
    b.open_board(args.board)
    time.sleep(1.0)

    posts, scanned = find_and_collect(b, args.keyword, args.max_scan)
    b.close()
    print("COLLECTED=%d scanned=%d" % (len(posts), scanned), flush=True)
    if not posts:
        print("NOT_FOUND", flush=True)
        sys.exit(2)

    posts.sort(key=lambda p: int(p["id"]))
    now = dt.datetime.now(TZ)
    os.makedirs(args.outdir, exist_ok=True)
    title0 = re.sub(r"^(re:\s*)+", "", posts[0]["title"] or "", flags=re.I).strip() or args.keyword

    with open(os.path.join(args.outdir, "原帖_主题_%s.md" % args.board), "w", encoding="utf-8") as f:
        f.write("# 水木 %s 版 主题全讨论（原文）\n\n" % args.board)
        f.write("- **主题**：%s\n" % title0)
        f.write("- **楼层数**：%d（原帖 1 + 回复 %d）\n" % (len(posts), len(posts) - 1))
        f.write("- **爬取时间**：%s（北京时间，快照）\n" % now.strftime("%Y-%m-%d %H:%M"))
        f.write("- **说明**：主题仍在增长中，本文件为爬取时刻的完整快照\n\n---\n")
        for i, p in enumerate(posts, 1):
            role = "📌 原帖" if i == 1 else "💬 回复 #%d" % i
            f.write("\n## %s — %s%s [%s]\n\n" % (role, p["author"] or "?",
                                                " (%s)" % p["nick"] if p.get("nick") else "",
                                                p["id"]))
            f.write("> 发信时间：%s\n" % (p.get("time_str") or p.get("time_list") or "?"))
            f.write("\n%s\n" % ((p.get("body") or "").strip() or "(正文为空)"))
    with open(os.path.join(args.outdir, "meta_topic.json"), "w", encoding="utf-8") as f:
        json.dump({
            "board": args.board, "keyword": args.keyword, "title": title0,
            "post_count": len(posts), "scanned": scanned,
            "ids": [p["id"] for p in posts],
            "authors": sorted(set(p["author"] for p in posts if p.get("author"))),
            "time_range": [posts[0].get("time_str"), posts[-1].get("time_str")],
            "crawled_at": now.isoformat(),
        }, f, ensure_ascii=False, indent=2)
    print("DONE posts=%d dir=%s" % (len(posts), args.outdir), flush=True)


if __name__ == "__main__":
    main()
