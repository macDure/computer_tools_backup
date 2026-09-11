#!/usr/bin/env python3
"""_img_selftest.py — 图片功能端到端自测 (走集成后的真实代码路径, 测试目录不动生产归档):
  1) 板列表找 has_attachment 串 (取 3 个)
  2) threads 拉全楼 -> posts_from_api (真实归档转换函数)
  3) write_archive 到测试目录 (真实归档函数, arch_root 指测试目录)
  4) download_bucket_attachments 下载全部附件 (真实下载函数)
  5) 验证: 每个附件文件存在 + 魔数 PNG/JPEG/GIF 正确 + md 里附件行齐全
  全过 = PASS; 任一失败 = FAIL + 详情
"""
import os, sys, hashlib, json, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nf_crawler as C

TEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_img_selftest_out")
MAGIC = {b"\x89PNG": "png", b"\xff\xd8": "jpeg", b"GIF8": "gif", b"RIFF": "webp"}

def verify(fn):
    head = open(fn, "rb").read(8)
    kind = next((v for k, v in MAGIC.items() if head.startswith(k)), None)
    size = os.path.getsize(fn)
    return (kind is not None and size > 500), kind, size

def main():
    import shutil
    shutil.rmtree(TEST, ignore_errors=True)
    os.makedirs(TEST, exist_ok=True)
    token = C.load_auth()
    nf = C.NF(token)
    # 1) 找带图串
    bl = nf.board_page(1)
    if not bl:
        print("FAIL: 板列表拉取失败"); return 1
    targets = [(a.get("group_id"), a.get("title")) for a in (bl.get("article") or []) if a.get("has_attachment")][:3]
    if not targets:
        print("FAIL: 首页无带图串"); nf.close(); return 1
    print("自测目标串: %d 个: %s" % (len(targets), [t[:15] for _, t in targets]))
    # 2) 全楼 + 真实转换函数
    tinfo = []
    for gid, title in targets:
        td = nf.threads(gid)
        if td is None:
            print("FAIL: gid %s 拉取失败" % gid); nf.close(); return 1
        posts = td.get("article") or []
        ft = C.parse_time(posts[0].get("post_time")) or dt.datetime.now(C.TZ)
        tinfo.append({"title": posts[0].get("title") or title, "first_time": ft, "gid": gid,
                      "posts": C.posts_from_api(posts, ft)})
    n_att = sum(len(p.get("attachments") or []) for t in tinfo for p in t["posts"])
    print("转换完成: %d 串 / %d 帖 / %d 附件" % (len(tinfo), sum(len(t['posts']) for t in tinfo), n_att))
    if n_att == 0:
        print("FAIL: 无附件可测"); nf.close(); return 1
    # 3) 真实归档函数 (测试目录)
    win_dir = os.path.join(TEST, "2026/09/11", "selftest")
    C.write_archive("2026/09/11", "selftest", "selftest 00:00-04:00", tinfo, arch_root=TEST)
    md = open(os.path.join(win_dir, "原帖_Stock.md")).read()
    n_md_att = md.count("📎 附件")
    print("md 生成: %d 个附件行 (期望 %d)" % (n_md_att, n_att))
    # 4) 真实下载函数
    ok, fail = C.download_bucket_attachments(nf, win_dir, tinfo)
    print("下载: ok=%d fail=%d" % (ok, fail))
    nf.close()
    # 5) 验证
    adir = os.path.join(win_dir, "attachments")
    files = sorted(os.listdir(adir)) if os.path.isdir(adir) else []
    print("落盘文件: %d 个" % len(files))
    bad = []
    for fn in files:
        p = os.path.join(adir, fn)
        good, kind, size = verify(p)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]
        print("  %-45s %6d bytes  %-5s sha256=%s  %s" % (fn[:45], size, kind or "UNKNOWN", h, "✅" if good else "❌"))
        if not good: bad.append(fn)
    # md 与落盘一致性
    md_refs = set(__import__("re").findall(r"attachments/(\S+?)`", md))
    missing_in_md = [f for f in files if f not in md_refs]
    print("md 引用与落盘一致性: %d 落盘 vs %d 引用, md缺失=%s" % (len(files), len(md_refs), missing_in_md or "无"))
    # 判定
    pass_all = (fail == 0 and not bad and n_md_att == n_att and not missing_in_md and len(files) == n_att)
    print("=" * 50)
    print("结果: %s  (附件 %d, 下载 ok %d / fail %d, 落盘 %d, md 行 %d)" % (
        "✅ PASS" if pass_all else "❌ FAIL", n_att, ok, fail, len(files), n_md_att))
    return 0 if pass_all else 1

if __name__ == "__main__":
    sys.exit(main())
