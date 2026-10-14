# Catppuccin Mocha：iTerm2 + tmux 配色备份

更新日期：2026-10-01（Asia/Shanghai）

这份备份保存本机 iTerm2 和服务器宿主机 tmux 的配色。

## 文件

- `iTerm2-Catppuccin-Mocha.itermcolors`：颜色预设，包含背景、正文、加粗字、ANSI 16 色、光标和选区颜色。
- `iTerm2-Catppuccin-Mocha-profile.json`：完整 iTerm2 Profile 导出，包含配色开关、字体、终端类型和对比度等设置。
- `iterm2-profile-settings.md`：导入颜色预设之后还需确认的 Profile 开关。
- `tmux-colors.conf`：服务器宿主机 tmux 的颜色和 truecolor 配置。
- `before-bold-fix-20261001/`：本次更新前的备份文件，仅用于保留历史。

## 当前设置

- Profile：`Catppuccin Mocha`。
- 背景：`#1E1E2E`；正文：`#CDD6F4`。
- 关闭独立的加粗字颜色，让加粗字继承正文颜色；备用 Bold Color 也统一为 `#CDD6F4`。加粗字体仍启用。
- 关闭明暗模式的独立配色，始终使用这套深色背景；保留的明暗颜色字段也已同步。
- Minimum Contrast：界面值 **30**，配置文件内部值 **0.3**。之前的 60/80 说明已撤销。
- ANSI 黑色：`#8991A7`；亮黑：`#A6ADC8`。
- ANSI 红色槽位使用淡紫色；不使用红字或白色背景。
- 选区：蓝底 `#89B4FA`、深色字 `#1E1E2E`。

## 恢复 iTerm2 配色

打开 iTerm2 Settings → Profiles → Colors → Color Presets → Import，导入 `.itermcolors` 文件，再选择这个颜色预设。

颜色预设不保存所有 Profile 开关。按 `iterm2-profile-settings.md` 设置 Bold 开关、明暗配色开关和 Minimum Contrast，避免只恢复颜色而漏掉加粗字设置。

## 恢复宿主机 tmux 配色

在服务器宿主机的 `mac` 用户下执行：

```sh
tmux source-file /home/mac/macperson/computer_tools_backup/tmux_setup/catppuccin-mocha-20260930/tmux-colors.conf
```

永久配置保存在宿主机 `/home/mac/.tmux.conf`。本次黑色加粗字问题在本机 iTerm2 的显示配色中修正，容器配置无需修改。
