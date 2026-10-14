# iTerm2 Profile 设置

更新日期：2026-10-01（Asia/Shanghai）。目标 Profile：`Catppuccin Mocha`。

在 Settings → Profiles → Colors 中确认：

- 关闭 **Bold** 的独立颜色开关，让加粗字继承普通正文颜色。
- Bold Color 的备用颜色为 `#CDD6F4`，普通 Foreground 也是 `#CDD6F4`。
- 关闭 **Use separate colors for light and dark mode**，始终使用深色背景 `#1E1E2E`。
- **Minimum Contrast：30**。内部字段是 `0.3`，有效范围为 `0.0–1.0`；不要把整数 30、60 或 80 直接写入这个字段。
- Selection：`#89B4FA`；Selected Text：`#1E1E2E`。

在 Settings → Profiles → Text 中保留 **Draw bold text in bold font**，文字仍然加粗，只是不再被独立的黑色覆盖。

之前的黑字来自遗留的 Bold Color `#101010`。已修正当前打开的 iTerm2 会话，并读取确认加粗字颜色与浅色正文颜色一致。颜色预设、完整 Profile JSON 和本文记录相互匹配。

配置字段对应关系：

```text
Use Separate Colors for Light and Dark Mode = false
Use Bright Bold = false
Use Bright Bold (Light) = false
Use Bright Bold (Dark) = false
Bold Color / Bold Color (Light) / Bold Color (Dark) = #CDD6F4
Minimum Contrast / Minimum Contrast (Light) / Minimum Contrast (Dark) = 0.3
```

这些设置修改本机终端的显示，容器文件无需改动。
