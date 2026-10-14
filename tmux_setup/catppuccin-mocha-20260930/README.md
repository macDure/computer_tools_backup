# Catppuccin Mocha Readable：iTerm2 + tmux 配色备份

更新日期：2026-10-01（Asia/Shanghai）。

保存本机 iTerm2 和服务器宿主机 tmux 的可读深色配色。

## 文件

- `Catppuccin-Mocha-Readable.json`：实际使用的完整动态 Profile 配置。
- `iTerm2-Catppuccin-Mocha-profile.json`：相同 Profile 的通用 JSON 导出。
- `iTerm2-Catppuccin-Mocha.itermcolors`：颜色预设。
- `iterm2-profile-settings.md`：开关和值，以及本次检查结果。
- `tmux-colors.conf`：服务器宿主机 tmux 的颜色与 truecolor 配置。

## 当前生效方案

默认 Profile 为 `Catppuccin Mocha Readable`。
背景 #1E1E2E，正文和加粗字 #CDD6F4。加粗字继承正文色，保留加粗字体。
关闭明暗模式的独立配色。ANSI 黑色和亮黑提高亮度，ANSI 红色槽位改为淡紫。
Minimum Contrast 的内部值为 0.3（界面显示 30），不能填写 30、60 或 80 作为内部值。

当前会话和实际新开的默认标签均已检查，浅色加粗字配置生效。

## 恢复本机 iTerm2

1. 把 `Catppuccin-Mocha-Readable.json` 复制到 Mac 的
   `~/Library/Application Support/iTerm2/DynamicProfiles/`。
   iTerm2 运行时会自动加载它。
2. 打开 iTerm2 Settings → Profiles，选择 `Catppuccin Mocha Readable`，
   在 Other Actions 菜单中选择 Set as Default，将它设为默认 Profile。
3. 已经打开的终端会话需要切换到此 Profile。通过 Session → Edit Session
   中的 Change Profile 选择 `Catppuccin Mocha Readable`，或新开默认标签。

只导入 `.itermcolors` 不会恢复所有开关；完整方案优先使用 JSON。
不要依赖在 iTerm2 运行时直接改 preferences 文件来更新正在使用的 Profile。

## 恢复宿主机 tmux

在服务器宿主机的 mac 用户下执行：

```sh
tmux source-file /home/mac/macperson/computer_tools_backup/tmux_setup/catppuccin-mocha-20260930/tmux-colors.conf
```

宿主机永久配置位于 `/home/mac/.tmux.conf`。这次修正本机 iTerm2 的显示配置，
容器无需配置修改。
