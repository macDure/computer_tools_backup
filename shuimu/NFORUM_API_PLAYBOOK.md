# 水木 Stock 高速爬（nForum JSON API + HTTP Basic）方法文档

> 定稿: 2026-09-11 12:35 北京时间 | 状态: **已收官并固化**
> 代码基线: 本目录 git 仓库 `shuimu_daily`（commit 见 `git log`）；数据归档仓 `/opt/data/shuimu_daily/`（git，`shuimu-bot` 身份）
> 本文所有性能数字均为 09-11 当日实测（A 级证据，日志在 `logs/nf_crawler.log`）

---

## 1. 一句话总结

水木桌面站（www.newsmth.net，nForum 程序）带一套完整 JSON API，**用账号密码做 HTTP Basic 认证即可全速读取**：
24 分钟、1281 次请求、零失败，一次补完 34 个 4 小时窗 / 686 个主题 / 4.3 万行归档（telnet 旧法同等工作量需 2-3 天）。

## 2. 结论演进（为什么最终是 Basic 认证）

| 阶段 | 方案 | 结局 | 证据 |
|---|---|---|---|
| 09-03~09-10 | telnet raw socket 慢速爬 | 账号级限流/惩罚窗口，补爬 38 窗排了 2 天还只完成 2 窗 | 历史日志 |
| 09-11 早 | 程序化登录（HTTP POST ajax_login） | **死路**：生产版强制 geetest v4 滑块（空 captcha → code=1103），不碰滑块是账号安全纪律 | 实测 |
| 09-11 上午 | keyring 解密 Chrome cookie | **死路**：v11 cookie AES-128-CBC，密钥派生矩阵穷尽全部失败 | get_ck.py~debug_decrypt4.py |
| 09-11 上午 | CDP 读浏览器 cookie 喂 API | **方向错误**：nForum API 根本不读 cookie 会话 | 401 响应头 `WWW-Authenticate: Basic realm="nForum API"` |
| 09-11 中午 | **HTTP Basic 认证** | **正路**：源码 `basic_auth.php` 只认 `PHP_AUTH_USER/PW`+`checkPwd`；实测 200 返回真实数据 | /tmp/nforum-src + 实测 |

关键认知：**浏览器 UI 登录（cookie 会话）与 API 认证（Basic）是两套完全独立的机制**。
"浏览器显示欢迎 macp 但 API 401"是正常现象，不是 cookie 没拷全。
凭据直接用 `/host-home/.config/newsmth/credentials`（只读，`username=`/`password=` 两行，值不落日志/不落屏）。

## 3. API 参考（实测验证过的端点）

Base: `https://www.newsmth.net/nForum/api`
请求头必须带: `Authorization: Basic <base64(user:pass)>` + 正常浏览器 UA + `Referer: https://www.newsmth.net/nForum/board/Stock`

| 端点 | 用途 | 响应结构（**扁平，无 data 包装**） |
|---|---|---|
| `GET /board/index/Stock.json?count=50&page=N` | 版面列表，翻页 | 顶层 `article[]`：`id`, `group_id`, `title`, `post_time`(首帖), `last_reply_time`(flush), `is_top`, `user.user_name` |
| `GET /threads/Stock/<gid>.json?count=50&page=1` | 整串全部楼层（一次拿全） | 顶层 `article[]`（按楼层序，第一楼=首帖）：`post_time`, `content`(全文), `user.user_name`, 顶层另有 `last_reply_time` |
| `GET /article/Stock/<aid>.json` | 单帖全文 | 同上单条；爬虫不依赖（threads 已含全文） |

注意：
- 路径必须带 `.json` 后缀，否则返回 "Unknow Return Format"
- **mode=2** 时列表按最后回复时间倒序（与 telnet 列表同语义）——`?count=50&page=N` 默认即此序
- 时间字段是 `2026-09-09 08:23:45` 字符串（北京时间），代码兼容 epoch 秒/毫秒
- **只读纪律：只用上述只读端点；API 里还有 publish/reply/delete 等写接口，一律不碰**

### 错误处理（实测行为）

| 现象 | 含义 | 处理 |
|---|---|---|
| HTTP 401 | 凭据错 | 终止（exit 2），看门狗 15min 冷却后重试 |
| HTTP 200 + `code=0102` "账号过多" | **BBS 在线登录槽被浏览器会话占满**（普通账号并发槽位很小） | 退避 30s×3 重试；根治=让用户在浏览器点"退出登录"释放槽位；看门狗会飞书提示 |
| HTTP 200 + 其他 `code` | 业务拒绝 | 记日志终止 |
| 网络异常 | 超时等 | 单请求重试 3 次（3s/6s 退避） |

## 4. 已踩的坑（全部实测，代码里已修）

1. **置顶帖 `last_reply_time` 恒为 2026-06-12**（极旧假时间戳）→ 翻页截止判定必须 `is_top` 跳过，否则第 1 页就假停。
2. **响应是扁平结构**：顶层直接 `article[]`，不是源码里看到的 `data.article`（开源版与生产版有差异）。
3. **作者字段是 `user.user_name`**，不是 `user.name`。
4. **threads 接口一次返回全串全部楼层**（实测 10 楼层完整 content），不需要逐楼 article 接口——这是高速的关键。
5. **限速仍必须**：API 虽快，请求间 0.6~1.6s 随机（`random.uniform`），24 分钟 1281 请求零风控命中；不要贪快。
6. **0102 与爬取互斥**：爬取期间用户浏览器别登录水木，否则槽位被占。

## 5. 系统架构

```
cron e2598086c5b3 (*/2 * * * *, no_agent)
    │ 每 2 分钟
    ▼
auto_pipeline.py  ← 看门狗状态机 (.auto_state.json: idle/running, 成功后回 idle 值守)
    │ idle:    冷却中/无 pending -> 静默
    │          有 pending: verify_api() 内联 Basic 验 API
    │           ├─ 200      → Popen nf_crawler.py → running → 飞书"开跑"
    │           ├─ 0102     → 飞书"请退出浏览器登录" → 下轮重试
    │           └─ 其他失败 → bump_fail() (3 连败 6h 冷却) + 飞书(15min 冷却)
    │ running: pid 活着 → 静默; 死了 → 读日志判"=== 完成" → 汇总飞书 → 回 idle
    │
cron 153e69eff3de (16:20 UTC = 北京 00:20, no_agent)
    ▼
queue_add_windows.py  ← 每日增量入队: 昨天 6 个 4h 窗加入队列 (幂等:
                         已 done / 归档已有 nf_api / 窗未结束 都跳过)
                         → 看门狗下一 tick 见 pending 自动开爬 (全自治)
    ▼
nf_crawler.py  ← 爬虫本体 (动态截止: 默认=最早 pending 窗起点, 无 pending=今天 00:00)
    1) 列表遍: board/index 翻页到 last_reply_time <= 截止 (~40s/27页, 只扫一遍)
    2) 列表级预筛: 只拉首帖命中 pending 窗的串全文 (日增量=个位数请求)
    3) 归档:   /opt/data/shuimu_daily/年/月/日/wHH/ {meta.json, 原帖_Stock.md}
              (同模式 nf_api 覆盖不备份; 异模式 telnet 旧档先 .bak_nf 备份)
    4) 空窗复核: 完整覆盖且零命中的窗自动标 done (note=empty_window_verified)
    5) 队列:   backfill_queue.json 命中标 done
    6) git:    cd /opt/data/shuimu_daily && git add -A && commit
```

飞书直发一律走 `deliver_feishu.py`（绕开 cron live-adapter 静默失败缺陷 #47056），
看门狗 stdout 恒为空（no_agent 纪律：stdout 非空=给用户的消息）。

### 文件清单（核心，已在 git 基线）

| 文件 | 行数 | 职责 |
|---|---|---|
| `nf_crawler.py` | ~400 | 爬虫本体（Basic 认证 + 动态截止 + 列表级预筛 + 空窗复核） |
| `auto_pipeline.py` | ~300 | 看门狗状态机（队列感知，成功后回 idle 值守） |
| `queue_add_windows.py` | ~115 | 每日增量入队（幂等，cron 153e69eff3de 北京 00:20） |
| `deliver_feishu.py` | 99 | 飞书直发（chat_id 硬编码，凭据 /opt/data/.env） |
| `backfill_queue.json` | - | 4h 窗队列（40 窗，08-31~09-09，含 done/pending 状态） |
| `nf_dryrun.py` | 102 | 离线全流程演练（mock 网络，改完爬虫先跑它） |
| `NFORUM_API_PLAYBOOK.md` | - | 本文档 |

运行环境: `/opt/data/venvs/scrapling/bin/python`（scrapling FetcherSession，`impersonate="chrome"`）。
日志: `logs/nf_crawler.log`（爬虫）、`logs/auto_pipeline.log`（看门狗）。
退役留档（git 已 ignore）: cdp_*.py, login_*.py, get_ck*.py, debug_decrypt*.py, spike_*.py 等探索期脚本。

## 6. 性能基线（09-11 12:08:53 → 12:33:03 实测）

| 指标 | 数值 |
|---|---|
| 总耗时 | **24 分 10 秒** |
| 请求总数 | 1281 次（列表 27 + 全文 ~1254），**0 失败 0 风控** |
| 列表遍 | 27 页 / 1344 串 / ~40 秒 |
| 全文遍 | 1254 候选串 / 平均 ~1.1s/串 |
| 产出 | 34 个 4h 窗 / 686 主题 / 70 文件 / 43158 行（git commit `0de13df`） |
| 归档样例 | 2026/09/09/w12 = 51 主题 / 289 帖（meta.json `complete:true`） |
| 队列终态 | 40 窗中 36 done；剩 4 个 w00（00:00-04:00）pending → **13:28 看门狗自动复核轮**（见下） |

### 复核轮（09-11 13:28:04 → 13:30:05，每日增量机制首次实战）

| 指标 | 数值 |
|---|---|
| 触发 | 看门狗 done→idle 队列感知，见 4 pending 自动拉起（无人工干预） |
| 列表遍 | 27 页（截止推到 2026-08-31 00:00，覆盖 4 个凌晨窗） |
| 结论 | 4 个 w00 窗全部**真空窗**（列表全量扫过零命中），标 `done` + `note=empty_window_verified`（任务内容保留，非删除） |
| 飞书 | 13:28:04 开跑 + 13:30:05 完成，两条自动直发 |

## 7. 运维手册

### 7.1 每日增量（默认模式，全自动）

每天北京 00:20 `queue_add_windows.py` 把昨天 6 个 4h 窗入队 → 看门狗 ≤2min 内
见 pending 自动开爬（列表一遍 ~40s + 只拉命中窗的串全文，通常 <10 个请求）→
归档 + git + 飞书汇报 → 回 idle 值守。**无需人工干预**。
手动补某天: `/opt/data/venvs/scrapling/bin/python queue_add_windows.py --date 2026-09-10`
（幂等：已 done / 归档已有 nf_api / 未结束的窗都自动跳过）。

### 7.2 再爬一轮 / 补爬（手动）

```bash
cd /opt/data/scripts/shuimu_daily
# 把要补的窗 status 改 pending (backfill_queue.json, label 格式 "YYYY-MM-DD HH:00-HH:00")
# 爬虫截止自动 = 最早 pending 窗起点, 无需改代码; 也可 --stop-time 手动指定
# 看门狗下一 tick (≤2min) 自动开爬, 或手动:
/opt/data/venvs/scrapling/bin/python auto_pipeline.py
```

### 7.3 手动跑爬虫（不看门狗）

```bash
/opt/data/venvs/scrapling/bin/python nf_crawler.py            # 全量(写归档+git)
/opt/data/venvs/scrapling/bin/python nf_crawler.py --dry-run  # 只统计不落盘
/opt/data/venvs/scrapling/bin/python nf_crawler.py --list-only # 只列表遍(调试)
/opt/data/venvs/scrapling/bin/python nf_crawler.py --stop-time "2026-09-01 00:00:00"
```

### 7.4 排障速查

| 症状 | 诊断 | 处理 |
|---|---|---|
| 飞书"登录槽满" | 用户浏览器登录了水木占槽 | 用户浏览器点"退出登录"，2 分钟内看门狗自动恢复 |
| 飞书"API 验证失败 401" | 凭据文件被改/密码改了 | 核对 `/host-home/.config/newsmth/credentials` |
| 爬虫卡住不动 | `tail -f logs/nf_crawler.log` 看最后请求时间 | 单请求 30s 超时+重试 3 次，>3min 无日志才 kill |
| 改完代码想先验 | `nf_dryrun.py`（mock 网络）+ `--list-only` 真跑列表遍 | 全绿再全量 |
| 归档覆盖保护 | 目标窗目录已存在时自动 `.bak_nf_<ts>` 备份 | 备份可删，先 diff |

### 7.4 验证清单（每轮收官必查）

1. `tail logs/nf_crawler.log` 有 `=== 完成: 请求 N 次 ===`
2. `.auto_state.json` state=done
3. 归档仓 `git log -1` 有新 commit；`git show --stat` 文件数=2×窗数
4. 抽 1 个窗: `meta.json` 的 thread_count 与 `原帖_Stock.md` 的 `## ` 计数一致
5. 队列 `pending` 数符合预期（空窗除外，空窗特征=该时段列表无命中）

## 8. 安全纪律（不可违背）

1. 凭据文件**只读**，绝不删改；密码值不落日志/飞书/文档/对话
2. 只调只读端点（board/index, threads），写接口一律不碰
3. 限速 0.6-1.6s 随机，不贪快（账号风控 > 爬取速度）
4. 不碰 geetest 滑块（程序化登录=死路+风控风险）
5. 归档不静默覆盖：已有目录先备份
6. 爬虫与浏览器登录互斥（0102），爬取期间别动浏览器水木登录

## 9. 扩展（现状）

- **帖子附件/图片下载：已接入（09-11 16:56 自测 9/9 PASS）**
  - **关键坑**：API `threads` 返回的 `attachment.file[].url` 是 **web 路由** `/attachment/Stock/<aid>/<pos>`，匿名/Basic 访问一律 404（web controller 有 XWJOKE cookie 检查）。
  - **正确路由**（源码 `app/plugins/api/controllers/attachment_controller.php` + `wrapper.php:141` 实证）：
    `GET https://www.newsmth.net/nForum/api/attachment/Stock/<article_id>/<pos>` + **Basic 认证即可**（API controller 无 cookie 检查，只查 `hasReadPerm`）。
    `<article_id>` 取 `file.url` 倒数第二段（⚠️ 回复楼的 article_id ≠ 主题 gid！如主题 gid=11577361，24 楼附件 url 是 `11582553/494`）。
  - 归档落点：`<窗目录>/attachments/<article_id>_<文件名>`；`原帖_Stock.md` 每帖下加 `📎 附件: 名字 (大小) -> attachments/...` 行；meta.json 加 `attachment_count`。
  - 集成函数：`nf_crawler.posts_from_api()`（解析附件）/ `download_bucket_attachments()`（幂等下载，已存在非空跳过）；自测 `_img_selftest.py`（真实代码路径端到端：找图串→全楼→归档→下载→魔数+sha256+md 一致性验证）。
  - 限速沿用 `nf._gap()`（0.6-1.6s/附件）；`has_attachment` 布尔字段可预筛带图串。
- **每日增量 cron：已接入（09-11）** — 见 7.1；cron `153e69eff3de`（北京 00:20 入队）
  + `e2598086c5b3`（*/2 看门狗）构成全自动日归档闭环。
- **多版扩展（未实现）**：BOARD 变量 + 队列文件参数化即可复制到 Fund/GlobalStocks 等版。
- **WAP API 交叉对账（未实现）**：wap.newsmth.net 匿名只读端点（见 skill 水木 WAP 章节）
  可对帖子数/标题做双源验证。

## 10. 相关索引

- Skill: `shuimu-bbs-telnet`（telnet 铁律 15 条 + WAP API 全端点 + Chrome/CDP 坑全记录）
- 归档仓: `/opt/data/shuimu_daily/`（年/月/日/wHH/，git 可回溯，含 telnet 时代旧数据）
- 看门狗 cron: `e2598086c5b3`（`*/2 * * * *` no_agent）
- nForum 源码: github.com/fancyrabbit/nForum（生产版有差异，以实测为准）
