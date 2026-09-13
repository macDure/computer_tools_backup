#!/usr/bin/env python3
"""extract_author_posts.py — 按发帖人提取全部帖子 (09-12 用户指令)

数据源: /opt/data/shuimu_daily/<YYYY>/<MM>/<DD>/wHH/meta.json (meta v2)
用法:
  # 看谁发得最多 (前N)
  python3 extract_author_posts.py --top 20
  # 模糊找人名
  python3 extract_author_posts.py --find 北
  # 提取某人全部帖子 (精确匹配) -> <out>/<昵称>.md + .json
  python3 extract_author_posts.py --author 中年惨男 --out /opt/data/tmp/author_extract
  # 按子串提取(可能多人同名, 输出里按人分节)
  python3 extract_author_posts.py --author-substr 北北 --out /opt/data/tmp/author_extract
  # 只看某月
  python3 extract_author_posts.py --author 中年惨男 --month 01 --out ...
输出 md: 按时间升序, 每条 = 时间 | 主题(楼主/回复N楼) | 正文 | 附件
去重: 同 (time, author, content) 跨窗只留最新归档版本
"""
import os, re, json, argparse, datetime as dt

ARCH = "/opt/data/shuimu_daily"
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

def iter_posts(arch, year, month=None):
    """yield (author, time_iso, gid, title, seq, content, atts, rel_win)"""
    base = os.path.join(arch, str(year))
    if not os.path.isdir(base):
        return
    months = [month] if month else sorted(os.listdir(base))
    for mm in months:
        dp = os.path.join(base, mm)
        if not os.path.isdir(dp):
            continue
        for day in sorted(os.listdir(dp)):
            dpath = os.path.join(dp, day)
            if not os.path.isdir(dpath):
                continue
            for slot in sorted(os.listdir(dpath)):
                mp = os.path.join(dpath, slot, "meta.json")
                if not os.path.isfile(mp):
                    continue
                st = json.load(open(mp)).get("boards", {}).get("Stock", {})
                if st.get("meta_version") != 2:
                    continue
                rel_win = "%s/%s/%s" % (mm, day, slot)
                for t in st.get("threads", []):
                    gid = t.get("gid")
                    title = t.get("title") or "(无题)"
                    for p in t.get("posts") or []:
                        seq = p.get("seq")
                        yield (p.get("author") or "?", p.get("time") or "",
                               gid, title, seq, (p.get("content") or "").strip(),
                               p.get("attachments") or [], rel_win)

def collect(arch, year, month=None):
    """全量收 -> {author: [(time, gid, title, seq, content, atts, win)]}"""
    data = {}
    for author, time, gid, title, seq, content, atts, win in iter_posts(arch, year, month):
        data.setdefault(author, []).append(
            (time, gid, title, seq, content, atts, win))
    return data

def dedupe(posts):
    """同 (time, content) 跨窗去重, 保留最新窗(win 字典序最大)"""
    best = {}
    for time, gid, title, seq, content, atts, win in posts:
        k = (time, content)
        old = best.get(k)
        if old is None or win > old[6]:
            best[k] = (time, gid, title, seq, content, atts, win)
    return sorted(best.values(), key=lambda x: (x[0], str(x[2])))

def fmt_posts_md(name, posts, year="2026", link_prefix=""):
    """link_prefix: 从最终放置目录(默认 shuimu/发帖人/) 到 仓库 shuimu/ 的相对前缀 (默认 ../)"""
    L = ["# %s 的全部帖子 (%d 条)" % (name, len(posts)), ""]
    for time, gid, title, seq, content, atts, win in posts:
        role = "楼主" if (seq in (1, "1")) else "回复%s楼" % seq
        L.append("## %s · %s · 「%s」" % (time or "?", role, title))
        L.append("")
        L.append(content or "(空)")
        for a in atts:
            fn = a.get("fname") or ""
            if not fn:
                continue
            L.append("")
            if fn.lower().endswith(IMG_EXT):
                L.append("![%s](%s帖子/%s/%s/attachments/%s)" % (a.get("name") or fn, link_prefix, year, win, fn))
            else:
                L.append("📎 附件: %s -> `%s帖子/%s/%s/attachments/%s`" % (a.get("name"), link_prefix, year, win, fn))
        L.append("")
    return "\n".join(L)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="2026")
    ap.add_argument("--month", help="MM, 缺省全年")
    ap.add_argument("--author", help="精确匹配昵称")
    ap.add_argument("--author-substr", help="子串匹配(可命中多人)")
    ap.add_argument("--find", help="只搜含该子串的昵称列表, 不提取")
    ap.add_argument("--top", type=int, help="显示发帖最多的 N 人")
    ap.add_argument("--out", default="/opt/data/tmp/author_extract")
    ap.add_argument("--arch", default=os.environ.get("SHUIMU_ARCH", "/opt/data/shuimu_daily"),
                    help="归档根 (<YYYY>/<MM>/<DD>/<slot>/meta.json), 换机时指向 帖子 归档目录")
    a = ap.parse_args()

    data = collect(a.arch, a.year, a.month)
    ranking = sorted(data.items(), key=lambda kv: -len(kv[1]))

    if a.find:
        hits = [(n, len(p)) for n, p in ranking if a.find in n]
        print("含 '%s' 的昵称 %d 个 (按发帖数):" % (a.find, len(hits)))
        for n, c in hits[:50]:
            print("  %-24s %d" % (n, c))
        return
    if a.top:
        print("2026 发帖最多的 %d 人 (总发帖人 %d):" % (a.top, len(ranking)))
        for n, c in ranking[:a.top]:
            print("  %-24s %d" % (n, len(c)))
        return
    if not (a.author or a.author_substr):
        ap.print_help()
        return

    targets = []
    if a.author:
        if a.author not in data:
            print("❌ 没找到昵称 '%s', 用 --find 模糊搜" % a.author)
            return
        targets = [(a.author, data[a.author])]
    else:
        targets = [(n, p) for n, p in ranking if a.author_substr in n]
        print("子串 '%s' 命中 %d 人" % (a.author_substr, len(targets)))
        if not targets:
            return

    os.makedirs(a.out, exist_ok=True)
    for name, posts in targets:
        d = dedupe(posts)
        safe = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)[:40]
        mdp = os.path.join(a.out, safe + ".md")
        jsonp = os.path.join(a.out, safe + ".json")
        open(mdp, "w", encoding="utf-8").write(fmt_posts_md(name, d, year=a.year, link_prefix="../"))
        json.dump([{ "time": t, "gid": g, "topic": ti, "seq": s,
                     "content": c, "attachments": at, "source_window": w}
                   for t, g, ti, s, c, at, w in d],
                  open(jsonp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        span = "%s ~ %s" % (d[0][0], d[-1][0]) if d else "?"
        print("✅ %-20s %5d 条 (%s) -> %s" % (name, len(d), span, mdp))

if __name__ == "__main__":
    main()
