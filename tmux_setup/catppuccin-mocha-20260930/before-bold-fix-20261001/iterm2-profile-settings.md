# iTerm2 Profile 单独设置

`.itermcolors` 预设不保存 iTerm2 的 Profile 级 `Minimum Contrast` 滑块，因此当前 Profile 还需使用以下设置：

- Profile：`Catppuccin Mocha`
- Minimum Contrast：`80`（0–100）
- Background：`#1E1E2E`（保持深色）
- Foreground：`#CDD6F4`
- Selection：`#89B4FA`，selected text：`#1E1E2E`

最小对比度会在前景与背景太接近时把前景推向黑或白；100 会把所有文字变成纯黑或纯白，因此这里设为 80，优先保证低对比文字可读。设置位置：iTerm2 Settings → Profiles → Colors → Minimum Contrast。

此设置只改本机 iTerm2 Profile；没有修改容器配置。
