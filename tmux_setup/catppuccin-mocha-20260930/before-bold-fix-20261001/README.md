# Catppuccin Mocha：iTerm2 + tmux 配色备份

记录时间：2026-09-30（Asia/Shanghai）

这份备份保存当前 iTerm2 和服务器宿主机 tmux 的配色。容器内配置没有包含在本备份中，也不需要改容器文件。

## 文件

- `iTerm2-Catppuccin-Mocha.itermcolors`：iTerm2 可导入的颜色预设，含深色背景、前景、ANSI 16 色、光标和高对比度选区颜色。
- `tmux-colors.conf`：tmux 3.4 的配色片段，含状态栏、窗口标签、分屏边框、复制模式和 truecolor 设置。

## 当前配色要点

- 背景：`#1E1E2E`；正文：`#CDD6F4`。
- 常规 ANSI 黑色调亮为 `#8991A7`，亮黑为 `#A6ADC8`，避免黑字贴近深色背景。
- iTerm2 选区为蓝底 `#89B4FA`、深色字 `#1E1E2E`。
- iTerm2 Profile 的 `Minimum Contrast` 设为 60（中等），用于提亮应用发出的近黑 RGB 字；此选项不包含在 `.itermcolors` 文件中，见 `iterm2-profile-settings.md`。
- tmux 复制标记同样使用蓝底深字；未使用红底或白底。

## 导入 iTerm2

打开 iTerm2 设置 → Profiles → Colors → Color Presets → Import，选择 `iTerm2-Catppuccin-Mocha.itermcolors`。然后在目标 Profile 的 Color Presets 菜单中选择该预设。

## 应用 tmux 配色

tmux 服务端运行在服务器宿主机的 `mac` 用户下。可在宿主机执行：

```sh
tmux source-file /home/mac/macperson/computer_tools_backup/tmux_setup/catppuccin-mocha-20260930/tmux-colors.conf
```

将来需要永久使用时，把片段内容合并到宿主机 `/home/mac/.tmux.conf`。容器内没有 tmux；本文件不修改容器设置。

## 容器终端颜色提示

某些 `docker exec -it` 启动方式会把终端类型设为 `xterm`。若容器内程序因此不启用 256 色，可仅在当前 shell 手动运行：

```sh
export TERM=xterm-256color COLORTERM=truecolor
```

这只是当前 shell 的环境变量，不会写入容器配置。
