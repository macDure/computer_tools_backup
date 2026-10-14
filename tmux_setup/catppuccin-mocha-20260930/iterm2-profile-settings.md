# iTerm2 配色设置

更新日期：2026-10-01（Asia/Shanghai）。

当前默认 Profile：`Catppuccin Mocha Readable`。

| 设置 | 当前值 |
| --- | --- |
| Background Color | #1E1E2E |
| Foreground Color | #CDD6F4 |
| Bold Color（备用值） | #CDD6F4 |
| 独立加粗颜色（内部键 Use Bright Bold） | 关闭 |
| Use Bold Font | 开启 |
| Use Separate Colors for Light and Dark Mode | 关闭 |
| Minimum Contrast | 界面 30，内部 0.3 |
| Faint Text Alpha | 1.0 |
| ANSI 0 / ANSI 8 | #8991A7 / #A6ADC8 |
| ANSI 1 / ANSI 9 | #B4BEFE / #CBA6F7（淡紫色） |
| Selection / Selected Text | #89B4FA / #1E1E2E |

Light/Dark 保留字段已同步为同一套深色配色。

2026-10-01 已读取当前 iTerm2 会话和实际新开的默认标签，两者均使用
`Catppuccin Mocha Readable`，加粗色与正文色相同。临时配置接口开关已关闭，
其本地 Unix 连接入口已移除并确认不可连接。

先前只改 macOS preferences 文件，没有刷新 iTerm2 内存里的 Profile，
因此新会话仍使用旧的黑色加粗字。当前方案使用 iTerm2 官方的动态 Profile
加载机制，完整 JSON 为实际生效的配置来源。
