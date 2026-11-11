# 本机 Codex pane 清单

记录日期：2026-11-10（Asia/Shanghai）
本次读取到 16 个正在运行 Codex 的 pane。

这份清单用于在 tmux 布局恢复后辨认 Codex pane 的位置、工作目录、对话 ID 和当前任务线索。10 个 ID 是从对应 pane 的 Codex 进程 `resume` 启动参数中读取的；其余 6 个 pane 的进程参数没有暴露 ID。此表是当时状态的记录；window/pane 编号、标题和工作目录之后可能变化。

| Session | Window | Pane | tmux 定位目标 | 工作目录 | Pane 标题 / 任务线索 | Codex 对话 ID |
| --- | --- | ---: | --- | --- | --- | --- |
| `control` | 0 `control当前功能开发` | 2 | `control:0.2` | `/home/mac/mkcode/application-core/modules/control` | 了解对话内容 | 未能读取 |
| `control` | 2 `底盘适配工具开发` | 0 | `control:2.0` | `/home/mac/mkcode/application-core` | 梳理新车适配参数与工具 | `01a15339-b122-7372-bca3-289b04441cdd` |
| `control` | 2 `底盘适配工具开发` | 1 | `control:2.1` | `/home/mac/mkcode/application-core/modules/control` | 整理三类平台测试指令文档 | `01a182e2-9a1a-7580-83bf-a31ab0bf9430` |
| `control` | 3 `control 代码管理` | 1 | `control:3.1` | `/home/mac/mkcode/application-core` | 新增清理提交并保留本地文件 | `01a162f4-845d-74e1-9e03-c91425a3d69e` |
| `other` | 0 `codex-tmux配置` | 0 | `other:0.0` | `/home/mac` | 配置 tmux 滚轮翻页 | `01a0a53a-ca98-7d73-9294-c0515984ab63` |
| `other` | 1 `codex-local-shuimu` | 2 | `other:1.2` | `/home/mac/macperson/stock_research_mac` | 运行暂存集校验 | `01a0eb6f-517e-70c0-a19a-1934a6d76119` |
| `other` | 3 `computer_tools_backup` | 1 | `other:3.1` | `/home/mac/macperson/computer_tools_backup` | 检查并配置 MKVPN | 未能读取 |
| `other` | 4 `stock` | 0 | `other:4.0` | `/home/mac/macperson/stock` | 整理并规划 stock 部署 | 未能读取 |
| `other` | 4 `stock` | 3 | `other:4.3` | `/home/mac/macperson/stock` | 接续完成agent剩余工作 | 未能读取 |
| `other_modules` | 0 `dreamview代码管理` | 2 | `other_modules:0.2` | `/home/mac/mkcode/application-core/modules` | 检查 sim_control 分支差异 | `01a12df5-997c-73a1-b36a-e63e3c9e6c7f` |
| `planning` | 0 `codex-planning-ilqr` | 1 | `planning:0.1` | `/home/mac/mkcode/application-core` | 完成对话未完工作 | 未能读取 |
| `planning` | 0 `codex-planning-ilqr` | 2 | `planning:0.2` | `/home/mac/mkcode/application-core` | 切换容器2代码库至master并rebase | `01a1613e-8831-7be0-afc7-f423041a252c` |
| `planning` | 0 `codex-planning-ilqr` | 4 | `planning:0.4` | `/home/mac/mkcode/application-core/modules/planning` | Clarify /us request | `01a17c6d-42d2-7d23-a3d4-f6869b67e7e7` |
| `planning` | 2 `codex-planning代码闭环流程` | 0 | `planning:2.0` | `/home/mac/mkcode/application-core` | 梳理并落地planning流程 | `01a09e83-257b-7ec1-9a49-c1b44ad7c218` |
| `planning` | 2 `codex-planning代码闭环流程` | 1 | `planning:2.1` | `/home/mac/mkcode/application-core` | 研究仿真文档并分析容器用法 | `01a143d7-26b4-7420-830f-4d317dc7af6b` |
| `ranger_mini_v3_old` | 0 `mini_v3多窗口文件管理` | 3 | `ranger_mini_v3_old:0.3` | `/home/mac` | 调试planning紧急停车决策 | 未能读取 |

## 恢复时使用

`tmux-resurrect` 用于恢复 session/window/pane 布局和工作目录；恢复后可按表中的 `tmux 定位目标` 找到相应 pane。例如：

```bash
tmux select-pane -t 'planning:0.1'
```

pane 标题只用于辨认当时正在做的事情，不保证 Codex 恢复后仍显示相同内容。10 个对话 ID 是从同一 pane 上 Codex 进程的 `resume` 启动参数直接确认的；其余 6 个启动参数没有出现 UUID，不能根据工作目录或标题猜测 ID。

恢复布局后，可用 `tmux select-pane -t 'session:window.pane'` 定位 pane，再对已记录 ID 的行执行 `codex resume <对话ID>`。标为“未能读取”的 6 个 pane 需要从 Codex 会话历史中另行确认 ID。
