#!/usr/bin/env python3
"""backfill_meta.py — 存量 nf_api 窗 meta.json 补全 (09-12 用户指令)
老 meta 只有 title/authors/first_time, 正文/gid/每楼时间全在 md 里。
本脚本解析 原帖_Stock.md, 重建 threads[].posts 完整结构写回 meta.json (幂等):
  threads[]: {title, gid(存量无, null), first_time_bj, last_time_bj, post_count,
              authors, posts:[{seq,time,author,content,attachments:[{name,size,fname,is_img}]}]}
meta_version=2 标记; 已有 posts 的窗 (新格式) 跳过。不碰 md/附件/队列。
用法: python backfill_meta.py --year 2026 [--month 01]
"""
import re, json, os, sys, argparse, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
ARCH = "/opt/data/shuimu_daily"
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
ATT_RE = re.compile(r"📎 附件: (.+?) \((.*?)\) -> `attachments/([^`]+)`")
POST_RE = re.compile(r"^### \[(\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+)$", re.M)
TOPIC_RE = re.compile(r"\n## (\d+)\. (.+?)(?=\n## \d+\. |\Z)", re.S)
HEAD_RE = re.compile(r"> 类型: 主题 \| 首帖: (\d{2}-\d{2} \d{2}:\d{2}) \| 楼层数: (\d+)")

def parse_md(path, year):
    """md 全文 -> [thread dict] (thread 结构与新 meta 完全一致)"""
    txt = open(path, encoding="utf-8").read()
    threads = []
    for m in TOPIC_RE.finditer(txt):
        title = m.group(2).strip().split("\n")[0].strip()  # 只取首行 (re.S 下 group 会吞整块)
        chunk = m.group(0)
        hm = HEAD_RE.search(chunk)
        if not hm:
            continue
        first_mmdd, declared = hm.group(1), int(hm.group(2))
        posts = []
        pm = list(POST_RE.finditer(chunk))
        for i, pmth in enumerate(pm):
            start = pmth.end()
            end = pm[i + 1].start() if i + 1 < len(pm) else len(chunk)
            body = chunk[start:end]
            atts = []
            for a in ATT_RE.finditer(body):
                name, size_disp, fname = a.group(1).strip(), a.group(2).strip(), a.group(3).strip()
                atts.append({"name": name, "size": size_disp, "fname": fname,
                             "is_img": os.path.splitext(fname)[1].lower() in IMG_EXT})
            content = ATT_RE.sub("", body)
            content = content.rstrip()
            if content.endswith("---"):
                content = content[:-3].rstrip()
            mmdd, hm = pmth.group(1).split(" ")  # "01-16 08:09:28" -> ("01-16", "08:09:28")
            t = dt.datetime.strptime("%s-%d %s" % (mmdd, year, hm), "%m-%d-%Y %H:%M:%S")
            posts.append({"seq": i + 1,
                          "time": t.replace(tzinfo=dt.timezone(dt.timedelta(hours=8))).isoformat(),
                          "author": pmth.group(2).strip(),
                          "content": content,
                          "attachments": atts})
        if not posts:
            continue
        threads.append({
            "title": title, "gid": None,
            "first_time_bj": posts[0]["time"],
            "last_time_bj": posts[-1]["time"],
            "post_count": len(posts),
            "authors": list({p["author"] for p in posts}),
            "posts": posts,
        })
    return threads

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", required=True)
    ap.add_argument("--month")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="已是 v2 的窗也重写")
    a = ap.parse_args()
    year_base = os.path.join(ARCH, a.year)
    # 指定 month: [year/month]; 不指定: 遍历 year/ 下所有 MM 目录
    if a.month:
        month_dirs = [(a.month, os.path.join(year_base, a.month))]
    else:
        month_dirs = [(d, os.path.join(year_base, d)) for d in sorted(os.listdir(year_base))
                      if re.fullmatch(r"\d{2}", d) and os.path.isdir(os.path.join(year_base, d))]
    n_win = n_skip = n_bad = 0
    for _, mp in month_dirs:
        for day in sorted(os.listdir(mp)):
            dp = os.path.join(mp, day)
            if not os.path.isdir(dp) or not re.fullmatch(r"\d{2}", day):
                continue
            for slot in sorted(os.listdir(dp)):
                d = os.path.join(dp, slot)
                meta_p = os.path.join(d, "meta.json")
                md_p = os.path.join(d, "原帖_Stock.md")
                if not (os.path.isfile(meta_p) and os.path.isfile(md_p)):
                    continue
                n_win += 1
                meta = json.load(open(meta_p))
                st = meta.get("boards", {}).get("Stock", {})
                if st.get("mode") != "nf_api" and meta.get("mode") != "nf_api":
                    n_skip += 1
                    continue
                if any("posts" in t for t in st.get("threads", [])) and not a.force:
                    n_skip += 1  # 已是新格式
                    continue
                year = int(a.year)
                try:
                    threads = parse_md(md_p, year)
                except Exception as e:
                    n_bad += 1
                    print("  ⚠ 解析失败 %s/%s: %s" % (day, slot, e))
                    continue
                # 校验: 楼层数与 meta 声明一致
                declared_total = st.get("post_count", 0)
                got_total = sum(t["post_count"] for t in threads)
                if declared_total and got_total != declared_total:
                    n_bad += 1
                    print("  ⚠ 帖数不符 %s/%s: meta=%d md=%d (跳过, 需人工看)" % (day, slot, declared_total, got_total))
                    continue
                st["threads"] = threads
                st["thread_count"] = len(threads)
                st["post_count"] = got_total
                st["attachment_count"] = sum(len(p["attachments"]) for t in threads for p in t["posts"])
                st["mode"] = "nf_api"
                st["meta_version"] = 2
                st["meta_backfilled_bj"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
                if not a.dry_run:
                    json.dump(meta, open(meta_p, "w"), ensure_ascii=False, indent=1)
    print("窗数=%d 跳过(新格式/非nf)=%d 异常=%d %s" % (n_win, n_skip, n_bad, "(dry-run)" if a.dry_run else "已写回"))

if __name__ == "__main__":
    main()
