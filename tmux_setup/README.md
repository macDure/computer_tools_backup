# tmux 配置、终端剪贴板与代理接入备份

整理日期：2026-09-30（Asia/Shanghai）

本目录合并了原 `tmux_setup_20260916`（tmux 配置与迁移指南）和
`tmux_setup_20260920`（代理自动接入说明与修改快照）。以后 tmux 相关备份统一放在这里。

## tmux 配置与迁移

- [tmux.conf](./tmux.conf)：本机 Ubuntu 24.04/tmux 3.4 配置，包含滚轮历史、系统剪贴板、Catppuccin Mocha 配色和 session 自动恢复/登录启动；使用 server-level `copy-command` + xclip，并关闭可能冲突的 OSC 52。目标机需按其 `DISPLAY`/`XAUTHORITY` 调整剪贴板命令。
- [tmux.conf.ubuntu20.04](./tmux.conf.ubuntu20.04)：Ubuntu 20.04 的兼容配置，直接向 `copy-pipe-and-cancel` 传入 xclip 命令。
- [install_tmux_config.sh](./install_tmux_config.sh)：自动探测 `copy-command` 支持情况，选择对应配置；备份旧配置，安装低优先级保存包装脚本并重载当前 server。
- [tmux-resurrect-save-low-priority](./tmux-resurrect-save-low-priority)：供 Continuum 定时保存使用，以低 CPU／磁盘优先级运行；手动 `Ctrl-b Ctrl-s` 不受影响。
- [tmux_setup_guide.md](./tmux_setup_guide.md)：完整迁移、使用、验证和排障文档。
- tmux-resurrect + tmux-continuum：每 60 分钟以低优先级自动保存 session/window/pane 布局；Linux 用户登录时由 systemd 自动启动 tmux server，并自动恢复最近快照。
- [session_layout_snapshot](./session_layout_snapshot/)：2026-10-19 16:28 导出的本机最新 Resurrect 布局快照及 `last` 链接；包含 7 个 session、29 个 window、89 个 pane。快照含工作目录和 pane 命令，只应保存在私有仓库；新电脑恢复步骤见迁移指南。
- [ubuntu20.04_local_install_20260916](./ubuntu20.04_local_install_20260916/)：本机 Ubuntu 20.04 的实际安装状态和生效配置备份。
- [catppuccin-mocha-20260930](./catppuccin-mocha-20260930/README.md)：独立配色片段及 iTerm2 配色资源；主 `tmux.conf` 已包含本机 tmux 配色，Ubuntu 20.04 兼容配置不包含不兼容的配色选项。

## 终端代理自动接入

- [auto_proxy_startup_guide.md](./auto_proxy_startup_guide.md)：普通终端和 tmux shell 的代理检查、配置、验证与回滚说明。
- [proxy_env.sh.before-auto-system-proxy](./proxy_env.sh.before-auto-system-proxy)：代理自动管理改动前的脚本快照。
- [proxy_env.sh.after-auto-system-proxy](./proxy_env.sh.after-auto-system-proxy)：代理自动管理改动后的脚本快照。

代理 helper 的实际安装位置及 `.bashrc` 加载配置不在本目录内；换电脑时按代理指南检查并迁移对应文件，不要把快照误当成已安装配置。

快速安装：

```bash
bash install_tmux_config.sh
```

脚本会自动选择 Ubuntu 24.04/较新 tmux 配置或 Ubuntu 20.04 兼容配置。安装前请阅读文档中的 `DISPLAY`/`XAUTHORITY` 核对说明；这两个值可能随电脑或图形会话改变。
