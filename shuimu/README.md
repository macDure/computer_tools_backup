# 水木社区 Telnet 中文终端

这个目录提供一个适合 Linux 终端使用的水木社区 Telnet 客户端：

- 连接 `bbs.newsmth.net:23`
- 自动进行本地 UTF-8 与论坛 GB18030/GBK 编码转换，解决中文乱码
- 使用伪终端保持 Telnet 的交互体验
- 默认每 60 秒发送一个不显示的 NUL 心跳，减少空闲超时断线
- 支持首次保存用户名和密码，以后自动填写登录提示

## 文件

| 文件 | 作用 |
|---|---|
| [`newsmth-bbs.py`](./newsmth-bbs.py) | 主程序 |
| [`shuimu-scrape.py`](./shuimu-scrape.py) | 按版面和作者抓取帖子 |
| [`requirements.txt`](./requirements.txt) | 抓取工具的 Python 依赖 |
| [`tests/test_shuimu_scrape.py`](./tests/test_shuimu_scrape.py) | 解析器回归测试 |
| `README.md` | 本部署和使用说明 |

## 依赖

目标电脑需要安装：

```bash
python3 --version
telnet --help
```

本程序只使用 Python 标准库，不需要安装 `expect`、`luit` 等额外组件。若没有 Telnet 客户端，在 Debian/Ubuntu 上可安装：

```bash
sudo apt update
sudo apt install telnet
```

`shuimu-scrape.py` 使用 `requests` 和 `beautifulsoup4`，建议单独建立虚拟环境：

```bash
cd /home/mac/macperson/computer_tools_backup/shuimu
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

迁移到新电脑时不必复制 `.venv`，在新电脑重新执行上面三条命令即可。

## 第一次部署

把整个 `shuimu` 目录复制到目标电脑。例如仍使用当前路径：

```bash
mkdir -p /home/mac/macperson/computer_tools_backup
cp -r shuimu /home/mac/macperson/computer_tools_backup/
chmod +x /home/mac/macperson/computer_tools_backup/shuimu/newsmth-bbs.py
```

如果目标电脑用户名或目录不同，把下面命令中的路径改成实际路径。

## 配置 `shuimu` 命令

`shuimu` 实际上是 Bash 函数，不是普通环境变量。将下面内容追加到 `~/.bashrc`：

```bash
shuimu() {
    /home/mac/macperson/computer_tools_backup/shuimu/newsmth-bbs.py "$@"
}
```

让当前终端立即生效：

```bash
source ~/.bashrc
```

也可以关闭当前终端、重新打开一个终端。

检查是否配置成功：

```bash
type shuimu
```

## 已实测的 Telnet 路径

真实登录后，进入 `Stock` 版和查找作者的路径如下：

```text
登录后按 n 翻过提示页
主选单 → S → 回车 → 输入 Stock → 回车
版面列表 → A（上翻作者）或 a（下翻作者）
清空输入框中当前作者 → 输入 Icestone → 回车
r 读取选中文章；q 返回列表；p 或 Ctrl-X 进入主题阅读；空格/↓ 看下一篇；P 翻到更早一页
```

注意：作者搜索框会保留当前选中的作者。第一次搜索时要先退格清空；程序会自动完成这一步。自动遍历时，程序使用实测的 `A → 等待作者提示 → 回车 → r → q` 顺序；当前页面找不到更早的作者文章时，会自动按 `P` 翻到更早的版面页，再继续检索，直到日期范围之外或论坛最早记录。终端刷新时偶尔只显示楼层序号，程序会根据返回后的普通版面页和同页完整文章号恢复真实编号，不会把楼层号、作者检索序号或在线人数当成文章号。跨页位置会写入 `.state.json`，`--resume` 时会先恢复到上次的大致版面位置。

## 抓取指定作者帖子

`shuimu-scrape.py` 默认抓取 `Stock` 版 `Icestone` 的作者文章，正文和引用只保存到本地，不会发帖、回帖或上传数据。它有两个后端：

- `telnet`：使用已有 Telnet 账号，适合当前需要登录才能阅读的内容；默认每秒间隔一次操作。
- `web`：使用网页结构化页面；水木当前可能要求 Geetest，工具不会绕过验证码。
- `auto`：先尝试网页端，网页端需要验证码或不可用时自动切换到 Telnet。

图片会自动提取并下载到 `data/images/`，Markdown 会嵌入本地图片，JSON 会同时保存原始 URL、下载状态和失败原因。默认每篇最多下载 20 张、单张不超过 20 MiB；可用 `--no-images` 只保留链接。

在 `~/.bashrc` 中加入抓取快捷命令：

```bash
shuimu-scrape() {
    /home/mac/macperson/computer_tools_backup/shuimu/.venv/bin/python \
        /home/mac/macperson/computer_tools_backup/shuimu/shuimu-scrape.py "$@"
}
```

然后执行：

```bash
source ~/.bashrc
```

先用一篇文章做真实验证：

```bash
shuimu-scrape --backend telnet --limit 1
```

默认全量抓取 `Stock` 版 `Icestone`：

```bash
shuimu-scrape
```

也可以明确使用 Telnet 后端：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock
```

换作者或版面：

```bash
shuimu-scrape --author Icestone --board Stock
shuimu-scrape --author other_user --board Fund
```

按日期过滤：

```bash
shuimu-scrape --since 2020-01-01 --until 2026-12-31
```

中断后继续：

```bash
shuimu-scrape --resume
```

只做小规模检查、不保存正文：

```bash
shuimu-scrape --dry-run
```

默认输出到 `shuimu/data/`：

```text
Stock_Icestone.md          # 便于阅读的完整主题归档
Stock_Icestone.json        # 结构化数据
Stock_Icestone.state.json  # 断点状态
Stock_Icestone.errors.json # 失败主题和原因
images/                    # 已下载图片
```

Telnet 后端会跨版面分页按作者搜索结果逐篇保存目标作者的文章、标题、时间、引用和正文；Telnet 页面不总显示楼层号，因此个别文章会标记为“楼层未标记”。遇到删除、审核中或无权限查看的内容时，只保存元数据和缺失原因。网页后端可进一步保存主题中的其他楼层。

图片参数：

```bash
shuimu-scrape --max-images 50 --max-image-bytes 52428800
shuimu-scrape --no-images
```

默认每次操作间隔 1 秒。工具不模拟真人、不随机伪装请求，也不绕过验证码或封禁；它只做串行低频访问、重试瞬态错误、缓存已下载图片，遇到账号在线窗口、验证码、权限拒绝或连续超时会停止并保留断点。可以进一步放慢访问：

```bash
shuimu-scrape --rate 2
```

若遇到“账号已有其他在线窗口”，程序不会自动踢出已有会话；先退出其他 Telnet/Web 会话，再重试。Telnet 后端每成功读取一篇就落盘；中途断开后可使用 `--resume` 继续向更早文章遍历。

调试网页后端（不读取凭据）：

```bash
shuimu-scrape --backend web --no-login --dry-run
```

调试解析器：

```bash
cd /home/mac/macperson/computer_tools_backup/shuimu
.venv/bin/python -m unittest discover -s tests -v
```

旧版本曾只在当前版面页内搜索，因此可能得到像“只有 9 篇”这样的明显偏少结果。升级本版本后，第一次重新做某个日期段时请不要加 `--resume`，直接用原命令重新抓取；之后如果中断，再对同一个输出目录加 `--resume`。如果旧目录里已经有旧版本结果，建议换一个新的输出目录，避免把旧断点和新逻辑混在一起。

## 配置自动登录

首次执行：

```bash
shuimu --setup
```

按提示输入水木用户名和密码。输入密码时终端不会显示字符。

凭据默认保存到：

```text
~/.config/newsmth/credentials
```

程序会将该文件权限设置为 `600`，即仅当前用户可读写。密码以本地文件形式保存，请不要把这个文件上传到 Git 仓库或分享给别人。

配置完成后直接执行：

```bash
shuimu
```

程序会在识别到用户名、密码提示时自动填写。如果不想自动登录，删除凭据文件即可，之后手动输入：

```bash
rm ~/.config/newsmth/credentials
```

## 常用参数

论坛仍显示乱码时尝试使用 GBK：

```bash
shuimu --encoding gbk
```

调整心跳间隔为 120 秒：

```bash
shuimu --heartbeat 120
```

关闭心跳：

```bash
shuimu --heartbeat 0
```

也可以指定其他主机和端口：

```bash
shuimu bbs.newsmth.net 23
```

## 使用和退出

启动：

```bash
shuimu
```

退出 Telnet：按 `Ctrl-]`，然后按 `q`。

## 故障排查

### `shuimu: command not found`

确认 `~/.bashrc` 中已经加入函数，然后执行：

```bash
source ~/.bashrc
```

### `Permission denied`

重新设置脚本可执行权限：

```bash
chmod +x /home/mac/macperson/computer_tools_backup/shuimu/newsmth-bbs.py
```

### 中文仍然乱码

依次尝试：

```bash
shuimu --encoding gbk
shuimu --encoding gb18030
```

### 服务器仍然断开

可以把心跳调短，例如：

```bash
shuimu --heartbeat 30
```

心跳只能减少服务器因空闲导致的断开，无法避免服务器维护、网络中断或服务器主动踢线。

## 迁移到另一台电脑

迁移时复制以下内容：

1. `shuimu` 目录中的 `newsmth-bbs.py`、`shuimu-scrape.py`、`requirements.txt` 和本 `README.md`。
2. 新电脑重新创建 `.venv` 并安装 `requirements.txt`。
3. `~/.bashrc` 中的 `shuimu` 和 `shuimu-scrape` 函数配置。
4. 如果希望免登录，还要单独迁移 `~/.config/newsmth/credentials`，并确保权限为 `600`；更安全的方式是在新电脑上重新执行 `shuimu --setup`。

推荐在新电脑上重新配置密码：

```bash
shuimu --setup
shuimu
```

## 新手操作手册：按时间段抓取文章

这一节只需要记住一个命令格式。下面的日期都使用 `年-月-日` 格式，例如 `2025-01-01`。

### 第一步：打开终端并加载命令

每次打开一个新的终端窗口，先执行：

```bash
source ~/.bashrc
```

如果提示 `shuimu-scrape: command not found`，重新执行上面的命令即可。

如果这是新电脑、还没有保存登录信息，先执行一次：

```bash
shuimu --setup
```

按提示输入水木用户名和密码。以后抓取时程序会自动使用这个登录信息，不需要在命令中写密码。

### 第二步：填写日期并开始抓取

最常用的命令是：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 2025-01-01 --until 2025-12-31 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_2025
```

这条命令的意思是：

- `--author Icestone`：抓取发信人 `Icestone` 的文章。
- `--board Stock`：只抓取 `Stock` 版。
- `--since 2025-01-01`：从 2025 年 1 月 1 日开始，包含这一天。
- `--until 2025-12-31`：到 2025 年 12 月 31 日结束，包含这一天。
- `--output-dir .../Stock_Icestone_2025`：把这一段日期单独保存，避免覆盖其他日期的归档。

你以后只需要改 `--since`、`--until` 和最后的文件夹名称。例如：

抓取 2024 年全年：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 2024-01-01 --until 2024-12-31 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_2024
```

抓取 2026 年 1 月至 6 月：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 2026-01-01 --until 2026-06-30 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_2026上半年
```

只抓取某一天：把开始日期和结束日期写成同一天：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 2026-08-01 --until 2026-08-01 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_2026-08-01
```

只设置开始日期，表示从这天开始一直抓到目前能找到的最新文章：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 2026-01-01 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_from_2026-01-01
```

只设置结束日期，表示抓取这天以及更早的文章：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --until 2025-12-31 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_until_2025-12-31
```

### 第三步：等待完成并查看结果

抓取过程中终端会逐篇显示文章编号和标题。完成后，结果会在你指定的文件夹中：

```text
Stock_Icestone.md          可直接阅读的文章
Stock_Icestone.json        结构化数据
Stock_Icestone.state.json  断点记录
Stock_Icestone.errors.json 失败记录
images/                    下载的图片
```

例如上面的 2025 年命令完成后，阅读文件是：

```text
/home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_2025/Stock_Icestone.md
```

图片在：

```text
/home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_2025/images/
```

### 中途断线或主动停止后怎么办

如果同一段日期还没有抓完，使用完全相同的命令，并在末尾加上 `--resume`：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 2025-01-01 --until 2025-12-31 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_2025 \
  --resume
```

`--resume` 的意思是“读取这个文件夹里的断点，接着上次继续”。作者、版面、开始日期、结束日期和输出文件夹都要保持不变。

如果要抓取一个新的日期段，不要使用旧日期段的 `--resume`，请换一个新的 `--output-dir` 文件夹。这样每个日期段都有自己独立的文章和图片，不会相互覆盖。

### 第一次使用时先抓一篇测试

如果你只是想确认登录和路径正常，可以先执行：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 2025-01-01 --until 2025-12-31 \
  --limit 1 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/test
```

确认 `data/test/Stock_Icestone.md` 能打开后，再删除 `--limit 1`，进行完整抓取。`--limit 1` 只适合测试，不代表完整结果。

### 换一个作者或版面

例如抓取 `Alice` 在 `Fund` 版、2025 年全年的文章：

```bash
shuimu-scrape --backend telnet --author Alice --board Fund \
  --since 2025-01-01 --until 2025-12-31 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Fund_Alice_2025
```

只需要替换 `Alice` 和 `Fund`。版面名称、作者名和日期必须写在命令后面，参数前面要保留两个短横线，例如 `--since`。

### 图片下载说明

程序默认会下载文章中识别到的公开图片，并放在本次任务的 `images/` 文件夹中。通常不需要额外参数。

如果想让每篇文章最多下载 50 张图片：

```bash
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 2025-01-01 --until 2025-12-31 \
  --max-images 50 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/Stock_Icestone_2025
```

如果只想保存图片链接、不下载图片，可以加 `--no-images`。已经完成的旧任务也可以用原来的日期和输出文件夹加 `--resume` 重新检查图片。

### 最简记忆版

以后抓取某个日期段时，照着下面的命令，只改日期和文件夹名即可：

```bash
source ~/.bashrc
shuimu-scrape --backend telnet --author Icestone --board Stock \
  --since 开始日期 --until 结束日期 \
  --output-dir /home/mac/macperson/computer_tools_backup/shuimu/data/本次任务名称
```

例如要抓取 2023 年全年，就把 `开始日期` 改为 `2023-01-01`，把 `结束日期` 改为 `2023-12-31`，把 `本次任务名称` 改为 `Stock_Icestone_2023`。
