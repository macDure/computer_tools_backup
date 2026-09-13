#!/usr/bin/env python3
# 回补探针 v2: 量出「翻到 last_reply_time < 目标 需要多少页」— 决定 2026/2025 回补可行性
import sys, datetime as dt
sys.path.insert(0, "/opt/data/scripts/shuimu_daily")
import nf_crawler as C

TZ = dt.timezone(dt.timedelta(hours=8))
def log(m):
    print("[%s] %s" % (dt.datetime.now(TZ).strftime("%H:%M:%S"), m), flush=True)

GOALS = {
    "2025-12-31 20:00": dt.datetime(2025, 12, 31, 20, 0, tzinfo=TZ),   # 2026 回补终点 (09-11 w12 之前)
    "2025-01-01 00:00": dt.datetime(2025, 1, 1, 0, 0, tzinfo=TZ),      # 2025 回补终点
}
ck = C.load_auth()
assert ck, "凭据不可读"
nf = C.NF(ck)
log("认证 OK, 深翻测深度 (目标: 页内最老 flush 到达 2025-01-01, 或 5000 页封顶)")

page = 1
hits = {}
sample = None   # (gid, 首帖时间, 楼层数, 附件测试结果)
while page <= 5000:
    d = nf.board_page(page)
    if nf.unauth:
        log("!!! 登录态失效 page=%d" % page); sys.exit(2)
    if d is None:
        log("!!! page=%d 连续失败 — API 分页上限/风控" % page); break
    arts = [a for a in (d.get("article") or []) if not a.get("is_top")]
    if not arts:
        log("!!! page=%d 空页 — 列表到底" % page); break
    flushes = []
    for a in arts:
        lt = C.parse_time(a.get("last_reply_time")) or C.parse_time(a.get("post_time"))
        if lt: flushes.append(lt)
    if not flushes:
        page += 1; continue
    pg_min = min(flushes)
    if page == 1 or page % 100 == 0:
        log("page %d: 页内最老 flush=%s, 请求累计 %d" % (page, pg_min.strftime("%Y-%m-%d %H:%M"), nf.n))
    for name, g in list(GOALS.items()):
        if name not in hits and pg_min <= g:
            hits[name] = (page, pg_min)
            log(">>> 到达 %s @ page=%d (最老 flush=%s)" % (name, page, pg_min.strftime("%Y-%m-%d %H:%M")))
    # 抓一个 2025 年老帖验证 threads + 附件路由 (只测一次)
    if sample is None and "2025-01-01 00:00" in hits:
        for a in arts:
            ft = C.parse_time(a.get("post_time"))
            if ft and ft < dt.datetime(2026, 1, 1, tzinfo=TZ):
                gid = str(a.get("group_id") or a.get("id"))
                td = nf.threads(gid)
                posts = (td or {}).get("article") or []
                if posts:
                    att = "无附件"
                    for p in posts[:8]:
                        for f in ((p.get("attachment") or {}).get("file") or []):
                            u = (f.get("url") or "").rstrip("/").split("/")
                            if len(u) >= 3 and u[-1].isdigit():
                                api_url = C.BASE + "/attachment/" + "/".join(u[-3:])
                                r = nf.s.get(api_url, headers=nf.h, timeout=60)
                                att = "附件HTTP %d, %d bytes" % (r.status, len(r.body) if r.body else 0)
                                break
                        if att != "无附件": break
                    sample = (gid, ft.strftime("%Y-%m-%d"), len(posts), att)
                    break
    if all(g in hits for g in GOALS):
        log("两个目标都到达, 结束"); break
    page += 1
nf.close()
log("=== 结果 ===")
for name in GOALS:
    h = hits.get(name)
    log("%s -> page=%d" % (name, h[0]) if h else "%s -> 未达到(5000页/列表到底)" % name)
log("2025 老帖全文+附件验证: %s" % (list(sample) if sample else "未测到"))
log("总请求 %d, 到达 page=%d" % (nf.n, page - 1))
