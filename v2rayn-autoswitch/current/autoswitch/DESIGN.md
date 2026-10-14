# v2rayN 自动切换服务器 & 自动更新订阅工具 — 设计方案

版本: v0.1（待确认）  日期: 2026-09-07  状态: 待评审

## 1. 背景与目标

v2rayN（V7.4.2）当前通过订阅 `justmysocks3.net` 管理 6 个节点（c1s1~c1s5、c1s801，
2×Shadowsocks + 4×VLESS-Reality）。节点 IP 会随订阅更新轮换，且线路质量不稳定
（此前已发生过"孤儿核心占用 10808 导致代理持续失效"的事故）。

目标：每天 **08:30（北京时间）** 由定时任务自动完成：

1. 检查所有服务器连通性（按 c1s1 → c1s2 → … 升序），记录各节点延迟；
2. 选取**升序第一个不超时**的服务器 S1，切换过去；
3. **通过 S1 的代理**更新订阅（拉取最新节点列表写入 v2rayN 数据库）；
4. 更新后重新检查 **c1s1 与 c1s2**：
   - 两者都正常 → 切换到延迟更小的那个；
   - 只有一个正常 → 切换到那个；
   - 都不正常 → 保持 S1。
5. 全程写日志，结果可查、失败可诊断。

## 2. 现状盘点（已实测确认）

| 项目 | 现状 |
|---|---|
| v2rayN | `/home/mac/v2rayN-linux-64/v2rayN`（Avalonia GUI，V7.4.2），当前在纯 tty 会话下运行，无 X 显示、无 Xvfb |
| 核心 | 自带 `bin/xray/xray`（Xray 24.11.5），所有节点类型均可由它处理 |
| 状态文件 | `guiConfigs/guiNDB.db`（SQLite：ProfileItem/SubItem/ProfileExItem 等）、`guiConfigs/guiNConfig.json`（`IndexId` = 当前选中节点）、`guiConfigs/config.json`（v2rayN 启动时自动生成，**工具不手写**） |
| 订阅 | `SubItem.Url` = `<TARGET_SUBSCRIPTION_URL>`（直接 HTTPS URL，未 base64） |
| 节点表 | `ProfileItem`：ConfigType 3=Shadowsocks、5=VLESS；VLESS-Reality 参数存于 Sni/Fingerprint/PublicKey/ShortId/Flow 列 |
| 代理端口 | socks5 `127.0.0.1:10808`（系统代理指向它） |
| 定时 | 系统已装 cron（`/usr/sbin/cron`、`/usr/bin/crontab`），系统时区 = Asia/Shanghai |
| 关键教训 | v2rayN 退出后核心进程可能残留并继续占用 10808；**工具必须保证"写库/写配置前 v2rayN 进程已完全退出"** |

## 3. 总体架构

**原则：不依赖 GUI、不依赖显示环境，全部在"配置文件 + xray 核心进程"层面操作。**
v2rayN 的 GUI 只作为"最终载体"：工具改好状态文件后重启 v2rayN，由它按新状态起核心。

```
autoswitch/
├── DESIGN.md          # 本文档
├── run.sh             # cron 入口（环境、日志、调用主程序、锁）
├── autoswitch.py      # 主逻辑（Python3 纯标准库，单文件）
├── config.conf        # 可调参数
├── logs/              # auto-YYYYMMDD.log 每次运行追加
└── last_result.json   # 最近一次结果摘要（人/脚本可读）
```

组件职责：

- **run.sh**：拿锁（防重叠运行，`flock autoswitch.lock`）、设置 PATH/时区、调用
  `python3 autoswitch.py "$@"`、按退出码记录结果。
- **autoswitch.py**：
  - `db.py` 逻辑：读写 guiNDB.db（先备份；仅在 v2rayN 进程确认退出后写）
  - `probe.py` 逻辑：生成测试用 xray 配置（仿 v2rayN `configSpeedtest.json` 的
    单核心多端口模式）→ 启动 `bin/xray/xray` → 逐节点
    `curl -x socks5h://127.0.0.1:PORT <test_url>` 测延迟 → 回收进程
  - `subsync.py` 逻辑：经选定节点代理拉取订阅 → 解析 share links → 事务性写库
  - `switch.py` 逻辑：写 `guiNConfig.json` 的 `IndexId`；必要时重启 v2rayN；
    校验 10808 恢复监听
  - `report.py` 逻辑：日志 + last_result.json
- **v2rayN（被管对象）**：工具在开始前提前退出（SIGTERM→等待→SIGKILL），结束前重启
  （`nohup ./v2rayN &`）。v2rayN 启动时读取 `IndexId`、自动生成 `config.json`、
  恢复代理（该行为在 2026-09-02 15:11 启动时已观察到：启动 12s 内重写 config.json）。

## 4. 每日执行流程（08:30）

```
┌─ run.sh（flock 防重叠）
│
1. 预检
   ├─ 1.1 v2rayN 在跑？ → SIGTERM，等 ≤15s；未退 → SIGKILL；仍未退 → [中止, 退出码2]
   ├─ 1.2 pgrep 确认 v2rayN/xray(本目录) 均无进程
   ├─ 1.3 读取 guiNDB.db：当前订阅的全部节点、SubItem.Url
   └─ 1.4 读取 guiNConfig.json：当前 IndexId（仅作记录）
│
2. 节点探测（更新前）
   ├─ 生成单核心多端口测试配置：127.0.0.1:12301..1230N socks in，每节点一个
   │  outbound（按 DB 字段精确还原 ss / vless-reality 配置），routing 按
   │  inboundTag→outboundTag 映射（与 v2rayN configSpeedtest.json 同构）
   ├─ 启动 bin/xray/xray；任一启动失败 → [中止, 退出码4]
   ├─ 按 c1s1→c1s801 升序（remark 尾部数字排序），逐个：
   │  curl -x socks5h://127.0.0.1:PORT -o /dev/null -s -w '%{http_code} %{time_total}'
   │       --max-time 8 https://www.google.com/generate_204
   │  记录：ok = (http_code==204)，latency = time_total；超时/非204 = fail
   └─ 选 S1 = 升序第一个 ok 的节点
       若全部 fail → [不切换、更新订阅跳过、恢复现场、退出码1]
│
3. 切换 S1（先于订阅更新，保证有可用代理）
   └─ 写 guiNConfig.json IndexId = S1（写入前 .bak 备份）
│
4. 订阅更新（经 S1 代理）
   ├─ curl -x socks5h://127.0.0.1:S1port --max-time 30 <SubItem.Url>
   ├─ 解码：先按 base64 尝试（校验解码后含 "://"），失败则按原文
   ├─ 解析每行 share link：ss:// / vless:// / trojan:// / vmess://
   │  （remark 取 # 片段 URL-decode；参数映射到 ProfileItem 各列，
   │   ConfigType：ss=3, vless=5, trojan=4, vmess=1 —— 以现库行为校准）
   ├─ 事务写库：
   │  · 同 subid 内按 remark 匹配 → 保留原 IndexId 仅更新字段；新节点生成
   │    唯一 19 位 IndexId；订阅中消失的节点删除
   │  · ProfileExItem 同步（新节点 delay=-1）；SubItem.UpdateTime=now
   └─ 失败（超时/解析 0 节点）→ [跳过订阅更新，保留旧库，记警告，继续第 5 步]
│
5. 更新后复检 c1s1 / c1s2
   ├─ 用更新后的 DB 重新生成测试配置，重启测试 xray，只测 c1s1、c1s2
   ├─ 判定：
   │  · 两者 ok → final = 延迟更小者
   │  · 仅一个 ok → final = 该节点
   │  · 都 fail → final = S1
   └─ final ≠ S1 时：再写一次 IndexId
│
6. 恢复代理
   ├─ nohup ./v2rayN & disown（在 v2rayN 目录下）
   ├─ 等待 10808 监听（轮询 ≤30s）
   └─ 未监听 → 兜底：按 final 节点生成 config.json（v2rayN 同构格式）
      并自行启动 bin/xray/xray，保证代理可用
│
7. 收尾
   ├─ 清理测试 xray 与临时配置
   ├─ 写 logs/auto-YYYYMMDD.log 全过程 + last_result.json
   └─ 退出码：0=全部成功 1=全节点不可用 2=v2rayN 无法退出 3=订阅更新失败(已切换)
      4=探测环境失败
└─ 结束
```

## 5. 关键设计点

### 5.1 节点探测为什么自起 xray 而不是走 10808
- 10808 由 v2rayN 核心占用且此时 v2rayN 已被停掉；测试必须独立。
- 与 v2rayN 自带测速（configSpeedtest.json）完全同构：单核心、每节点一对
  socks 端口，结果口径一致，便于对照。
- 测试端口 12301 起递增，启动前做占用检查，冲突则整体 +1000 重试一次。

### 5.2 为什么订阅更新由工具自己拉取解析（而不是让 v2rayN 做）
- v2rayN 的订阅更新只能靠 GUI 操作或启动时机触发，无法在无 GUI 交互的定时
  场景里可靠地"等待其完成"；本环境没有 X 显示/Xvfb。
- 工具解析逻辑与 v2rayN 行为对齐（同 schema 写库、同 remark 匹配保留
  IndexId），且**第 5 步用更新后的节点实测连通**天然验证了解析正确性——
  若解析错了，c1s1/c1s2 测试必失败，自动回落到 S1，不会把用户搞挂。
- 当前订阅只含 ss:// 与 vless:// 两类（另实现 trojan/vmess 解析作为冗余）。

### 5.3 为什么"切换"= 改 IndexId 而不直接改 config.json
- `config.json` 由 v2rayN 启动时按 `IndexId` + DB 重新生成（已实测），
  手写它会被覆盖、且易与 v2rayN 状态不一致。
- 写 `IndexId` 是唯一权威入口：v2rayN 重启后即按新节点工作，GUI 列表状态一致。

### 5.4 v2rayN 进程处理
- 开始时：SIGTERM → 等 ≤15s → SIGKILL → pgrep 双确认（v2rayN 主进程 +
  本目录 xray 子进程）。
- **写任何状态文件之前必须再次 pgrep 确认**（吸取孤儿核心教训）。
- 结束时：重启 v2rayN；若 v2rayN 未能自行恢复代理（未监听 10808），
  工具按 final 节点自行启动 xray 兜底（v2rayN 之后手动开代理时若遇端口
  冲突，v2rayN 会提示，属已知取舍，见 §8 开放问题 ①）。

### 5.5 数据安全
- 每次写 `guiNDB.db` / `guiNConfig.json` 前备份为 `*.bak-YYYYmmddHHMMSS`，
  各保留最近 5 份；
- 订阅更新为单事务（upsert + 删除 + UpdateTime），任何解析异常整体回滚；
- 全程只读 v2rayN 二进制与 bin/ 目录，不改 v2rayA 的任何东西。

### 5.6 故障矩阵

| 故障 | 行为 | 退出码 |
|---|---|---|
| v2rayN 无法杀死 | 不碰任何文件，日志记录 | 2 |
| 全部节点超时 | 不切换、不更新、重启 v2rayN 恢复原代理 | 1 |
| 测试 xray 启动失败 | 同上，恢复原代理 | 4 |
| 订阅拉取/解析失败 | 跳过订阅更新，仍完成切换 S1（及其复检逻辑退化为保持 S1） | 3 |
| c1s1/c1s2 更新后都不可用 | 保持 S1 | 0 |
| 代理最终未恢复（极端） | 日志 ERROR + last_result.json 标记，兜底 xray 已尝试 | 0/5 |

## 6. 定时任务部署

- 时区：系统即 Asia/Shanghai，无需在 cron 里额外处理。
- 用户级 cron（默认方案，`crontab -e` 添加一行）：

```
30 8 * * * /home/mac/v2rayN-linux-64/autoswitch/run.sh >/dev/null 2>&1
```

- 备选：systemd user timer（需要 `loginctl enable-linger mac` 保证未登录也运行），
  若你希望"关机状态/未登录也保证执行"再考虑，本方案默认 cron。
- 结果查看：
  - `cat autoswitch/logs/auto-$(date +\%Y\%m\%d).log`
  - `cat autoswitch/last_result.json`

## 7. 验收标准

1. **dry-run**：`./run.sh --dry-run` 只探测并打印各节点延迟与将选择的节点，
   不杀进程、不写库、不切节点；
2. **真实执行**：v2rayN 被平滑重启，`IndexId` 指向预期节点，10808 恢复监听，
   订阅 `UpdateTime` 刷新（节点 IP 如有轮换则更新），c1s1/c1s2 优先规则生效；
3. **故障注入**（任选 2 项验证）：
   - test_url 改不可达 → 全节点 fail → 状态零变更、退出码 1；
   - 订阅 URL 改错误 → 订阅跳过、节点仍切换、退出码 3；
   - 手工构造 v2rayN 不响应 SIGTERM（难模拟，可改测 SIGKILL 路径）；
4. **连续 2 天** 08:30 cron 自动运行，日志与 last_result.json 正常。

## 8. 开放问题（请确认）

① 每天 08:30 工具会**关闭并重启 v2rayN**（代理中断约 1~3 分钟），可接受？
② 全部节点超时时的默认行为是"保持现状只记日志"，可接受？
③ 测试 URL = `https://www.google.com/generate_204`、单节点超时 8 秒、
   订阅拉取超时 30 秒——数值是否 OK？
④ 更新后 c1s1/c1s2 都不正常时保持 S1（升序第一个可用），确认？
⑤ 订阅更新由工具自行拉取解析写库（理由见 §5.2），确认？
⑥ 调度用用户级 cron（默认）还是 systemd user timer？
⑦ 工具运行期间若 v2rayN 重启后没自动恢复代理，工具会**自行起一个 xray**
   兜底（可能与之后你手动操作 v2rayN 开代理产生一次端口冲突提示），可接受？

## 9. 明确不做的事

- 不修改 v2rayA 的任何进程/文件/服务；
- 不实现 v2rayN 内置"自动切换"能覆盖的部分之外的 GUI 自动化（不模拟点击）；
- 不做多订阅、不做节点池扩容（当前单一订阅 6 节点）；
- 不改动 10808 以外的任何系统代理设置。

---

# 附: 工具使用方法

> 工具目录: `/home/mac/v2rayN-linux-64/autoswitch/`
> 入口: `run.sh`(推荐) 或直接 `python3 autoswitch.py`

## A. 日常使用(三步走)

### A.1 试跑(零副作用, 先确认探测正常)
```bash
/home/mac/v2rayN-linux-64/autoswitch/run.sh --dry-run
```
- 只启动临时测试 xray 探测各节点并打印延迟, **不杀 v2rayN、不写任何 v2rayN 文件**;
- 输出结尾 "若正式执行: 切换到 c1sX" 即本次会选的节点;
- 全部 FAIL 时退出码为 1(仅提示, 无任何改动)。

### A.2 正式执行(首次建议盯着日志看)
```bash
cd /home/mac/v2rayN-linux-64/autoswitch
./run.sh
tail -f logs/auto-$(date +%Y%m%d).log   # 另开终端观察
```
执行期间 v2rayN 会被短暂关闭并自动重启(代理中断约 1~3 分钟)。
完成后检查:
```bash
cat last_result.json
```
- `selected`: 升序探测选中的 S1
- `sub_updated`: 订阅是否更新成功
- `final_server`: 最终生效节点
- `proxy_restored`: 代理(10808)是否恢复
- `fallback_xray`: 是否走了兜底 xray(true 说明 v2rayN 没自动恢复代理)

再到 v2rayN 界面确认当前节点与订阅已刷新。

### A.3 挂每日定时(确认 A.1/A.2 都正常后)
```bash
crontab -e
# 加入一行:
30 8 * * * /home/mac/v2rayN-linux-64/autoswitch/run.sh
```
- 系统时区即 Asia/Shanghai, 无需额外设置;
- 查看已装任务: `crontab -l`;
- cron 运行结果看 `logs/auto-YYYYMMDD.log` 和 `last_result.json`。

## B. 常用参数

| 参数 | 说明 |
|---|---|
| `--dry-run` | 只探测+报告, 不杀进程不写文件(退出码 1 表示全部不可用, 仅提示) |
| `--no-restart` | 结束后不重启 v2rayN(状态文件仍会更新, 由你手动启动 v2rayN) |
| 无参数 | 正式执行(cron 用法) |

## C. 配置项 (`config.conf`)

| 键 | 默认 | 说明 |
|---|---|---|
| `v2rayn_dir` | `/home/mac/v2rayN-linux-64` | v2rayN 目录 |
| `test_url` | `https://www.google.com/generate_204` | 连通性测试 URL |
| `test_timeout` | `8` | 单节点探测超时(秒) |
| `sub_timeout` | `30` | 订阅拉取超时(秒) |
| `port_base` | `12301` | 探测 socks 起始端口(自动跳过被占用端口) |
| `main_port` | `10808` | v2rayN 代理端口(校验用) |
| `prefer_after_update` | `c1s1,c1s2` | 更新订阅后优先复检的节点(逗号分隔) |
| `restart_v2rayn` | `true` | 结束后是否重启 v2rayN |
| `backup_keep` | `5` | 备份保留份数 |

## D. 退出码

| 码 | 含义 |
|---|---|
| 0 | 全部成功 |
| 1 | 全部节点超时(保持现状, 未做任何切换) |
| 2 | v2rayN 无法停止(未修改任何文件) |
| 3 | 订阅更新失败(节点切换仍完成) 或 复检后无任何可用节点 |
| 4 | 探测环境失败(curl/xray 不可用) |
| 5 | 兜底 xray 也未能恢复代理(需人工介入) |
| 6 | 未预期异常(看日志堆栈) |
| 75 | 上一次运行未结束, 本次跳过(flock) |

## E. 文件说明

| 路径 | 说明 |
|---|---|
| `logs/auto-YYYYMMDD.log` | 每日运行日志(每次运行追加一段) |
| `logs/v2rayn-restart.log` | 工具拉起 v2rayN 后的输出 |
| `last_result.json` | 最近一次结果摘要(人工/脚本查看) |
| `autoswitch.lock` | 防重叠运行锁(flock) |
| `tmp/` | 临时探测配置/订阅原始内容, 可随时 `rm -rf tmp/` |
| `guiConfigs/guiNDB.db.bak-*` / `guiNConfig.json.bak-*` | 自动备份(每次写前生成, 各留 5 份) |

## F. 排错

1. **某节点一直 FAIL**: 单独验证
   ```bash
   curl -x socks5h://127.0.0.1:10808 -o /dev/null -s -w '%{http_code} %{time_total}s\n' --max-time 10 https://www.google.com/generate_204
   ```
   (10808 上跑的节点若即该节点, 204 正常则说明问题在探测端口/网络侧)
2. **`fallback_xray: true`**: v2rayN 重启后未自动开代理, 工具已自起 xray 接管 10808;
   之后在 v2rayN 里手动开代理可能提示端口占用, 关掉再开一次即可。
3. **订阅更新失败(exit 3)**: 看日志 "订阅更新失败" 一行及 curl 报错;
   常见为节点出口无法访问 `justmysocks3.net` 或面板侧临时故障; 本次节点切换不受影响。
4. **v2rayN 进程杀不掉(exit 2)**: 日志有 ERROR; 手工
   ```bash
   ps -ef | grep -iE 'v2rayn|xray' | grep -v grep
   sudo kill -9 <pid>   # 确认是本目录 v2rayN 相关进程后再执行
   ```
   然后重跑 `./run.sh`。
5. **想回滚某次变更**: 用对应 `.bak-*` 备份覆盖回去
   ```bash
   cp guiConfigs/guiNConfig.json.bak-<时间戳> guiConfigs/guiNConfig.json
   cp guiConfigs/guiNDB.db.bak-<时间戳> guiConfigs/guiNDB.db
   ```
   (操作前确保 v2rayN 已退出)
6. **手动触发一次**(不等 8:30): 直接跑 `./run.sh` 即可, 与 cron 完全等价。

## G. 已知边界

- 工具只在**单一启用订阅**场景下设计(当前 6 节点); 若将来启用多订阅,
  取 `SubItem.Enabled=1` 的第一个, 需评估是否扩展;
- 节点识别依赖 remark 中的 `c1sN` 命名(升序按 N 的数字值);
  若服务商更换命名规则, 调整 `config.conf` 的 `prefer_after_update` 即可,
  排序逻辑(remark 尾部数字)一般无需改动;
- 不修改 v2rayA 的任何组件; 若 v2rayA 的 xray 服务同时启用并占用 10808,
  请先在 v2rayA 面板停掉该服务。

---

# 附录二：最终实现与运维手册（2026-09-08 起为权威版本）

> 本文档前半部分是 09-07 的 v0.1 设计稿。实现经过三轮迭代：
> **温柔模式（GUI 共存）→ 温柔模式 V2（09-08 事故修复）→ 看门狗 v3（GUI 感知端口状态机）**。
> 前后矛盾处，**以本附录为准**。目标读者：拿到本文档后能完成 启动 / 停止 / 诊断 / 新机器部署 的人。

## 1. 用户铁律（一切设计的前提）

1. **10808 端口任何时刻最多一个持有者**——绝不允许助手兜底 xray 与用户 GUI 核心抢端口。
2. **用户开着 `./v2rayN` GUI 时，助手只负责"定时更新订阅 + 保活"**，不管理 GUI 内部状态、不杀用户的任何进程。

推论：GUI 运行时，助手脚本只能以**客户端**身份借道 10808（普通 TCP 连接），绝不绑定端口、绝不 kill 进程。

## 2. 最终架构总览

```
┌─ 宿主机 (有显示器, Ubuntu/Debian, 用户 <user>) ──────────────────────┐
│  /home/<user>/v2rayN-linux-64/                                       │
│    ├── v2rayN            用户手动 ./v2rayN 启动的 GUI (可选运行)       │
│    │     └── bin/xray/xray  GUI 核心 (uid=1000, 可选持有 10808)        │
│    ├── guiConfigs/       guiNDB.db(节点库) config.json GUI 启动时生成   │
│    ├── bin/xray/         兜底核心也用这个 xray (跑 root, uid=0)        │
│    │     └── geosite.dat → ../geosite.dat  (符号链接, 必须存在)        │
│    └── autoswitch/       autoswitch.py(主逻辑) run.sh config.conf     │
│         logs/ last_result.json node_snapshot.json .bak-* 备份         │
├─ Docker: v2rayn-switch-runner ──────────────────────────────────────┤
│  --pid=host --network=host --user 1000:1000                          │
│  --security-opt apparmor=unconfined --security-opt seccomp=unconfined │
│  -v /home/<user>:/home/<user>   (直通宿主目录, 可写)                  │
│  作用: 提供 `docker exec -u 0` 的 root 环境 →                        │
│        ① 以 root(uid=0) 身份跑兜底 xray (与 GUI 核心 uid=1000 区分)    │
│        ② 对宿主 uid=1000 进程发信号 / 读 /proc 做归属判定              │
├─ Hermes Agent 容器 (本助手, /opt/data = 宿主 /home/<user>/.hermes) ──┤
│  cron 调度 (config.yaml timezone: UTC, 调度钉 UTC 防时区漂移):        │
│    · v2rayN-10808代理看门狗    * * * * *   (每 1 分钟)               │
│    · v2rayN-autoswitch-每日08:29  29 0 * * *  (UTC = 北京 08:29)      │
│  脚本目录 /opt/data/scripts/ (= 宿主 /home/<user>/.hermes/scripts/)   │
│  飞书直发: shuimu_daily/deliver_feishu.py (读 .env 凭据)             │
└──────────────────────────────────────────────────────────────────────┘
```

**组件清单（行数/体积为 2026-09-08 实测）**

| 文件 | 行 | 角色 | 位置 |
|---|---|---|---|
| `autoswitch.py` (+3 个幂等补丁) | ~1015 | 主逻辑：探测→切节点→经节点更新订阅→复检→恢复代理 | 宿主 autoswitch/ |
| `run.sh` | 19 | flock 防重叠入口 | 宿主 autoswitch/ |
| `config.conf` | 9 | 可调参数 | 宿主 autoswitch/ |
| `v2rayn_autoswitch.sh` | 116 | 08:29 封装：自愈 runner → 重放 3 补丁 → run.sh → 成功通知/失败告警 | Hermes scripts/ |
| `v2rayn_proxy_guard.sh` | 310 | **看门狗 v3**：GUI 感知 10808 端口状态机，每 1 分钟 | Hermes scripts/ |
| `v2rayn_owner.py` | 122 | 10808 归属判定：`OWNER=gui\|fallback\|none\|other` | Hermes scripts/ |
| `v2rayn_sub_notify.py` | 125 | 08:29 成功通知：节点 diff + 当前节点，无变化静默 | Hermes scripts/ |
| `v2rayn_parse_ss_fix.py` | 102 | 幂等补丁 1：整段 base64 老式 ss 链接解析 | Hermes scripts/ |
| `v2rayn_gentle_mode_fix.py` | 158 | 幂等补丁 2（V1）：检测到 GUI 不杀不重启 | Hermes scripts/ |
| `v2rayn_gentle_v2_fix.py` | 85 | 幂等补丁 3（V2）：gentle 下绝不 kill 任何 xray | Hermes scripts/ |
| `shuimu_daily/deliver_feishu.py` | 99 | 飞书直发（绕开 cron 投递静默失败缺陷 #47056） | Hermes scripts/ |

> **补丁重放机制（关键）**：宿主存在"按源版本还原 autoswitch.py"的行为（EDR 类软件），
> 三个补丁脚本全部**幂等**（已打则输出 `ALREADY_PATCHED`），封装脚本 `v2rayn_autoswitch.sh`
> 每次运行前重放一次，任何补丁失败则**跳过本次执行**（防坏库/防再次弄断端口）。

## 3. 看门狗 v3：5 状态端口归属状态机（每 1 分钟一跳）

归属判定 `v2rayn_owner.py`：读 `/proc/net/tcp6` 找 10808 LISTEN socket 的 inode →
`pgrep -ax xray` 拿全部 xray 进程 cmdline + `/proc/<pid>/status` 读 Uid →
**uid=0 是我方兜底，uid=1000 是 GUI 核心**（GUI 核心也叫 xray，必须按 uid 区分）。
不用 `/proc/exe`：容器 root 缺 CAP_SYS_PTRACE，跨 uid 读 exe 会被拒（实测踩坑）。

| 状态 | 10808 归属 | GUI | 助手行为 | 通知 |
|---|---|---|---|---|
| S1 | **GUI 核心** | 在 | 完全静默退出，不碰任何进程 | — |
| S2 | 兜底 xray | 在 | **交接**：按 PID 精确 kill uid=0 兜底 → 进入 120s 空窗 | 交接成功时 ✅ |
| S3 | 无人 | 在 | 空窗内：等 GUI 核心自行绑上（不动）；**绝不立即拉回兜底**（拉了就是抢端口） | 超期拉回时 ⚠️ |
| S4 | 无人 | 不在 | 拉兜底 xray（失败 2 次→完整 run.sh 自愈） | 恢复时 ✅ / 彻底失败 ⚠️ |
| S5 | 兜底 xray | 关→开 | GUI 关闭时复位交接状态；GUI 再开 → 走 S2 | — |

**交接安全三件套**
- **120s 空窗期**：让位后 GUI 核心 120 秒内绑上 = 交接成功；没绑上 = 拉回兜底保代理
  （最坏代理断口 2 分钟）。GUI 核心绑不上 10808 后**不会自动重试**（09-08 实测），
  所以空窗期是 GUI 点"重启核心"的窗口。
- **交接熔断**：连续 3 个空窗周期 GUI 都绑不上 → 停止反复让位，保持兜底持有
  （防每分钟 120s 断口循环），**熔断触发当刻飞书通知一次**；GUI 关闭后自动复位。
- **只认 uid=0 的 xray 是兜底**：`pull_fallback`/`kill_fallback` 都按
  `/proc/<pid>/status` 的 Uid 过滤，绝不碰 uid=1000 的 GUI 核心。

**兜底 xray 启动加固（全是 09-08 事故的直接产物）**
1. **geosite.dat 符号链接必须存在**（A 级根因，见 §9 事故记录）：
   xray 按**可执行文件所在目录**找 geosite.dat，即 `bin/xray/geosite.dat`，
   而 v2rayN 发行版把 .dat 放在 `bin/`。缺链接 → 兜底 xray 秒退。
   看门狗每次拉兜底前自动补链（防 EDR 还原/重装丢失）。
2. **stderr 落盘**：`nohup xray run -c $CFG >> /home/<user>/.hermes/logs/v2rayn_fallback_xray.log`
   （此前 stderr 被丢弃，死因无法复盘——直接导致 14:15~14:25 三次 RECOVERY_FAILED 查无死因）。
3. **启动前 JSON 校验**：`config.json` 必须可 `json.load`（GUI 运行时正被 GUI 改写，
   可能读到半截 JSON）；失败重试 1 次。
4. **port_up 探测带超时**：python socket 3s + 8s 硬顶（bash `/dev/tcp` 无超时会永久
   挂死 cron tick——09-08 实测复现并修复）。

## 4. 每日 08:29 自动切换 + 订阅更新流程

```
cron 29 0 * * * (UTC) = 北京 08:29
v2rayn_autoswitch.sh:
  1. 确保 runner 容器存活 (不在→start; 没有→按 §2 命令重建)
  2. 重放 3 个幂等补丁, 任一失败 → 跳过本次 + 飞书告警 (防坏库)
  3. docker exec -u 0: cd autoswitch && ./run.sh   (flock 防重叠)
     ├─ 探测 GUI 是否在跑 (pgrep ./v2rayN)
     │   ├─ 在 → 温柔模式: 不杀 GUI、不重启 GUI、绝不 kill 任何 xray
     │   │        照常: 探测→选 S1→切 IndexId→经 S1 更新订阅→复检→写库
     │   │        结束时只保证 10808 有人服务 (谁持有都不动)
     │   └─ 不在 → 原流程: SIGTERM 停 v2rayN→…→结束时重启 v2rayN
  4. 结果处理:
     ├─ exit 0  → v2rayn_sub_notify.py:
     │             有订阅更新或节点切换才发飞书 (新增/移除节点 diff + 当前节点
     │             + GUI 在跑时提示"需在 GUI 刷新订阅/手动切换才生效");
     │             无变化/ dry_run / last_result 超 2 小时 → 静默
     │             节点名单快照: autoswitch/node_snapshot.json (diff 基线)
     ├─ exit 75 → flock 被占, 静默
     └─ 其他    → 飞书告警 (退出码 + last_result 摘要 + 日志尾部, 失败重试 1 次)
```

**两个诚实保留（GUI 运行时的限制，无法绕过）**
1. 订阅更新后 GUI 里的节点列表要**手动刷新/重开**才可见新节点（不能不杀进程操控 GUI 内部）。
2. 若某次交接后 GUI 核心没绑上 10808，需要在 GUI 点一次"重启核心"（飞书会提醒）。

## 5. 通知体系（全部飞书直发 deliver_feishu.py，不依赖 cron 自动投递）

| 场景 | 内容 | 频控 |
|---|---|---|
| 交接成功（GUI 核心接管 10808） | ✅ 已交接，助手退出端口管理 | 事件触发 |
| 交接熔断（GUI 核心连续 3 次未接管） | ⚠️ 兜底持有中，切回需点"重启核心" | 仅触发当刻一次 |
| 空窗 120s 超期拉回兜底 | ⚠️ GUI 核心未绑上，已拉回兜底 + 处理建议 | 60min 告警冷却 |
| 10808 掉线（GUI 在跑） | ⚠️ 兜底临时维持，下 tick 让位 | 60min 冷却 |
| 代理自动恢复（S4 兜底 / run.sh / GUI 独占） | ✅ 已恢复 + 节点 | 事件触发 |
| 彻底失败（兜底+run.sh 均失败） | ⚠️ 需人工 + 日志路径 | 60min 冷却 |
| 08:29 订阅更新成功 | 📡 节点 diff + 当前节点 + GUI 提示 | 有变化才发 |
| 08:29 失败 | ⚠️ 退出码 + 摘要 + 日志尾部 | 每次失败 |

## 6. 启动 / 停止 / 日常操作

### 6.1 停止（分级，按需）

| 想停什么 | 操作（本机 Hermes 环境） | 影响 |
|---|---|---|
| 停 08:29 自动切换（保代理保活） | 对 Hermes 说"暂停 autoswitch 定时任务"（job `7fb119005b5b`） | 不再自动切节点/更新订阅，代理不受影响 |
| 停看门狗（停保活与交接） | 对 Hermes 说"暂停看门狗"（job `bf5966089aa9`） | 兜底 xray 死了没人拉；GUI 开着则基本无感 |
| 停兜底 xray（GUI 自己接管/不需要助手代理） | 见 6.3 精确 kill 命令 | GUI 核心能绑上 10808 就无缝；否则代理断 |
| 全部停 | 上两行 + `docker stop v2rayn-switch-runner` | 宿主 GUI（若开着）完全不受影响 |

> 新机器（系统 cron 版，见 §8 步骤 8）：`crontab -e` 注释对应行即可；
> 停兜底 xray 同 6.3。

### 6.2 恢复
按 6.1 反操作。runner 容器 `--restart unless-stopped`，docker daemon 重启后自愈。

### 6.3 精确 kill 兜底 xray（**严禁 `pkill xray`，会误杀 GUI 核心**）
```bash
# 只列 uid=0 的 xray (我方兜底); uid=1000 的是 GUI 核心, 不碰
for p in $(pgrep -ax xray | cut -d' ' -f1); do
  [ "$(awk '/^Uid:/{print $2}' /proc/$p/status)" = "0" ] && echo "kill $p"
done
# 确认输出只有你预期的 pid 后再执行 kill
```
（看门狗内部即用此逻辑；`kill_fallback` 先 TERM 等 2s 再 KILL，按 PID 精确。）

### 6.4 30 秒日常体检
```bash
# ① 代理是否可用 (期望 204 + <2s)
curl -x socks5h://127.0.0.1:10808 -o /dev/null -s -w '%{http_code} %{time_total}s\n' \
  --max-time 10 https://www.google.com/generate_204
# ② 10808 是谁的 (gui=你的GUI核心 / fallback=助手兜底)
docker exec -u 0 v2rayn-switch-runner \
  python3 /home/<user>/.hermes/scripts/v2rayn_owner.py 10808
# ③ 最近一次自动切换结果
python3 -c "import json;d=json.load(open('/home/<user>/v2rayN-linux-64/autoswitch/last_result.json'));print({k:d.get(k) for k in ('ts','selected','final_server','sub_updated','gentle','exit_code')})"
```

## 7. 诊断手册（按症状）

| 症状 | 第一步 | 然后 |
|---|---|---|
| 代理不可用 | 6.4 ①② 组合判定 | owner=fallback→`tail /home/<user>/.hermes/logs/v2rayn_fallback_xray.log`；owner=gui→节点本身问题（GUI 里切节点）；owner=none→看 `v2rayn_guard.log` 最近 20 行 |
| 收到"交接熔断"飞书 | GUI 界面点"重启核心"（或重选节点） | 核心起来后助手下一分钟自动让位；反复无效→关 GUI 全交兜底 |
| 兜底 xray 反复死 | `tail v2rayn_fallback_xray.log` | 90% 是 `bin/xray/geosite.dat` 符号链接没了：`ln -sf ../geosite.dat bin/xray/geosite.dat`（+geoip.dat）；其次是 config.json 被 GUI 写坏 |
| 看门狗不动作 | `tail -20 v2rayn_guard.log` + `cat v2rayn_guard.state` | state 卡 `free_window` → GUI 核心没绑上，走"交接熔断"行；日志很久没新增 → Hermes cron 是否被暂停/网关是否在线 |
| 08:29 没跑 | `tail v2rayn_autoswitch.log` | 有"补丁应用失败"→ 手动跑补丁脚本看报错；`exit 75` 是 flock 防重叠正常跳过 |
| autoswitch.py 像被还原 | `grep -c GENTLE_MODE_PATCH_V2 autoswitch.py`（应为 ≥1） | 为 0 说明被还原了——**不用手动修**，下次运行前封装脚本会自动重放补丁；想立即恢复就手动跑一遍三个补丁脚本 |
| GUI 打开后助手一直提示 | `v2rayn_owner.py 10808` | owner=fallback 且 state=free_window → GUI 核心没绑上：GUI 点"重启核心"；看 v2rayN 的 Verror 日志确认核心报错 |

**关键日志位置**
| 日志 | 内容 |
|---|---|
| `/opt/data/scripts/logs/v2rayn_guard.log`（= 宿主 `/home/<user>/.hermes/scripts/logs/`） | 看门狗每 tick 决策（含 HANDOFF/空窗/恢复/失败） |
| `…/v2rayn_guard.state` | 状态机状态（STATE/PREV/HANDOFF_FREE_SINCE/HANDOFF_FAILS/ALERT_TS） |
| `…/v2rayn_autoswitch.log` | 08:29 每次运行（补丁结果 + run.sh 输出 + 通知结果） |
| `/home/<user>/v2rayN-linux-64/autoswitch/logs/auto-YYYYMMDD.log` | 主逻辑全过程（探测/切换/订阅） |
| `/home/<user>/.hermes/logs/v2rayn_fallback_xray.log` | **兜底 xray stderr**（死因第一现场） |
| `autoswitch/last_result.json` | 最近一次结果摘要（通知数据源） |

## 8. 新 Ubuntu 部署（从零到全自动）

> 参考环境：Ubuntu 22.04/24.04，有显示器的用户机（要开 v2rayN GUI），有 docker。
> 下文路径以 `/home/<user>/v2rayN-linux-64` 为 v2rayN 目录；Hermes 相关步骤
> 可跳过，走"无 Hermes 最小版"（§8 步骤 8b）。

### 8.1 前置
```bash
sudo apt update && sudo apt install -y python3 docker.io libicu70   # libicu 版本按系统
sudo usermod -aG docker $USER && newgrp docker
timedatectl set-timezone Asia/Shanghai     # 系统时区北京时间
```

### 8.2 步骤
1. **装 v2rayN**：下载 `v2rayN-linux-64` 解压到 `/home/<user>/v2rayN-linux-64`；
   手动 `./v2rayN`，导入订阅（ss:// 或 vless:// 均可），确认某节点下 10808 出网 204：
   ```bash
   curl -x socks5h://127.0.0.1:10808 -o /dev/null -s -w '%{http_code}\n' --max-time 10 https://www.google.com/generate_204
   ```
2. **建 geosite 符号链接**（不做 → 兜底 xray 永远起不来，见 §9）：
   ```bash
   cd /home/<user>/v2rayN-linux-64/bin/xray
   ln -sf ../geosite.dat geosite.dat
   ln -sf ../geoip.dat geoip.dat
   ```
3. **建 runner 容器**（root exec 通道；镜像任意可用 linux 镜像即可，
   本环境用 hermes-agent:local 只是顺手，与功能无关）：
   ```bash
   docker run -d --name v2rayn-switch-runner --restart unless-stopped \
     --pid=host --network=host --user 1000:1000 \
     --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
     -v /home/<user>:/home/<user> \
     --entrypoint /usr/bin/tail <IMAGE> -f /dev/null
   docker exec -u 0 v2rayn-switch-runner id   # 应输出 uid=0(root)
   ```
   > 两个 `--security-opt unconfined` 是**必需**的：缺了容器内 root 给宿主
   > uid=1000 进程发信号会被拒（09-07 实测）。
   > 若用户 uid 不是 1000，把 `--user 1000:1000` 与脚本里的 uid 判定
   > （`v2rayn_owner.py`、`kill_fallback` 中的 `= "0"` 过滤）按实际调整。
4. **部署 autoswitch 目录**：把 `autoswitch/`（autoswitch.py、run.sh、config.conf）
   放到 `/home/<user>/v2rayN-linux-64/autoswitch/`，改 `config.conf` 的
   `v2rayn_dir` 和 `prefer_after_update`（你的优先节点名）。
5. **部署补丁与脚本**：把 8 个脚本（§2 清单中 "Hermes scripts/" 的 8 个）放到固定目录：
   - 有 Hermes：`/home/<user>/.hermes/scripts/`（随 /opt/data 持久卷）；
   - 无 Hermes：`/opt/v2rayn-ops/`。
   无 Hermes 时把脚本里的 `DELIV`/通知调用与 `v2rayn_autoswitch.sh` 的 ensure_runner
   保持原样即可，路径用 8.3 对照表替换。
6. **飞书通知（可选但强烈建议）**：`deliver_feishu.py` 需要
   `FEISHU_APP_ID`/`FEISHU_APP_SECRET`（自建应用，开 im:message 权限，
   把 bot 拉进要收通知的群/单聊，改脚本里 `CHAT_ID`）。无飞书则把
   通知调用改成 `logger`/注释掉，功能不受影响（代理保活/切换照常）。
7. **手动验证一次**（先 dry-run 后正式）：
   ```bash
   docker exec -u 0 v2rayn-switch-runner bash -c \
     "cd /home/<user>/v2rayN-linux-64/autoswitch && ./run.sh --dry-run"
   docker exec -u 0 v2rayn-switch-runner bash -c \
     "cd /home/<user>/v2rayN-linux-64/autoswitch && ./run.sh"
   cat /home/<user>/v2rayN-linux-64/autoswitch/last_result.json
   ```
   期望：`exit_code=0`、`final_server` 非空、6.4 ① 出 204。
8. **挂定时**：
   - **8a 有 Hermes**：让 Hermes 建两个 cron job（`no_agent=true`）：
     看门狗 `* * * * *`（跑 v2rayn_proxy_guard.sh）、
     autoswitch `29 0 * * *`（跑 v2rayn_autoswitch.sh；Hermes 时区为 UTC，
     北京 08:29 = UTC 00:29；若 Hermes config 时区非 UTC 自行折算）。
   - **8b 无 Hermes（系统 cron 最小版）**：
     ```bash
     crontab -e
     * * * * * /opt/v2rayn-ops/v2rayn_proxy_guard.sh >/dev/null 2>&1
     29 8 * * * /opt/v2rayn-ops/v2rayn_autoswitch.sh >/dev/null 2>&1
     ```
     （脚本内已 `export TZ=Asia/Shanghai`；系统 cron 用本地时间 8:29。）
9. **故障演练验收（全过才算部署完成）**：
   - 杀兜底 xray（§6.3）→ ≤65s 看门狗自动拉起，204 恢复；
   - 开着 GUI 跑一次 08:29 封装 → GUI 进程不死、10808 归属不变（owner=gui）、
     `last_result.json` 有 `gentle: true`；
   - 关 GUI → 看门狗 ≤65s 内拉兜底接管，204 恢复。

### 8.3 路径对照表（有 Hermes 时）

| 概念 | Hermes 容器内 | 宿主机 | runner 容器内 |
|---|---|---|---|
| 脚本目录 | `/opt/data/scripts/` | `/home/<user>/.hermes/scripts/` | `/home/<user>/.hermes/scripts/` |
| v2rayN 目录 | `/host-home/v2rayN-linux-64/`（**只读**，仅看） | `/home/<user>/v2rayN-linux-64/` | `/home/<user>/v2rayN-linux-64/`（可写） |
| 飞书凭据 | `/opt/data/.env` | `/home/<user>/.hermes/.env` | 同左（deliver_feishu.py 三路径自适应） |

> 写宿主文件一律走 `docker exec -u 0 v2rayn-switch-runner`（runner 的
> /home/<user> 挂载可写）；不要写 Hermes 的 `/host-home`（只读挂载）。

## 9. 事故记录（2026-09-08 14:10~14:32，代理断 ~20 分钟）

**现象**：用户 GUI 打开后代理不可用；看门狗 3 个 tick 全部 RECOVERY_FAILED。

**根因（均 A 级证据）**
1. 温柔模式 V1 假设"GUI 存在 = GUI 持有 10808"，实际 GUI 核心从未绑上 10808
   （被兜底占着）→ 杀兜底后 10808 裸奔。
2. 看门狗升级路径跑完整 run.sh → gentle 分支又杀兜底 → 自杀循环。
3. 14:15 起兜底 xray 每次拉起即死，真凶 = **geosite.dat 符号链接缺失**
   （§3 第 1 条）；当时 stderr 被丢弃无法复盘，靠 09-08 17:00 的
   临时端口复现实验钉死。

**衍生的三条铁律（已固化进代码/skill）**
1. 任何"让出端口"操作前必须先**确认目标进程确实持有该端口**（inode 反查），
   不能仅凭进程存在就假设。
2. 兜底 xray 的 stderr 必须落盘，不能丢弃。
3. 看门狗升级路径不能包含"杀兜底"逻辑（防自杀循环）。

---
*附录二完。本文档随实现演进更新；修改组件后请同步 §2 清单行数与 §6/§7 命令。*
