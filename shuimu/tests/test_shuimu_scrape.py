#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "shuimu-scrape.py"
SPEC = importlib.util.spec_from_file_location("shuimu_scrape", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


SEARCH_HTML = """
<html><body>
  <a href="/nForum/article/Stock/123">关于市场的讨论</a>
  <a href="/nForum/article/Stock/456?p=1">另一主题</a>
  <a href="?p=2">2</a>
</body></html>
"""

ARTICLE_HTML = """
<html><head><title>关于市场的讨论</title></head><body>
<div class="post">
  <div>楼主</div>
  <div>发信人: Icestone (冰石), 信区: Stock</div>
  <div>标 题: 关于市场的讨论</div>
  <div>发信站: 水木社区 (Mon Jan 02 12:34:56 2023), 站内</div>
  <div>这是作者的正文。</div>
  <div>第二行。</div>
  <div>--</div>
</div>
<div class="post">
  <div>第1楼</div>
  <div>发信人: OtherUser, 信区: Stock</div>
  <div>标 题: Re: 关于市场的讨论</div>
  <div>发信站: 水木社区 (Mon Jan 02 13:00:00 2023), 站内</div>
  <div>其他人的回复。</div>
  <div>--</div>
</div>
</body></html>
"""


class FakeResponse:
    def __init__(self, content):
        self.content = content.encode("utf-8")


class FakeClient:
    base_url = "https://example.test"

    def get(self, path, params=None):
        if path == "/nForum/s/article":
            page = (params or {}).get("p", 1)
            return FakeResponse(SEARCH_HTML if page == 1 else "<html><body></body></html>")
        return FakeResponse(ARTICLE_HTML)


class ScraperTests(unittest.TestCase):
    def test_render_terminal_screen_applies_cursor_overwrites(self):
        raw = "\x1b[2J\x1b[2;1H1264092 * Icestone Re: 今日开仓地产\x1b[1;1H旧标题"
        rendered = MODULE.render_terminal_screen(raw)
        self.assertIn("旧标题", rendered)
        self.assertIn("1264092 * Icestone", rendered)
        self.assertEqual(
            MODULE.TelnetArchiveSession.selected_article_id(rendered.replace("1264092", "> 1264092"), "Icestone"),
            "1264092",
        )

    def test_resolve_short_telnet_row_to_real_article_id(self):
        screen = """
1263375 * beinghalf     Re: 创新药爆发是能预料到的
>      79   Icestone      Re: 创新药爆发是能预料到的
1263380 * Ermia          铭普光磁
时间[Aug 10 20:46] 总人数[ 285279 ]
"""
        self.assertEqual(
            MODULE.TelnetArchiveSession.resolve_article_id(screen, "79", "Icestone"),
            "1263379",
        )
        self.assertEqual(
            MODULE.TelnetArchiveSession.resolve_article_id(screen, "19381", "Icestone"),
            "",
        )

    def test_discover_threads_and_filter_board(self):
        result = MODULE.discover_threads(FakeClient(), "Icestone", "Stock", None, None)
        self.assertEqual(sorted(result), ["Stock/123", "Stock/456"])

    def test_parse_article_page_extracts_author_and_content(self):
        response = FakeResponse(ARTICLE_HTML)
        title, posts, max_page = MODULE.parse_article_page(
            response, "https://example.test/nForum/article/Stock/123", "Icestone"
        )
        self.assertEqual(title, "关于市场的讨论")
        self.assertEqual(max_page, 1)
        self.assertEqual(len(posts), 2)
        self.assertTrue(posts[0]["is_target"])
        self.assertEqual(posts[0]["floor"], 0)
        self.assertIn("这是作者的正文。", posts[0]["content"])
        self.assertFalse(posts[1]["is_target"])

    def test_render_markdown_marks_target_author(self):
        report = {
            "query": {"board": "Stock", "author": "Icestone"},
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "stats": {"target_posts": 1},
            "threads": [
                {
                    "board": "Stock",
                    "thread_id": "123",
                    "title": "关于市场的讨论",
                    "url": "https://example.test/nForum/article/Stock/123",
                    "target_posts": 1,
                    "posts": [
                        {
                            "floor": 0,
                            "author": "Icestone",
                            "time": "2023-01-02",
                            "content": "正文",
                            "is_target": True,
                        }
                    ],
                }
            ],
        }
        output = MODULE.render_markdown(report)
        self.assertIn("目标作者", output)
        self.assertIn("正文", output)

    def test_parse_telnet_article_extracts_body_without_footer(self):
        screen = """
发信人: Icestone (冰石), 信区: Stock
标 题: Re: 测试主题
发信站: 水木社区 (Sun Aug  9 15:26:16 2026), 站内
这是 Telnet 正文。

※ 来源:·水木社区
[阅读文章] 回信 R │ 结束 Q
"""
        post = MODULE.parse_telnet_article(screen, "Stock", "1263417", "Icestone")
        self.assertIsNotNone(post)
        assert post is not None
        self.assertTrue(post["is_target"])
        self.assertEqual(post["date"], "2026-08-09")
        self.assertEqual(post["content"], "这是 Telnet 正文。")

    def test_author_article_ids_reads_all_rows_from_ctrl_g5_page(self):
        screen = """
Ctrl-G 5：搜索作者 Icestone 的文章
1263996  Re: 怒亏 66w                         Icestone
1263987  Re: 怒亏 66w                         Icestone
1263911  Re: T出四蹈利润                      Icestone
"""
        self.assertEqual(
            MODULE.TelnetArchiveSession.author_article_ids(screen, "Icestone"),
            ["1263996", "1263987", "1263911"],
        )

    def test_render_markdown_handles_unknown_telnet_floor(self):
        report = {
            "query": {"board": "Stock", "author": "Icestone"},
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "stats": {"target_posts": 1},
            "threads": [{
                "board": "Stock", "thread_id": "123", "title": "主题",
                "url": "https://example.test", "target_posts": 1, "posts": [{
                    "floor": None, "author": "Icestone", "time": "",
                    "content": "正文", "is_target": True,
                }],
            }],
        }
        self.assertIn("楼层未标记", MODULE.render_markdown(report))

    def test_extract_image_urls_and_telnet_image_field(self):
        urls = MODULE.extract_image_urls(
            "图片 https://att.newsmth.net/att/abc123.jpg，普通链接 https://example.test/page"
        )
        self.assertEqual(urls, ["https://att.newsmth.net/att/abc123.jpg"])
        screen = """
发信人: Icestone, 信区: Stock
标 题: 图片测试
发信站: 水木社区 (Sun Aug  9 15:26:16 2026), 站内
https://images.newsmth.net/att/abc123.png
※ 来源:·水木社区
"""
        post = MODULE.parse_telnet_article(screen, "Stock", "123", "Icestone")
        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post["image_urls"], ["https://images.newsmth.net/att/abc123.png"])


if __name__ == "__main__":
    unittest.main()
