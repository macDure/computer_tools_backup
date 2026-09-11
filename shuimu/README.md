# 水木股版 (Stock) 爬虫工具包 · 部署与使用说明

> 备份日期: 2026-09-11 | 工具版本: API 高速爬 v1 (scrapling 0.4.15 实测)
> 本目录是**可移植工具备份**: 按本文档操作, 可在任何 Ubuntu (x86_64) 机器上从零跑起水木股版爬虫, 产出与本机一致的归档文档 (含图片附件)。
>
> 爬取结果帖子数据**不在本目录**: 本机生产环境每轮爬完自动发布到 /home/mac/macperson/stock_research_mac/shuimu/帖子/ (git commit + push 远端, 由 auto_pipeline.py 调 publish_posts.sh 完成)。

---

## 一、这套工具是什么

通过水木社区 (newsmth.net) 的 **nForum JSON API** + **HTTP Basic 认证** 抓取股版 (BBS_Stock) 帖子, 替代旧 telnet 爬法:

| 对比项 | 旧 telnet 法 | 本工具 (API 法) |
|---|---|---|
| 30 天窗回补 | 2-3 天 | ~30 分钟 (1358 请求 0 失败实测) |
| 依赖 | 原始 socket + GBK 解析 + 屏显状态机 | 纯 HTTP JSON |
| 风控 | 频繁被踢 | TLS 指纹模拟 (Chrome), 限速 0.6-1.6s |
| 图片附件 | 不支持 | 自动下载原图 (PNG/JPEG) |

**核心原理 (为什么过风控)**: 水木 API 本身不加密、不需要 cookie, 但服务器对**非浏览器 TLS 指纹**的客户端有风控。本工具用 Scrapling 的 `FetcherSession(impersonate="chrome")` (底层 curl_cffi 精确模拟 Chrome 的 TLS/JA3 指纹), 配合 HTTP Basic 认证 (用户名密码直接编码进请求头), 即可稳定抓取, **不需要浏览器、不需要登录、不需要 cookie**。

## 二、目录结构

```
shuimu/
├── README.md              # 本文件 (部署+使用总入口)
├── requirements.txt       # Python 依赖 (一个包: scrapling[fetchers])
├── install.sh             # 一键安装 (Ubuntu 22.04/24.04)
├── credentials            # 水木账号模板 (需替换成你自己的账号, 勿提交 git!)
├── nf_crawler.py          # ★ 主爬虫: 列表遍->候选筛选->全文遍->归档->附件下载->git
├── auto_pipeline.py       # 看门狗: idle/running 状态机, 自动开爬+汇报 (生产用, 手动可跳过)
├── queue_add_windows.py   # 每日增量入队 (自动加"已结束且未爬"的 2h 窗, 幂等)
├── _img_selftest.py       # 图片下载功能端到端自测 (换机后验证环境用)
├── make_queue.py          # 区间队列生成器 (造 backfill_queue.json, 见 4.1)
├── deliver_feishu.py      # 飞书消息直发 (可选, 需要飞书应用 token; 不用飞书可删)
├── NFORUM_API_PLAYBOOK.md # ★ API 完整操作手册: 端点/字段/坑/附件下载路由/风控
├── publish_posts.sh       # 发布器: 归档 → stock_research_mac/shuimu/帖子 + commit + push (本机生产自动调用)
└── archive/               # (运行后自动生成) 归档仓, 建议 git init
    └── 2026/MM/DD/wHH/    # wHH = 该 2 小时窗 (w00=00:00-02:00 ... w20=20:00-24:00)
        ├── 原帖_Stock.md  # 原始文档: 窗内全部串 (主题+全部楼层+📎附件标记)
        ├── meta.json      # 窗元数据 (串数/帖数/附件数/时间戳)
        └── attachments/   # 图片附件原图
```

## 三、在新 Ubuntu 机器上部署 (5 步)

### 前提
- Ubuntu 22.04+ (x86_64), Python 3.10+ (建议 3.11/3.12/3.13; 本工具在 3.13 实测)
- 能访问 `https://www.newsmth.net` (国内直连即可, 无需代理)
- 一个水木社区账号 (**必须已开通股版读权限**; 账号需已在浏览器正常登录过一次)

### 步骤

```bash
# 1) 基础依赖 (装 venv 和 git; 已有可跳过)
sudo apt update && sudo apt install -y python3-venv python3-pip git

# 2) 把本目录拷到目标机器任意位置, 例如 ~/shuimu
#    进入目录, 一键安装:
cd ~/shuimu
chmod +x install.sh && ./install.sh
#    install.sh 做的事: 建 .venv -> 装 scrapling[fetchers] -> 建 archive/ 并 git init
#    -> 校验 credentials 存在且格式正确

# 3) 配置水木账号 (重要!)
vim credentials
#    格式 (两行, 无其他内容):
#    username=你的水木账号
#    password=你的水木密码
chmod 600 credentials   # 权限收紧, 防其他用户读

# 4) 环境自检: 跑图片功能自测 (会真实访问水木 API, 需要账号有效)
./.venv/bin/python _img_selftest.py
#    看到 "✅ PASS" 即环境 OK; 失败信息会指明是网络/账号/依赖哪一环

# 5) 开爬 (见下节)
```

> 不想用 install.sh 也可以手动: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt && git init archive`

### 依赖说明 (requirements.txt)
```
scrapling[fetchers]==0.4.15
```
- 这是唯一第三方依赖。`[fetchers]` extra 会带出 curl_cffi (TLS 指纹核心)、lxml、click 等。
- **不需要** playwright/浏览器 (旧 CDP 登录路已退役); pip 会自动装 playwright 库但不用装浏览器, 可忽略。
- 国内网络 pip 源慢时: `pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/`

## 四、使用

### 4.1 爬一段历史区间 (最常用)

主爬虫按 **2 小时窗** 组织数据。先造队列 (要爬哪些窗), 再跑主爬虫:

```bash
cd ~/shuimu

# A) 造区间队列: 08-31 00:00 -> 09-11 14:00 (北京时间), 每 2h 一窗, 只入队已结束的窗
./.venv/bin/python make_queue.py --start 2026-08-31 --end "2026-09-11 14:00"
#    常用参数: --force 覆盖已有队列 / --dry-run 只打印不写
#    产出 backfill_queue.json (结构 {"tasks":[{label,start,end,status}]}), 主爬虫/看门狗直接消费
```

```bash
# B) 开爬 (队列驱动; 自动: 列表遍 -> 只拉命中窗的串全文 -> 写 archive/ -> 下载附件 -> 标 done -> git commit)
./.venv/bin/python nf_crawler.py
#    可选参数:
#      --dry-run     不写归档不提交, 只统计 (先试水用)
#      --list-only   只跑列表遍看有多少串
#      --stop-time "2026-09-01 00:00:00"  显式指定列表截止 (默认自动取队列最早 pending 窗)
```

**产出**: `archive/2026/MM/DD/wHH/原帖_Stock.md` + `meta.json` + `attachments/*.png|jpg`, 并自动 git commit。

### 4.2 每日增量 (全自动, 生产环境配置)

生产机上用 cron 三件套 (本工具自带, 无需写任何代码):

| 任务 | cron 表达式 (UTC, 北京时间+8) | 脚本 | 作用 |
|---|---|---|---|
| 每日入队 | `20 0 * * *` (北京 00:20) | `queue_add_windows.py` | 把前一天已结束的 2h 窗加入队列 (幂等, 跳过已有) |
| 看门狗 | `*/2 * * * *` | `auto_pipeline.py` | 队列有 pending 就验认证->开爬->完成后飞书汇报; 连续 3 次失败进 30min 冷却 |
| (可选) 飞书汇报 | 看门狗内置 | `deliver_feishu.py` | 需要 `.env` 里有飞书 app_id/app_secret; 不用飞书忽略 |

```bash
# 装 cron (示例, 路径换成你的):
crontab -e
20 0 * * * cd /home/user/shuimu && ./.venv/bin/python queue_add_windows.py >> logs_cron.log 2>&1
*/2 * * * * cd /home/user/shuimu && ./.venv/bin/python auto_pipeline.py >> logs_cron.log 2>&1
```

不用 cron 也行: 每天手动跑一次 `queue_add_windows.py` 再跑 `nf_crawler.py`。

### 4.3 图片附件 (自动, 无需配置)

- 带图帖子在 `原帖_Stock.md` 里以 `📎 附件: 文件名 (大小)` 标记, 原图存 `attachments/`。
- 下载路由是 `/nForum/api/attachment/Stock/<article_id>/<pos>` + 同款 Basic (API 返回的 `file.url` 是 web 路由会 404, 代码已处理, 详见 playbook 第 9 节)。
- 幂等: 已下载的图不重复拉, 重跑安全。

### 4.4 环境变量 (可选覆盖, 默认开箱即用)

| 变量 | 默认解析顺序 |
|---|---|
| `SHUIMU_CREDS` | 本目录 `credentials` → `~/.config/newsmth/credentials` |
| `SHUIMU_ARCHIVE` | 本目录 `archive/` → `/opt/data/shuimu_daily` (仅本机生产机存在) |
| `SHUIMU_PYTHON` | 看门狗里调子进程用的解释器 (默认生产机路径; 手动跑主爬虫不受影响) |

**换机部署时什么都不用设**: 工具自动找本目录的 `credentials` 和 `archive/`。

## 五、常见问题 (踩坑实录)

1. **401 未授权** → 账号密码错, 或 `credentials` 格式不对 (必须 `username=`/`password=` 前缀, 值前后不要引号)。
2. **0102 (账号登录过多)** → 水木限制同账号同时登录会话数; 去浏览器把水木的登录退掉, 1-2 分钟自动恢复, 工具会自动重试。
3. **列表遍第 1 页就空** → 网络/被风控; 检查能否 `curl -I https://www.newsmth.net` (应 200/302), 等 10 分钟再试; 连续多试会加重风控, 别循环硬刷。
4. **附件 404** → 不要直接 GET API 返回的 `file.url` (web 路由, 需 cookie); 代码走的是 api 路由, 自测脚本 `_img_selftest.py` 专门验这条链。
5. **pip 装 scrapling 失败 (TLS/网络)** → 国内机用阿里云镜像源; 或宿主机 `pip download` 后 `pip install --no-index --find-links` 离线装。
6. **时区** → 所有时间一律北京时间 (UTC+8) 显式处理, 与系统时区无关; 但 cron 表达式按**系统时区**解释, 装 cron 前先 `date` 确认。
7. **被踢/风控升级** → 限速 0.6-1.6s 是实测安全值, 不要调低; 大区间补爬建议白天人盯着, 连续 3 次失败工具自动冷却 30 分钟。
8. **置顶帖** → API 的 `is_top` 帖 `last_reply_time` 恒为 2026-06-12, 工具已自动跳过, 不参与截止判定。

## 六、安全纪律 (务必遵守)

- **凭据文件永不进 git**: `archive/` 是独立 git 仓; 本目录若 git 化, `.gitignore` 必须含 `credentials`、`.nf_cookie`、`backfill_queue.json`。
- **不要尝试登录网页版/解 keyring/过滑块 (geetest)** — 旧登录路线全部退役, 会触发风控且伤账号。API 路只需要账号密码。
- **账号安全第一**: 同一账号别在多台机器同时高频跑; 本工具单实例设计。
- 凭据值不要打印到日志/群聊/文档。

## 七、备份路: telnet (API 故障时启用)

API 路连续不可用 (风控升级/接口改版) 时, 可切回经典 telnet 协议爬法。本工具包**不含** telnet 代码 (它是另一套 ~15 个文件的状态机, 且依赖独立 venv), 备份位置:

- 生产机代码: `/home/mac/.hermes/scripts/shuimu_daily/` (shuimu_telnet.py + shuimu_run.py + backfill_range.py + legacy_shuimu_scrape.py)
- 运行环境: 独立 venv `venvs/shuimu` (python3.12 + requests, 与 scrapling venv 分离)
- 用法: `python backfill_range.py --start 2026-08-31 --end 2026-09-02` (按天回补, ~3.2s/帖, 比 API 慢一个数量级)
- 纪律: 不碰 geetest 滑块; 自动化登录只做单次安全尝试

## 八、验证清单 (换机部署完成后逐项打勾)

- [ ] `./.venv/bin/python -c "from scrapling.fetchers import FetcherSession; print('ok')"`
- [ ] `cat credentials` 格式 = 两行 key=value (值不落群聊!)
- [ ] `./.venv/bin/python _img_selftest.py` → `✅ PASS` (真实 API 全链路含图片)
- [ ] 造 1 个小队列 (如昨天 1 个 2h 窗) → `nf_crawler.py` → `archive/` 出现 `原帖_Stock.md` + git commit 成功
- [ ] `tail logs/nf_crawler.log` 看到 `=== 完成: 请求 N 次 ===` 且无 `exit 2`

全部通过 = 部署成功。之后日常只跑 4.2 的两条 cron 即可。

---

## 附: 技术细节索引

- API 全部端点/字段/坑 → `NFORUM_API_PLAYBOOK.md`
- 附件下载路由推导 (源码级证据) → playbook 第 9 节
- 主爬虫代码注释 → `nf_crawler.py` (关键决策都有行内注释)
- 备份来源: 生产仓 `/home/mac/.hermes/scripts/shuimu_daily/` git commit `647450c` (2026-09-11)
