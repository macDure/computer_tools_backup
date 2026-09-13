#!/usr/bin/env python3
# 临时测量脚本: 统计归档主题数 + 列表深翻能力探测
import glob, re, collections
ARCH = "/opt/data/shuimu_daily"
print("=== 各天主题数 (原帖_Stock.md) ===")
per_day = collections.Counter()
for f in glob.glob(ARCH + "/2026/*/*/*/原帖_Stock.md"):
    day = f.split("/")[-3]
    n = sum(1 for ln in open(f, encoding="utf-8") if ln.startswith("## "))
    per_day[day] += n
for d in sorted(per_day):
    print(d, per_day[d])
tot = sum(per_day.values())
days = len(per_day)
print("总主题(%d天): %d, 日均 %.0f" % (days, tot, tot / days if days else 0))

print("\n=== PAGE_COUNT ===")
src = open("/opt/data/scripts/shuimu_daily/nf_crawler.py", encoding="utf-8").read()
m = re.search(r"PAGE_COUNT\s*=\s*(\d+)", src)
print("PAGE_COUNT =", m.group(1) if m else "?")

ad = glob.glob(ARCH + "/2026/*/*/*/attachments")
print("attachments 目录:", len(ad))
