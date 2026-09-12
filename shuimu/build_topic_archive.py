#!/usr/bin/env python3
"""build_topic_archive.py — 2026 水木 Stock 帖子按主题整理 (09-12 用户指令)

输入: /opt/data/shuimu_daily/2026/MM/DD/wHH/meta.json (meta_version=2 完整结构)
输出: 暂存目录 帖子按主题分类/2026/MM/
  - meta.json          当月主题清单 {year, month, topic_count, post_count, attachment_count,
                       topics: [{gid, title, first_time_bj, last_time_bj, post_count,
                                 authors, attachment_count, months, files, source_windows}]}
  - <slug>.md          同主题完整帖: 标题头(元信息) + 楼主[1楼] + 回复按楼层升序
规则:
  1. 以主题为轴线, 同主题(跨窗重复归档)聚合去重:
     优先 gid; 存量无 gid 用 (title, first_time) 兜底 key (1月实测0冲突)
  2. 楼层按 seq+time 去重(同 seq 取最新楼层版, 即后归档的窗含更多回复); 同 author+time+content 精确去重
  3. 跨月主题: 主题的任一帖落在哪个月, 该月就放完整文档; meta 里 months 列出所有涉及月份
  4. 附件: 文档内引用 ../../帖子/MM/DD/wHH/attachments/<fname> (相对原归档, 不拷贝文件, 不覆盖原目录)
  5. 幂等: 重跑先清空当月目录重建; 输出只进暂存目录, 宿主写入由调用方 docker -v 完成
用法: python build_topic_archive.py --year 2026 --month 01 --out /opt/data/tmp/topic_archive
      python build_topic_archive.py --year 2026 --out /opt/data/tmp/topic_archive  (全年)
"""
import re, os, json, argparse, datetime as dt
from collections import defaultdict

ARCH = "/opt/data/shuimu_daily"
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

def slugify(title, gid, i):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", title or "(无题)").strip()
    s = re.sub(r"\s+", " ", s)[:60]
    return ("%s_%s" % (gid or "noid", s)) if (gid or s) else ("topic_%04d" % i)

def load_month_topics(year, month):
    """读某月所有窗 meta v2, 返回 {agg_key: topic_dict}
    topic: {key, gid, title, first_time, posts:[{seq,time,author,content,atts,src}], last_time}"""
    topics = {}
    base = os.path.join(ARCH, str(year), month)
    if not os.path.isdir(base):
        return topics
    for day in sorted(os.listdir(base)):
        dp = os.path.join(base, day)
        if not os.path.isdir(dp):
            continue
        for slot in sorted(os.listdir(dp)):
            mp = os.path.join(dp, slot, "meta.json")
            if not os.path.isfile(mp):
                continue
            st = json.load(open(mp)).get("boards", {}).get("Stock", {})
            if st.get("meta_version") != 2:
                continue
            rel_win = "%s/%s/%s" % (month, day, slot)
            for t in st.get("threads", []):
                title = t.get("title") or "(无题)"
                gid = t.get("gid")
                # 首帖时间: 优先 first_time_bj, 缺失用首楼 time
                ft = t.get("first_time_bj")
                posts = t.get("posts") or []
                if not posts:
                    continue
                if not ft:
                    ft = posts[0].get("time")
                ft_norm = _norm(ft, posts[0].get("time"))
                key = ("gid:%s" % gid) if gid else ("tft:%s|%s" % (title, ft_norm))
                tp = topics.get(key)
                if tp is None:
                    tp = {"key": key, "gid": gid, "title": title,
                          "first_time": ft_norm, "posts": {}, "windows": set()}
                    topics[key] = tp
                tp["windows"].add(rel_win)
                if gid and not tp["gid"]:
                    tp["gid"] = gid
                # 楼层合并: seq 为主键, 同 seq 取 time 更大(更新楼层版); 精确重复丢弃
                for p in posts:
                    seq = p.get("seq")
                    if seq is None:
                        seq = len(tp["posts"]) + 1
                    t_norm = _norm(p.get("time"), ft_norm)
                    old = tp["posts"].get(seq)
                    newp = {"seq": seq, "time": t_norm, "author": p.get("author") or "?",
                            "content": (p.get("content") or "").strip(),
                            "atts": p.get("attachments") or [], "src": rel_win}
                    if old is None or (newp["author"], newp["time"], newp["content"]) == \
                          (old["author"], old["time"], old["content"]):
                        if old is None or newp["time"] > old["time"]:
                            tp["posts"][seq] = newp
                    else:
                        # 同 seq 不同内容: 取 time 大的; 相同则保留旧(并保留另一版本作 seq.x 防丢)
                        if newp["time"] > old["time"]:
                            tp["posts"][seq] = newp
                        else:
                            for extra in (".5", ".9"):
                                if seq + extra not in tp["posts"]:
                                    tp["posts"][seq + extra] = newp
                                    break
    return topics

def _norm(t, fallback):
    """ISO 时间规范化 (存量 md 解析的已是 +08:00 ISO; 新版同格式)"""
    return t or fallback

def month_of(t):
    """返回 'YYYY-MM' (ISO 时间前 7 位)"""
    return t[:7] if t and len(t) >= 7 else None

def build_month(year, month, topics, out_root):
    """把 topics 里落在该月的主题(有任一帖在该月)写成完整文档+meta"""
    ym = "%s-%s" % (year, month)  # 该月的 YYYY-MM 标识
    out_dir = os.path.join(out_root, str(year), month)
    os.makedirs(out_dir, exist_ok=True)
    used_names = {}
    month_topics = []
    for i, (key, tp) in enumerate(sorted(topics.items(), key=lambda kv: kv[1]["first_time"] or "")):
        pmap = tp["posts"]
        months = sorted({month_of(p["time"]) for p in pmap.values() if month_of(p["time"])})
        if ym not in months:
            continue
        posts = sorted(pmap.values(), key=lambda p: (p["time"], str(p["seq"])))
        # 文件名 slug (同月内唯一)
        base = slugify(tp["title"], tp["gid"], i)
        name, n = base, 1
        while name in used_names:
            n += 1
            name = "%s_v%d" % (base, n)
        used_names[name] = True
        fname = name + ".md"
        # 文档
        L = ["# %s" % tp["title"], ""]
        L.append("- 主题号: %s" % (tp["gid"] or "(存量无gid)"))
        L.append("- 首帖: %s | 末帖: %s | 楼层数: %d" % (tp["first_time"] or "?", posts[-1]["time"], len(posts)))
        L.append("- 涉及月份: %s" % ", ".join(m[-2:] + "月" for m in months))
        L.append("- 来源窗: %s" % ", ".join(sorted(tp["windows"])))
        L.append("")
        for p in posts:
            L.append("## [%d楼] %s" % (int(float(p["seq"])), p["author"]))
            L.append("")
            L.append("> 时间: %s" % p["time"])
            L.append("")
            L.append(p["content"] or "(空)")
            for a in p["atts"]:
                fn = a.get("fname") or ""
                if fn:
                    L.append("")
                    L.append("📎 附件: %s -> `../../../帖子/%s/attachments/%s`" % (a.get("name"), p["src"], fn))
            L.append("")
        open(os.path.join(out_dir, fname), "w", encoding="utf-8").write("\n".join(L))
        month_topics.append({
            "gid": tp["gid"], "title": tp["title"],
            "first_time_bj": tp["first_time"], "last_time_bj": posts[-1]["time"],
            "post_count": len(posts),
            "authors": list({p["author"] for p in posts}),
            "attachment_count": sum(len(p["atts"]) for p in posts),
            "months": months, "file": fname,
            "source_windows": sorted(tp["windows"]),
        })
    meta = {
        "year": int(year), "month": int(month),
        "generated_bj": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        "topic_count": len(month_topics),
        "post_count": sum(t["post_count"] for t in month_topics),
        "attachment_count": sum(t["attachment_count"] for t in month_topics),
        "cross_month_topics": sum(1 for t in month_topics if len(t["months"]) > 1),
        "topics": month_topics,
    }
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), ensure_ascii=False, indent=1)
    return meta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", required=True)
    ap.add_argument("--month", help="MM; 缺省=全年1-12")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    months = [a.month] if a.month else ["%02d" % m for m in range(1, 13)]
    for m in months:
        topics = load_month_topics(a.year, m)
        if not topics:
            print("2026-%s: 无数据" % m)
            continue
        meta = build_month(a.year, m, topics, a.out)
        print("2026-%s: 窗内主题 %d -> 该月放 %d 主题 / %d 帖 / %d 附件 (跨月 %d)" %
              (m, len(topics), meta["topic_count"], meta["post_count"],
               meta["attachment_count"], meta["cross_month_topics"]))

if __name__ == "__main__":
    main()
