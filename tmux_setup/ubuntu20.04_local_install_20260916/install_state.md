# Ubuntu 20.04 本机 tmux 安装备份

记录时间：2026-09-16（Asia/Shanghai）

## 系统与软件包

- 系统：Ubuntu 20.04.6 LTS（focal）
- tmux 包：`3.0a-2ubuntu0.4`
- tmux 版本：`tmux 3.0a`
- tmux 路径：`/usr/bin/tmux`
- xclip 包：`0.13-1`
- xclip 路径：`/usr/bin/xclip`

## 图形会话

- 外部终端：Terminator，X11 会话
- `DISPLAY=:1`
- `XAUTHORITY=/run/user/1000/gdm/Xauthority`
- `WAYLAND_DISPLAY`：未设置
- 当前终端 terminfo：包含 `Ms` OSC 52 能力

## 已安装文件

- 实际生效配置：`/home/mac/.tmux.conf`
- 本目录中的配置副本：`.tmux.conf`
- 配置权限：`600`
- 旧配置备份目录：`/home/mac/.tmux-config-backups/`
- 本次首次安装时生成的旧配置备份：`.tmux.conf.20260916_223112`
- 自动选择脚本回归安装生成的备份：`.tmux.conf.20260916_224112`

## 20.04 兼容差异

Ubuntu 20.04 的 tmux 3.0a 不支持 24.04/较新 tmux 使用的 server-level `copy-command`。本机配置将完整的 xclip 命令直接传给 5 个 `copy-pipe-and-cancel` 绑定，功能保持一致：鼠标拖选、`Enter`、`y` 复制到系统剪贴板，并保留 tmux 内部 buffer。
