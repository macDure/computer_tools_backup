# 当前 tmux 窗口、pane 与路径清单

- 布局与路径采集：2026-11-17 15:35（Asia/Shanghai）
- pane 可见屏幕保存：2026-11-17 15:35
- 共 9 个 session、37 个 window、139 个 pane；其中 18 个 pane 当前运行 Codex，16 个对话 ID 可从快照中的启动命令确认，另外 2 个未能确认。

## 快照与内容文件

- 布局快照：[tmux_resurrect_20261117T153525.txt](./session_layout_snapshot/tmux_resurrect_20261117T153525.txt)，`last` 指向此文件。
- pane 可见屏幕归档：[pane_contents_20261117T153536.tar.gz](./session_layout_snapshot/pane_contents_20261117T153536.tar.gz)，`pane_contents.tar.gz` 指向此归档，内含 139 个 pane 画面。
- `tmux-resurrect` 当前启用 `@resurrect-capture-pane-contents on` 和 `@resurrect-pane-contents-area visible`。
- 归档保存当前可见区域，不含完整 scrollback。恢复画面是静态文本，随后进入新 shell；不会让 Codex、SSH、Apollo 等前台程序继续运行。
- 屏幕归档可能包含终端上显示的内部命令和输出，应保存在私有代码库。

## Session 分布

| Session | Windows | Panes |
| --- | ---: | ---: |
| `control` | 7 | 26 |
| `develop容器` | 5 | 19 |
| `fr_max` | 2 | 20 |
| `other` | 7 | 18 |
| `other_modules` | 5 | 15 |
| `planning` | 7 | 19 |
| `ranger_mini_v3_old` | 1 | 7 |
| `ranger_mini_v4` | 1 | 6 |
| `榆林车` | 2 | 9 |
| **合计** | **37** | **139** |

## Window 分布

| Session | Window | Window 名称 | Panes |
| --- | ---: | --- | ---: |
| `control` | 0 | `control当前功能开发` | 4 |
| `control` | 1 | `control工具调试-容器1` | 5 |
| `control` | 2 | `底盘适配工具开发` | 4 |
| `control` | 3 | `control 代码管理` | 5 |
| `control` | 4 | `canbus-codex` | 4 |
| `control` | 5 | `canbus&control流程建设` | 2 |
| `control` | 6 | `车辆标定工具开发` | 2 |
| `develop容器` | 0 | `本地develop调试多窗口` | 6 |
| `develop容器` | 1 | `本地调试数据log多窗口` | 1 |
| `develop容器` | 2 | `apollo-test容器多窗口develop` | 7 |
| `develop容器` | 3 | `A6000服务器容器多窗口调试` | 4 |
| `develop容器` | 4 | `bash` | 1 |
| `fr_max` | 0 | `ssh多窗口文件处理` | 12 |
| `fr_max` | 1 | `fr_max 多窗口调试` | 8 |
| `other` | 0 | `codex-tmux配置` | 1 |
| `other` | 1 | `codex-local-shuimu` | 3 |
| `other` | 2 | `lenovo-ssh` | 5 |
| `other` | 3 | `computer_tools_backup` | 2 |
| `other` | 4 | `stock` | 4 |
| `other` | 5 | `系统问题` | 1 |
| `other` | 6 | `herness` | 2 |
| `other_modules` | 0 | `dreamview代码管理` | 3 |
| `other_modules` | 1 | `prediction代码管理` | 3 |
| `other_modules` | 2 | `canbus代码管理` | 4 |
| `other_modules` | 3 | `external_command代码管理` | 3 |
| `other_modules` | 5 | `common_msg` | 2 |
| `planning` | 0 | `codex-planning-ilqr` | 4 |
| `planning` | 1 | `agy-回归测试` | 2 |
| `planning` | 2 | `codex-planning代码闭环流程` | 2 |
| `planning` | 3 | `planning代码管理` | 6 |
| `planning` | 4 | `codex-agy-reference_as_path` | 2 |
| `planning` | 5 | `simulation代码管理` | 2 |
| `planning` | 6 | `bash` | 1 |
| `ranger_mini_v3_old` | 0 | `mini_v3多窗口文件管理` | 7 |
| `ranger_mini_v4` | 0 | `bash` | 6 |
| `榆林车` | 0 | `榆林车代码管理` | 5 |
| `榆林车` | 1 | `榆林车实车调试` | 4 |

## 每个 pane 的工作目录与恢复线索

工作目录是采集时 tmux 报告的绝对路径。`tmux target` 可定位 pane，例如 `tmux select-pane -t '榆林车:0.3'`。window/pane 编号会随布局变化；迁移到目录结构不同的电脑时，需要按目标机路径调整。

| Session | Window | Pane | tmux target | 绝对工作目录 | 前台命令 | Codex 对话 ID |
| --- | ---: | ---: | --- | --- | --- | --- |
| `control` | 0 `control当前功能开发` | 0 | `control:0.0` | `/home/mac/mkcode/application-core/data/fr_max_car_record` | `bash` | `—` |
| `control` | 0 `control当前功能开发` | 1 | `control:0.1` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `control` | 0 `control当前功能开发` | 2 | `control:0.2` | `/home/mac/mkcode/application-core/modules/control` | `codex` | `01a1a087-97ec-7a91-8b94-1310c1ee665c` |
| `control` | 0 `control当前功能开发` | 3 | `control:0.3` | `/home/mac/mkcode/apollo_test/application-core/modules/control` | `bash` | `—` |
| `control` | 1 `control工具调试-容器1` | 0 | `control:1.0` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `control` | 1 `control工具调试-容器1` | 1 | `control:1.1` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `control` | 1 `control工具调试-容器1` | 2 | `control:1.2` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `control` | 1 `control工具调试-容器1` | 3 | `control:1.3` | `/home/mac/mkcode/application-core/data/control_reports` | `bash` | `—` |
| `control` | 1 `control工具调试-容器1` | 4 | `control:1.4` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `control` | 2 `底盘适配工具开发` | 0 | `control:2.0` | `/home/mac/mkcode/application-core` | `codex` | `01a15339-b122-7372-bca3-289b04441cdd` |
| `control` | 2 `底盘适配工具开发` | 1 | `control:2.1` | `/home/mac/mkcode/application-core/modules/control` | `codex` | `01a182e2-9a1a-7580-83bf-a31ab0bf9430` |
| `control` | 2 `底盘适配工具开发` | 2 | `control:2.2` | `/home/mac/mkcode/application-core/modules/control` | `bash` | `—` |
| `control` | 2 `底盘适配工具开发` | 3 | `control:2.3` | `/home/mac/mkcode/apollo_test/application-core/modules/control` | `bash` | `—` |
| `control` | 3 `control 代码管理` | 0 | `control:3.0` | `/home/mac/mkcode/application-core/modules/control` | `bash` | `—` |
| `control` | 3 `control 代码管理` | 1 | `control:3.1` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `control` | 3 `control 代码管理` | 2 | `control:3.2` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `control` | 3 `control 代码管理` | 3 | `control:3.3` | `/home/mac/mkcode/apollo_test/application-core/modules/control` | `bash` | `—` |
| `control` | 3 `control 代码管理` | 4 | `control:3.4` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `control` | 4 `canbus-codex` | 0 | `control:4.0` | `/home/mac/mkcode/apollo_test/application-core` | `codex` | `01a1cee8-fa6a-7e92-80fc-94d6d5c91847` |
| `control` | 4 `canbus-codex` | 1 | `control:4.1` | `/home/mac/mkcode/apollo_test/application-core/modules/canbus` | `bash` | `—` |
| `control` | 4 `canbus-codex` | 2 | `control:4.2` | `/home/mac/mkcode/apollo_test/application-core/modules/canbus_vehicle` | `bash` | `—` |
| `control` | 4 `canbus-codex` | 3 | `control:4.3` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `control` | 5 `canbus&control流程建设` | 0 | `control:5.0` | `/home/mac/mkcode/apollo_test/application-core` | `codex` | `01a1def9-74e6-7b80-b165-e3cca2146938` |
| `control` | 5 `canbus&control流程建设` | 1 | `control:5.1` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `control` | 6 `车辆标定工具开发` | 0 | `control:6.0` | `/home/mac/mkcode/application-core/modules/control/tools/vehicle_calibration` | `bash` | `—` |
| `control` | 6 `车辆标定工具开发` | 1 | `control:6.1` | `/home/mac/mkcode/application-core/modules/control` | `codex` | `未能从启动参数读取` |
| `develop容器` | 0 `本地develop调试多窗口` | 0 | `develop容器:0.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `develop容器` | 0 `本地develop调试多窗口` | 1 | `develop容器:0.1` | `/home/mac/mkcode/application-core/data/record` | `bash` | `—` |
| `develop容器` | 0 `本地develop调试多窗口` | 2 | `develop容器:0.2` | `/home/mac/mkcode/application-core/data/fr_max_car_record/2026-10-12-14-35-27_middle` | `bash` | `—` |
| `develop容器` | 0 `本地develop调试多窗口` | 3 | `develop容器:0.3` | `/home/mac/mkcode/application-core/data/record` | `bash` | `—` |
| `develop容器` | 0 `本地develop调试多窗口` | 4 | `develop容器:0.4` | `/home/mac/mkcode/application-core/modules/map` | `bash` | `—` |
| `develop容器` | 0 `本地develop调试多窗口` | 5 | `develop容器:0.5` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `develop容器` | 1 `本地调试数据log多窗口` | 0 | `develop容器:1.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `develop容器` | 2 `apollo-test容器多窗口develop` | 0 | `develop容器:2.0` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `develop容器` | 2 `apollo-test容器多窗口develop` | 1 | `develop容器:2.1` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `develop容器` | 2 `apollo-test容器多窗口develop` | 2 | `develop容器:2.2` | `/home/mac/mkcode/application-core/data` | `bash` | `—` |
| `develop容器` | 2 `apollo-test容器多窗口develop` | 3 | `develop容器:2.3` | `/home/mac/mkcode/apollo_test/application-foundation` | `bash` | `—` |
| `develop容器` | 2 `apollo-test容器多窗口develop` | 4 | `develop容器:2.4` | `/home/mac/mkcode/apollo_test/application-foundation` | `bash` | `—` |
| `develop容器` | 2 `apollo-test容器多窗口develop` | 5 | `develop容器:2.5` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `develop容器` | 2 `apollo-test容器多窗口develop` | 6 | `develop容器:2.6` | `/home/mac/mkcode/apollo_test/application-core/modules` | `bash` | `—` |
| `develop容器` | 3 `A6000服务器容器多窗口调试` | 0 | `develop容器:3.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `develop容器` | 3 `A6000服务器容器多窗口调试` | 1 | `develop容器:3.1` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `develop容器` | 3 `A6000服务器容器多窗口调试` | 2 | `develop容器:3.2` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `develop容器` | 3 `A6000服务器容器多窗口调试` | 3 | `develop容器:3.3` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `develop容器` | 4 `bash` | 0 | `develop容器:4.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 0 | `fr_max:0.0` | `/home/mac` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 1 | `fr_max:0.1` | `/home/mac/mkcode/application-core/data/fr_max_car_record` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 2 | `fr_max:0.2` | `/home/mac` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 3 | `fr_max:0.3` | `/home/mac/mkcode/application-core/data` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 4 | `fr_max:0.4` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 5 | `fr_max:0.5` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 6 | `fr_max:0.6` | `/home/mac` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 7 | `fr_max:0.7` | `/home/mac` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 8 | `fr_max:0.8` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 9 | `fr_max:0.9` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 10 | `fr_max:0.10` | `/home/mac/mkcode/application-core/modules/control` | `bash` | `—` |
| `fr_max` | 0 `ssh多窗口文件处理` | 11 | `fr_max:0.11` | `/home/mac/mkcode/apollo_test/application-core/modules/control` | `bash` | `—` |
| `fr_max` | 1 `fr_max 多窗口调试` | 0 | `fr_max:1.0` | `/home/mac` | `bash` | `—` |
| `fr_max` | 1 `fr_max 多窗口调试` | 1 | `fr_max:1.1` | `/home/mac` | `bash` | `—` |
| `fr_max` | 1 `fr_max 多窗口调试` | 2 | `fr_max:1.2` | `/home/mac` | `bash` | `—` |
| `fr_max` | 1 `fr_max 多窗口调试` | 3 | `fr_max:1.3` | `/home/mac` | `bash` | `—` |
| `fr_max` | 1 `fr_max 多窗口调试` | 4 | `fr_max:1.4` | `/home/mac` | `bash` | `—` |
| `fr_max` | 1 `fr_max 多窗口调试` | 5 | `fr_max:1.5` | `/home/mac/mkcode/application-core/modules/planning` | `bash` | `—` |
| `fr_max` | 1 `fr_max 多窗口调试` | 6 | `fr_max:1.6` | `/home/mac` | `bash` | `—` |
| `fr_max` | 1 `fr_max 多窗口调试` | 7 | `fr_max:1.7` | `/home/mac` | `bash` | `—` |
| `other` | 0 `codex-tmux配置` | 0 | `other:0.0` | `/home/mac` | `codex` | `01a0a53a-ca98-7d73-9294-c0515984ab63` |
| `other` | 1 `codex-local-shuimu` | 0 | `other:1.0` | `/home/mac` | `bash` | `—` |
| `other` | 1 `codex-local-shuimu` | 1 | `other:1.1` | `/home/mac/macperson/stock_research_mac` | `bash` | `—` |
| `other` | 1 `codex-local-shuimu` | 2 | `other:1.2` | `/home/mac/macperson/stock_research_mac` | `codex` | `01a0eb6f-517e-70c0-a19a-1934a6d76119` |
| `other` | 2 `lenovo-ssh` | 0 | `other:2.0` | `/home/mac/mkcode/application-core/data/fr_max_car_record` | `bash` | `—` |
| `other` | 2 `lenovo-ssh` | 1 | `other:2.1` | `/home/mac/macperson/qwen3.8-deploy` | `bash` | `—` |
| `other` | 2 `lenovo-ssh` | 2 | `other:2.2` | `/home/mac` | `bash` | `—` |
| `other` | 2 `lenovo-ssh` | 3 | `other:2.3` | `/home/mac` | `bash` | `—` |
| `other` | 2 `lenovo-ssh` | 4 | `other:2.4` | `/home/mac` | `bash` | `—` |
| `other` | 3 `computer_tools_backup` | 0 | `other:3.0` | `/home/mac/macperson/computer_tools_backup` | `bash` | `—` |
| `other` | 3 `computer_tools_backup` | 1 | `other:3.1` | `/home/mac/macperson/computer_tools_backup` | `codex` | `01a1c4d1-c94e-7ec2-9fea-6ed93bfd80bd` |
| `other` | 4 `stock` | 0 | `other:4.0` | `/home/mac/macperson/stock` | `bash` | `—` |
| `other` | 4 `stock` | 1 | `other:4.1` | `/home/mac/macperson/hermes-agent` | `bash` | `—` |
| `other` | 4 `stock` | 2 | `other:4.2` | `/home/mac/macperson/stock` | `bash` | `—` |
| `other` | 4 `stock` | 3 | `other:4.3` | `/home/mac/macperson/stock` | `bash` | `—` |
| `other` | 5 `系统问题` | 0 | `other:5.0` | `/home/mac` | `codex` | `01a1d02f-c321-7683-b911-353c146bf7e4` |
| `other` | 6 `herness` | 0 | `other:6.0` | `/home/mac/macperson/hermes-agent` | `codex` | `01a09a8e-17f0-7102-85b4-d13e44344899` |
| `other` | 6 `herness` | 1 | `other:6.1` | `/home/mac/macperson/hermes-agent` | `bash` | `—` |
| `other_modules` | 0 `dreamview代码管理` | 0 | `other_modules:0.0` | `/home/mac/mkcode/application-core/modules/dreamview_plus` | `bash` | `—` |
| `other_modules` | 0 `dreamview代码管理` | 1 | `other_modules:0.1` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `other_modules` | 0 `dreamview代码管理` | 2 | `other_modules:0.2` | `/home/mac/mkcode/application-core/modules` | `codex` | `01a12df5-997c-73a1-b36a-e63e3c9e6c7f` |
| `other_modules` | 1 `prediction代码管理` | 0 | `other_modules:1.0` | `/home/mac/mkcode/application-core/modules/prediction` | `bash` | `—` |
| `other_modules` | 1 `prediction代码管理` | 1 | `other_modules:1.1` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `other_modules` | 1 `prediction代码管理` | 2 | `other_modules:1.2` | `/home/mac/mkcode/application-core/modules/map` | `bash` | `—` |
| `other_modules` | 2 `canbus代码管理` | 0 | `other_modules:2.0` | `/home/mac/mkcode/application-core/modules/canbus` | `bash` | `—` |
| `other_modules` | 2 `canbus代码管理` | 1 | `other_modules:2.1` | `/home/mac/mkcode/application-core/modules/canbus_vehicle` | `bash` | `—` |
| `other_modules` | 2 `canbus代码管理` | 2 | `other_modules:2.2` | `/home/mac/mkcode/apollo_test/application-core/modules/canbus` | `bash` | `—` |
| `other_modules` | 2 `canbus代码管理` | 3 | `other_modules:2.3` | `/home/mac/mkcode/apollo_test/application-core/modules/canbus_vehicle` | `bash` | `—` |
| `other_modules` | 3 `external_command代码管理` | 0 | `other_modules:3.0` | `/home/mac/mkcode/application-core/modules/external_command` | `bash` | `—` |
| `other_modules` | 3 `external_command代码管理` | 1 | `other_modules:3.1` | `/home/mac/mkcode/apollo_test/application-core/modules/external_command` | `bash` | `—` |
| `other_modules` | 3 `external_command代码管理` | 2 | `other_modules:3.2` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `other_modules` | 5 `common_msg` | 0 | `other_modules:5.0` | `/home/mac/mkcode/apollo_test/application-core/modules` | `bash` | `—` |
| `other_modules` | 5 `common_msg` | 1 | `other_modules:5.1` | `/home/mac/mkcode/apollo_test/application-foundation` | `bash` | `—` |
| `planning` | 0 `codex-planning-ilqr` | 0 | `planning:0.0` | `/home/mac/mkcode/application-core` | `codex` | `01a1c50a-51e1-79d0-82aa-509570a14f12` |
| `planning` | 0 `codex-planning-ilqr` | 1 | `planning:0.1` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 0 `codex-planning-ilqr` | 2 | `planning:0.2` | `/home/mac/mkcode/application-core/modules/planning` | `bash` | `—` |
| `planning` | 0 `codex-planning-ilqr` | 3 | `planning:0.3` | `/home/mac/mkcode/application-core/modules/planning` | `codex` | `01a17c6d-42d2-7d23-a3d4-f6869b67e7e7` |
| `planning` | 1 `agy-回归测试` | 0 | `planning:1.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 1 `agy-回归测试` | 1 | `planning:1.1` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 2 `codex-planning代码闭环流程` | 0 | `planning:2.0` | `/home/mac/mkcode/application-core` | `codex` | `未能从启动参数读取` |
| `planning` | 2 `codex-planning代码闭环流程` | 1 | `planning:2.1` | `/home/mac/mkcode/application-core` | `codex` | `01a143d7-26b4-7420-830f-4d317dc7af6b` |
| `planning` | 3 `planning代码管理` | 0 | `planning:3.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 3 `planning代码管理` | 1 | `planning:3.1` | `/home/mac/mkcode/application-core/modules/planning` | `bash` | `—` |
| `planning` | 3 `planning代码管理` | 2 | `planning:3.2` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `planning` | 3 `planning代码管理` | 3 | `planning:3.3` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 3 `planning代码管理` | 4 | `planning:3.4` | `/home/mac/mkcode/apollo_test/application-core/modules/planning` | `bash` | `—` |
| `planning` | 3 `planning代码管理` | 5 | `planning:3.5` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 4 `codex-agy-reference_as_path` | 0 | `planning:4.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 4 `codex-agy-reference_as_path` | 1 | `planning:4.1` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 5 `simulation代码管理` | 0 | `planning:5.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 5 `simulation代码管理` | 1 | `planning:5.1` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `planning` | 6 `bash` | 0 | `planning:6.0` | `/home/mac/mkcode/application-core` | `bash` | `—` |
| `ranger_mini_v3_old` | 0 `mini_v3多窗口文件管理` | 0 | `ranger_mini_v3_old:0.0` | `/home/mac` | `bash` | `—` |
| `ranger_mini_v3_old` | 0 `mini_v3多窗口文件管理` | 1 | `ranger_mini_v3_old:0.1` | `/home/mac/mkcode/apollo_test/application-core/modules` | `bash` | `—` |
| `ranger_mini_v3_old` | 0 `mini_v3多窗口文件管理` | 2 | `ranger_mini_v3_old:0.2` | `/home/mac` | `bash` | `—` |
| `ranger_mini_v3_old` | 0 `mini_v3多窗口文件管理` | 3 | `ranger_mini_v3_old:0.3` | `/home/mac` | `codex` | `01a158b4-f0f6-7040-a929-1ca44a1632c8` |
| `ranger_mini_v3_old` | 0 `mini_v3多窗口文件管理` | 4 | `ranger_mini_v3_old:0.4` | `/home/mac/mkcode/apollo_test/application-core/profiles/ranger_mini_v3/modules` | `bash` | `—` |
| `ranger_mini_v3_old` | 0 `mini_v3多窗口文件管理` | 5 | `ranger_mini_v3_old:0.5` | `/home/mac/mkcode/apollo_test/application-core/data/ranger_car_record` | `bash` | `—` |
| `ranger_mini_v3_old` | 0 `mini_v3多窗口文件管理` | 6 | `ranger_mini_v3_old:0.6` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `ranger_mini_v4` | 0 `bash` | 0 | `ranger_mini_v4:0.0` | `/home/mac` | `bash` | `—` |
| `ranger_mini_v4` | 0 `bash` | 1 | `ranger_mini_v4:0.1` | `/home/mac/mkcode/apollo_test/application-core/modules` | `bash` | `—` |
| `ranger_mini_v4` | 0 `bash` | 2 | `ranger_mini_v4:0.2` | `/home/mac/mkcode/apollo_test/application-core/profiles/ranger_mini_v3/modules` | `bash` | `—` |
| `ranger_mini_v4` | 0 `bash` | 3 | `ranger_mini_v4:0.3` | `/home/mac/mkcode/apollo_test/application-core/data/log` | `bash` | `—` |
| `ranger_mini_v4` | 0 `bash` | 4 | `ranger_mini_v4:0.4` | `/home/mac/mkcode/apollo_test/application-core/data/ranger_car_record` | `bash` | `—` |
| `ranger_mini_v4` | 0 `bash` | 5 | `ranger_mini_v4:0.5` | `/home/mac` | `bash` | `—` |
| `榆林车` | 0 `榆林车代码管理` | 0 | `榆林车:0.0` | `/home/mac/mkcode/apollo_test/application-core/profiles` | `bash` | `—` |
| `榆林车` | 0 `榆林车代码管理` | 1 | `榆林车:0.1` | `/home/mac` | `bash` | `—` |
| `榆林车` | 0 `榆林车代码管理` | 2 | `榆林车:0.2` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `榆林车` | 0 `榆林车代码管理` | 3 | `榆林车:0.3` | `/home/mac/mkcode/apollo_test/application-core` | `bash` | `—` |
| `榆林车` | 0 `榆林车代码管理` | 4 | `榆林车:0.4` | `/home/mac` | `codex` | `01a1cdbf-2215-7bf0-a458-2d6583b2ed48` |
| `榆林车` | 1 `榆林车实车调试` | 0 | `榆林车:1.0` | `/home/mac` | `bash` | `—` |
| `榆林车` | 1 `榆林车实车调试` | 1 | `榆林车:1.1` | `/home/mac` | `ssh` | `—` |
| `榆林车` | 1 `榆林车实车调试` | 2 | `榆林车:1.2` | `/home/mac` | `bash` | `—` |
| `榆林车` | 1 `榆林车实车调试` | 3 | `榆林车:1.3` | `/home/mac` | `bash` | `—` |

## 重启或迁移恢复

同一台电脑重新登录后，已启用的用户级 systemd 服务启动 tmux server，Continuum 从 `~/.local/share/tmux/resurrect/last` 恢复布局；配套 `pane_contents.tar.gz` 恢复 pane 可见画面。

迁移到另一台同版本系统时，安装 tmux、TPM、`tmux-resurrect` 和 `tmux-continuum` 后，在首次启动 tmux server 前，将本目录的 `session_layout_snapshot/` 复制到 `~/.local/share/tmux/resurrect/`，并保留 `last`、`pane_contents.tar.gz` 链接及其目标文件。

本次有 18 个 Codex pane，其中 16 个可从快照保存的启动命令确认对话 ID，另外 2 个未能确认。静态画面恢复不等于恢复程序内部状态。
