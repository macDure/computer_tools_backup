#!/usr/bin/env python3
"""extract_author_topics.py — 按发帖人提取, 按主题分文件夹 (09-12 Icestone 指令)

数据源: <归档根>/<YYYY>/<MM>/<DD>/<slot>/原帖_Stock.md (全量 md 解析, 覆盖 v1/v2/bak/旧批次窗;
       改名期/重爬前的帖只存在于 md, 比 meta v2 更全)
结构: <out>/<人名>/<主题slug>.md + meta.json
每主题文件 = 该人在该主题内的全部帖子(按时间升序), 正文内 📎 附件行转为可渲染图片引用
账号合并: --alias 可重复 (Icestone 账号两种署名: 'Icestone (减肥的小野猪)' + '减肥的小野猪')
去重: 同 (时间, 正文sha1) 跨窗只留一份; 同时间不同正文 = 不同帖, 都留
用法:
  python3 extract_author_topics.py --name Icestone \
      --alias 'Icestone (减肥的小野猪)' --alias '减肥的小野猪' \
      --year 2026 --out /tmp/icestone_topics \
      [--arch /path/to/stock_research_mac/shuimu/帖子]
  图片链接按最终放置目录 shuimu/<人名>/ 计算: ../帖子/<YYYY>/MM/DD/wHH/attachments/<file>
  换机运行时 --arch 指向本仓库的 shuimu/帖子 目录即可 (默认 stock_research_mac/shuimu/帖子)。
"""
import os, re, json, hashlib, argparse

IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

thread_re = re.compile(r"^## (\d+)\. (.+)$")
post_re   = re.compile(r"^### \[(\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+?)\s*$")
att_line_re = re.compile(r"^📎 附件: (.+?) \(.*?\) -> `attachments/([^`]+)`")
gen_re    = re.compile(r"生成时间 \(北京\): (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

def slugify(title, i):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", title or "(无题)").strip()
    s = re.sub(r"\s+", " ", s)[:60]
    return s or ("topic_%04d" % i)

def parse_windows(arch, year, authors):
    """扫归档根下全年原帖 md, yield (ts, title, win_rel, gen, content, atts)
    atts: [(原名, 存档名)]"""
    base = os.path.join(arch, str(year))
    if not os.path.isdir(base):
        return
    for mm in sorted(os.listdir(base)):
        dp = os.path.join(base, mm)
        if not os.path.isdir(dp):
            continue
        for day in sorted(os.listdir(dp)):
            dpath = os.path.join(dp, day)
            if not os.path.isdir(dpath):
                continue
            for slot in sorted(os.listdir(dpath)):
                fp = os.path.join(dpath, slot, "原帖_Stock.md")
                if not os.path.isfile(fp):
                    continue
                win_rel = "%s/%s/%s" % (mm, day, slot)
                lines = open(fp, encoding="utf-8").read().split("\n")
                gm = gen_re.search("\n".join(lines[:8]))
                gen = gm.group(1) if gm else ""
                cur_title = None
                i, n = 0, len(lines)
                while i < n:
                    m = thread_re.match(lines[i])
                    if m:
                        cur_title = m.group(2).strip()
                        i += 1
                        continue
                    m = post_re.match(lines[i])
                    if m and cur_title is not None:
                        ts, author = m.groups()
                        if author.strip() in authors:
                            j = i + 1
                            block = []
                            while j < n:
                                l2 = lines[j]
                                if post_re.match(l2) or thread_re.match(l2) or l2.strip() == "---":
                                    break
                                block.append(l2)
                                j += 1
                            while block and not block[-1].strip():
                                block.pop()
                            while block and not block[0].strip():
                                block.pop(0)
                            body, atts = [], []
                            for l in block:
                                ma = att_line_re.match(l.strip())
                                if ma:
                                    atts.append((ma.group(1), ma.group(2)))
                                else:
                                    body.append(l)
                            yield ts, cur_title, win_rel, gen, "\n".join(body), atts
                            i = j
                            continue
                    i += 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="输出文件夹名 (人名)")
    ap.add_argument("--alias", action="append", default=[], help="署名变体, 可多次")
    ap.add_argument("--year", default="2026")
    ap.add_argument("--out", required=True)
    ap.add_argument("--arch", default=os.path.join(os.getcwd(), "shuimu", "帖子"),
                    help="归档根 (含 <YYYY>/<MM>/<DD>/<slot>/), 默认 ./shuimu/帖子")
    a = ap.parse_args()
    authors = set(a.alias)

    # 去重: (ts, 正文sha1) -> 留 gen 最新的窗版本
    posts = {}
    for ts, title, win, gen, content, atts in parse_windows(a.arch, a.year, authors):
        k = (ts, hashlib.sha1(content.encode()).hexdigest())
        old = posts.get(k)
        if old is None or gen > old[3]:
            posts[k] = (ts, title, win, gen, content, atts)

    plist = sorted(posts.values(), key=lambda p: (p[0], p[1]))
    topics = {}
    for p in plist:
        topics.setdefault(p[1], []).append(p)

    out_dir = os.path.join(a.out, a.name)
    os.makedirs(out_dir, exist_ok=True)
    used = {}
    meta_topics = []
    stat = {"atts": 0, "found": 0, "missing": 0}
    for i, (title, tposts) in enumerate(sorted(topics.items(), key=lambda kv: kv[1][0][0])):
        base = slugify(title, i)
        name, n = base, 1
        while name in used:
            n += 1
            name = "%s_v%d" % (base, n)
        used[name] = True
        fname = name + ".md"
        wins = sorted({p[2] for p in tposts})
        L = ["# %s" % title, ""]
        L.append("- 发帖人: %s" % a.name)
        L.append("- %s 在此主题 %d 条 (首 %s ~ 末 %s)" % (a.name, len(tposts), tposts[0][0], tposts[-1][0]))
        L.append("- 来源窗: %s" % ", ".join(wins))
        L.append("")
        for ts, t, win, gen, content, atts in tposts:
            L.append("## %s" % ts)
            L.append("")
            L.append(content or "(空)")
            for orig, stored in atts:
                stat["atts"] += 1
                rel = "../帖子/%s/%s/attachments/%s" % (a.year, win, stored)
                src = os.path.join(a.arch, a.year, win, "attachments", stored)
                if os.path.isfile(src):
                    stat["found"] += 1
                    if stored.lower().endswith(IMG_EXT):
                        L.append("")
                        L.append("![%s](%s)" % (orig, rel))
                    else:
                        L.append("")
                        L.append("📎 附件: %s -> `%s`" % (orig, rel))
                else:
                    stat["missing"] += 1
                    L.append("")
                    L.append("📎 附件(原窗缺失): %s" % orig)
            L.append("")
        open(os.path.join(out_dir, fname), "w", encoding="utf-8").write("\n".join(L))
        meta_topics.append({
            "title": title, "file": fname, "post_count": len(tposts),
            "first_time": tposts[0][0], "last_time": tposts[-1][0],
            "source_windows": wins,
        })
    meta = {"name": a.name, "aliases": sorted(authors), "year": int(a.year),
            "topic_count": len(meta_topics), "post_count": len(plist),
            "attachment_refs": stat,
            "time_span": [plist[0][0], plist[-1][0]] if plist else [],
            "topics": meta_topics}
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), ensure_ascii=False, indent=1)
    print("✅ %s: %d 主题 / %d 条帖子 (%s ~ %s) -> %s" % (
        a.name, len(meta_topics), len(plist),
        plist[0][0] if plist else "?", plist[-1][0] if plist else "?", out_dir))
    print("   附件引用 %d (可解析 %d / 原窗缺失 %d)" % (stat["atts"], stat["found"], stat["missing"]))

if __name__ == "__main__":
    main()
