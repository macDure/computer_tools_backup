# tmux 滚轮翻页与系统剪贴板迁移指南（Ubuntu 24.04/20.04）

## 备份范围

本目录记录 2026-09-16 在本机完成的 tmux 配置及跨版本安装方式，目标是：

1. 在 tmux 窗格中使用鼠标滚轮翻阅历史输出。
2. 鼠标拖选或键盘选择后，复制到外部桌面终端的系统剪贴板。
3. 保留 tmux 内部 buffer 粘贴能力。
4. 将历史输出上限设置为 100000 行。
5. 自动保存并恢复 session、window、pane 名称、布局和工作目录。

配置涉及 tmux 用户配置、TPM、两个恢复插件及 Linux 用户级 systemd 服务；登录系统时由 systemd 自动启动 tmux server，不会自动打开终端窗口。不会修改 shell、Terminator、桌面配置或 SSH 配置。系统依赖仍通过 APT 安装 `tmux`/`xclip`。

## 本机已验证的环境

- Ubuntu 20.04：tmux `3.0a`（本机实际安装版本）
- Ubuntu 24.04 原始环境：tmux `3.4`
- 外部终端：Terminator，X11 会话
- 剪贴板工具：`/usr/bin/xclip`
- 当前图形显示：`DISPLAY=:1`
- 当前 X11 授权文件：`XAUTHORITY=/run/user/1000/gdm/Xauthority`
- tmux 客户端具备 `clipboard` 特性，并有 `Ms` OSC 52 能力

`DISPLAY` 和 `XAUTHORITY` 是当前机器的环境值，换电脑时必须重新核对，不能盲目假定仍然是相同值。

## 文件说明

- `tmux.conf`：与本机 Ubuntu 24.04/tmux 3.4 配置同步，包含滚轮历史、剪贴板、Catppuccin Mocha 配色及恢复/登录启动设置；使用 server-level `copy-command`。
- `tmux.conf.ubuntu20.04`：Ubuntu 20.04/tmux 3.0a 兼容配置，将 xclip 命令直接写入 5 个复制绑定。
- `install_tmux_config.sh`：安全安装脚本；自动探测 `copy-command` 是否可用，覆盖已有 `~/.tmux.conf` 前会先备份到 `~/.tmux-config-backups/`。
- TPM、`tmux-resurrect`、`tmux-continuum`：恢复插件；模板已包含插件配置，换电脑时按本指南安装插件。
- `session_layout_snapshot/`：2026-10-19 16:28 导出的本机最新 Resurrect 快照及 `last` 链接，并保留上一份迁移快照；当前布局含 7 个 session、29 个 window、89 个 pane。跨电脑复刻布局时复制到 `~/.local/share/tmux/resurrect/`。
- `ubuntu20.04_local_install_20260916/`：本机 Ubuntu 20.04 的实际安装状态与配置备份。
- `catppuccin-mocha-20260930/`：独立配色片段和终端配色资源；tmux 3.4 主配置已包含当前配色，Ubuntu 20.04 兼容配置不包含不兼容的颜色选项。
- 本文档：迁移、使用、验证和排障步骤。

## 换电脑快速配置

### 1. 安装依赖

在目标电脑的图形终端中执行：

```bash
tmux -V
command -v xclip
```

如果缺少 tmux 或 xclip（Ubuntu/Debian）：

```bash
sudo apt-get update
sudo apt-get install -y tmux xclip
```

版本差异：Ubuntu 24.04 通常提供较新的 tmux，可使用 `tmux.conf`；Ubuntu 20.04 官方仓库提供 tmux 3.0a，应使用 `tmux.conf.ubuntu20.04`。安装脚本会自动探测 `copy-command` 选项并选择配置，不需要手工判断版本。

### 2. 复制备份目录

将本目录整体复制到目标电脑，例如：

```text
/home/mac/macperson/computer_tools_backup/tmux_setup
```

目标电脑用户名或主目录不同时，目录位置可以改变；安装脚本会按脚本自身位置寻找 `tmux.conf`。

### 3. 安装配置

首次设置 session 自动恢复时，先安装 TPM（若尚未安装）：

```bash
if [ ! -d "$HOME/.tmux/plugins/tpm" ]; then
  git clone --depth 1 https://github.com/tmux-plugins/tpm "$HOME/.tmux/plugins/tpm"
fi
```

然后在备份目录中执行：

```bash
bash install_tmux_config.sh
```

脚本会：

- 探测当前 tmux 是否支持 server-level `copy-command`：支持时使用 `tmux.conf`（Ubuntu 24.04/原始方案），不支持时使用 `tmux.conf.ubuntu20.04`（Ubuntu 20.04 兼容方案）。
- 将已有 `~/.tmux.conf` 备份到 `~/.tmux-config-backups/`。
- 将已有 `~/.local/bin/tmux-resurrect-save-low-priority` 备份后安装低优先级自动保存包装脚本。
- 安装新的 `~/.tmux.conf`，权限设为 `600`。
- 如果 tmux server 正在运行，则自动重载配置。

若不迁移下面的布局快照，启动 tmux 后按 `Ctrl-b`，再按大写 `I`，安装 `tmux-resurrect` 和 `tmux-continuum`。插件安装完成后，再重载一次配置：

```bash
tmux source-file ~/.tmux.conf
```

若要恢复本目录附带的 `session_layout_snapshot/`，请跳过上面需要先启动 tmux 的按键安装流程；在目标电脑第一次启动 tmux **之前**安装插件并复制快照，这样插件可在 server 首次启动时自动读取它。TPM 已安装后，可在普通 shell 中预装两个插件：

```bash
mkdir -p "$HOME/.tmux/plugins"
for plugin in tmux-resurrect tmux-continuum; do
  if [ ! -d "$HOME/.tmux/plugins/$plugin" ]; then
    git clone --depth 1 "https://github.com/tmux-plugins/$plugin" "$HOME/.tmux/plugins/$plugin"
  fi
done
```

确认目标路径不存在（若已有目录，先另行备份），然后复制快照：

```bash
mkdir -p "$HOME/.local/share/tmux"
cp -a /path/to/computer_tools_backup/tmux_setup/session_layout_snapshot \
  "$HOME/.local/share/tmux/resurrect"
```

之后第一次启动 `tmux`，Continuum 会自动恢复快照。若已经先启动了 server、之后才安装插件，则按 `Ctrl-b Ctrl-r` 手动恢复。仅安装配置、不迁移此快照时，仍可用 `Ctrl-b I` 安装插件。

Linux 上的配置包含 `@continuum-boot 'on'`。插件加载后会创建并启用 `~/.config/systemd/user/tmux.service`，让它在该用户登录时自动启动 tmux server。无需设置 systemd linger；这不是开机未登录时运行的系统服务。若目标系统没有 systemd，自动启动部分不会生效。

### 4. 核对图形环境

在目标电脑的外部图形终端中执行：

```bash
printf 'DISPLAY=%s\nXAUTHORITY=%s\n' "${DISPLAY-}" "${XAUTHORITY-}"
```

如果值不是当前配置中的 `:1` 和 `/run/user/1000/gdm/Xauthority`：

- Ubuntu 24.04/较新 tmux：编辑 `~/.tmux.conf` 中 `set -s copy-command` 的值。
- Ubuntu 20.04/tmux 3.0a：编辑 `~/.tmux.conf` 中 5 个复制绑定里的 xclip 命令。

20.04 需要替换的命令片段是：

```tmux
DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority xclip -selection clipboard -i
```

将 `DISPLAY` 和 `XAUTHORITY` 替换为目标电脑图形终端显示的实际值，然后重载：

```bash
tmux source-file ~/.tmux.conf
```

## 当前配置的含义

```tmux
set -g mouse on
```

启用鼠标，包括滚轮翻页、鼠标拖选和窗格操作。

```tmux
set -g history-limit 100000
```

每个窗格最多保留 100000 行历史输出。

本配置通过 `copy-pipe-and-cancel` 调用 `xclip` 写入桌面系统剪贴板，因此关闭 OSC 52：tmux 官方文档提示 `set-clipboard` 与 `copy-pipe` 同时使用时可能冲突。

```tmux
set -s set-clipboard off
```

### Ubuntu 24.04/较新 tmux：原始配置

```tmux
set -s copy-command 'DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority xclip -selection clipboard -i'
```

`copy-command` 是 server-level 选项，让 `copy-pipe-and-cancel` 将选中文字通过 xclip 写入外部系统剪贴板。这是原 Ubuntu 24.04 环境使用的方案。

### Ubuntu 20.04/tmux 3.0a：兼容差异

Ubuntu 20.04 官方仓库的 tmux 3.0a 没有 `copy-command`，而且该版本要求 `copy-pipe-and-cancel` 带命令参数。因此 `tmux.conf.ubuntu20.04` 将完整的 xclip 命令直接传给 5 个复制绑定。该差异只改变配置写法，不改变鼠标复制、键盘复制或 tmux 内部 buffer 粘贴的使用方式。

由于现有 tmux server 可能是在没有 `DISPLAY` 的 SSH 环境中启动，两种配置都显式指定了 X11 环境。

鼠标拖选和复制模式的 `Enter`/`y` 都绑定到了 `copy-pipe-and-cancel`，因此选中文字会写入 tmux buffer，并通过 xclip 写入桌面系统剪贴板。不要再同时启用 OSC 52。

## 使用方法

默认 tmux 前缀键是 `Ctrl-b`。

### 鼠标复制

在窗格中按住鼠标左键拖选文字，松开后自动复制。然后在外部 Terminator 中按：

```text
Ctrl-Shift-V
```

在飞书等普通桌面应用中粘贴请按 `Ctrl-V`；`Ctrl-Shift-V` 是 Terminator 的粘贴快捷键。

### 键盘复制

当前 copy mode 使用 tmux 默认的 emacs 风格按键：

```text
Ctrl-b [       进入复制模式
Ctrl-Space     开始选择
方向键         移动选择
Enter          复制并退出
q              取消复制模式
```

tmux 内部粘贴仍然使用：

```text
Ctrl-b ]
```

不要用 `Ctrl-C` 代替复制，它会向正在运行的程序发送中断信号。
当前默认是 Emacs copy mode，`Enter` 可复制选区；配置中的 `y` 仅在切换到 Vi copy mode 后生效。

## 配置验证

重载后执行：

```bash
tmux show-options -g mouse
tmux show-window-options -g history-limit
tmux show-options -s set-clipboard
```

Ubuntu 24.04/较新 tmux 继续验证原始 server-level 配置：

```bash
tmux show-options -s copy-command
```

Ubuntu 20.04/tmux 3.0a 验证兼容绑定和 terminfo：

```bash
tmux list-keys -T copy-mode | rg 'copy-pipe-and-cancel'
tmux list-keys -T copy-mode-vi | rg 'copy-pipe-and-cancel'
```

预期至少看到：

```text
mouse on
history-limit 100000
set-clipboard off
```

24.04/较新 tmux 还应看到 `copy-command`；两个版本的相关绑定都应包含 `copy-pipe-and-cancel`。本配置使用 xclip，不依赖终端的 `Ms`/OSC 52 能力。

测试 xclip 是否能访问系统剪贴板时，可以只读测试，不改写当前剪贴板：

```bash
DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority \
  xclip -selection clipboard -o >/dev/null \
  && echo 'xclip clipboard connection: OK'
```

## 排障

### 能翻页但不能复制

确认配置中的 `DISPLAY` 与 `XAUTHORITY` 是目标电脑当前图形终端的值，然后执行：

```bash
tmux source-file ~/.tmux.conf
```

24.04/较新 tmux 检查：

```bash
tmux show-options -s copy-command
```

20.04/tmux 3.0a 检查：

```bash
tmux list-keys -T copy-mode | rg 'copy-pipe-and-cancel'
```

### tmux server 是旧的 SSH 会话

这是本机曾遇到的情况：tmux server 没有 `DISPLAY`，但图形终端 shell 有 `DISPLAY=:1`。配置中的 xclip 命令已显式补齐环境，因此不需要关闭现有会话。修改配置后只需执行：

```bash
tmux source-file ~/.tmux.conf
```

### 目标电脑使用 Wayland

安装 `wl-clipboard` 后：

- Ubuntu 24.04/较新 tmux：将 `copy-command` 改为：

  ```tmux
  set -s copy-command 'wl-copy'
  ```

- Ubuntu 20.04/tmux 3.0a：将 `tmux.conf.ubuntu20.04` 中 5 个复制绑定里的 xclip 命令替换为：

  ```tmux
  wl-copy
  ```

同时确保 tmux server 能看到正确的 `WAYLAND_DISPLAY`；如果 server 是在没有图形环境的 SSH 会话中启动，需要从图形终端重新启动 tmux server，或单独补充其环境变量。

### 恢复旧配置

安装脚本不会删除旧配置。查看备份：

```bash
ls -lt ~/.tmux-config-backups/
```

恢复某个备份后重载：

```bash
cp -a ~/.tmux-config-backups/.tmux.conf.时间戳 ~/.tmux.conf
tmux source-file ~/.tmux.conf
```

## tmux 窗口层级与常用快捷键

tmux 的层级关系如下：

```text
tmux server
└── session 会话
    └── window 窗口
        └── pane 分屏
```

一个 `window` 不能嵌套多个 `session`。一个 `session` 可以包含多个 `window`，一个 `window` 可以包含多个 `pane`。

例如：

```text
session: work
├── window 0
│   ├── pane 0
│   ├── pane 1
│   └── pane 2
└── window 1
    ├── pane 0
    └── pane 1
```

因此在 `Ctrl-b w` 的窗口列表中，如果某个 window 下看到 `0`，通常表示该 window 目前只有一个 pane，编号为 `pane 0`。每个 window 的 pane 编号都会从 `0` 重新开始。

### Session 会话

在外部终端创建并命名一个独立 session：

```bash
tmux new-session -s work
```

`new` 是 `new-session` 的简写：

```bash
tmux new -s debug
```

在 tmux 内创建并切换到新 session：

```text
Ctrl-b :
new-session -s work
```

`-s` 后面是新 session 的名称；名称需要唯一。新建 session 不等于在当前 session 中新建 window，后者使用 `Ctrl-b c`。

切换和查看 session：

```text
Ctrl-b s        列出并选择 session
Ctrl-b (        切换到上一个 session
Ctrl-b )        切换到下一个 session
```

如果想让两个 session 共享同一组 window：

```bash
tmux new-session -s work
tmux new-session -t work -s work2
```

### Window 窗口

在当前 session 中创建新 window：

```text
Ctrl-b c        创建新 window
Ctrl-b w        查看 window 列表
Ctrl-b n        切换到下一个 window
Ctrl-b p        切换到上一个 window
```

`Ctrl-b c` 创建的是 window，不是 session。多个 window 通常编号为 `0、1、2、3`；每个 window 内的 pane 编号则从 `0` 开始。

### Pane 分屏

在当前 window 创建分屏：

```text
Ctrl-b %        左右分屏
Ctrl-b "        上下分屏
```

切换 pane：

```text
Ctrl-b q        临时显示当前 window 的 pane 编号
Ctrl-b o        切换到下一个 pane
Ctrl-b 方向键   按方向切换 pane
```

关闭当前 pane：

```text
Ctrl-b x        关闭当前 pane，然后按 y 确认
Ctrl-b :
kill-pane       通过 tmux 命令关闭当前 pane
```

只想暂时放大当前 pane，不要关闭它：

```text
Ctrl-b z        放大/恢复当前 pane
```

### 滚轮、复制和粘贴

本配置已启用鼠标：

```text
鼠标滚轮       在 pane 历史输出中翻页
鼠标拖选       松开后复制到外部系统剪贴板
```

键盘复制：

```text
Ctrl-b [       进入复制模式
Ctrl-Space     开始选择
方向键         移动选择
Enter          复制并退出
q              退出复制模式
```

粘贴方式：

```text
Ctrl-b ]       粘贴 tmux buffer
Ctrl-Shift-V   在外部 Terminator 中粘贴系统剪贴板内容
```

不要用 `Ctrl-C` 代替复制；它会向当前 pane 中运行的程序发送中断信号。

## 新建 window 或 session

默认终端中的 `Ctrl-Shift-T` 通常表示新建一个标签页。在 tmux 中，等价操作是：

```text
Ctrl-b c        在当前 session 中新建一个 window
```

这也是日常最推荐的方式。新建的 window 仍属于当前 session，可以用下面的快捷键切换：

```text
Ctrl-b w        查看 window 列表
Ctrl-b n        下一个 window
Ctrl-b p        上一个 window
```

如果需要新建独立 session 并指定名称，使用前面“Session 会话”小节中的命令；session 的查看和切换快捷键也列在那里。

两者区别：

```text
Ctrl-b c        当前 session 新建 window，类似终端新标签页
new-session     新建独立 session，适合不同项目或长期工作环境
```

## 重命名 session 和 window

重命名当前 session：

```text
Ctrl-b $        输入新名称后按回车
```

也可以使用 tmux 命令：

```text
Ctrl-b :
rename-session work
```

也可以在外部终端重命名指定 session：

```bash
tmux rename-session -t 旧名称 新名称
```

`rename-session` 的完整语法是：

```text
rename-session [-t target-session] new-name
```

不要使用 `rename-session -n 名称`；`rename-session` 没有 `-n` 参数。若重命名当前 session，直接给出新名称即可。

例如，给编号为 `0` 的 session 改名：

```text
rename-session -t 0 work
```

重命名当前 window：

```text
Ctrl-b ,        输入新名称后按回车
```

两者区别：

```text
Ctrl-b $        重命名当前 session
Ctrl-b ,        重命名当前 window
```

## Catppuccin Mocha 配色主题（tmux 3.4）

当前本机使用的 Ubuntu 24.04/tmux 3.4 配置已将 Catppuccin Mocha 配色写入 `tmux.conf`，运行基础安装脚本即可一并安装。独立配色片段和 `.itermcolors` 预设仍保存在配色目录；`.itermcolors` 仅供 iTerm2 使用，不会改变 Terminator 配色，tmux 配色也不会修改容器配置。

在 tmux 3.4 宿主机上，可从备份目录临时加载：

```bash
cd /path/to/computer_tools_backup/tmux_setup
tmux source-file ./catppuccin-mocha-20260930/tmux-colors.conf
```

要在 tmux server 每次启动时自动加载，先运行基础安装脚本，再把下面一行加入 `~/.tmux.conf`，并换成目标电脑上的实际路径：

```tmux
source-file /path/to/computer_tools_backup/tmux_setup/catppuccin-mocha-20260930/tmux-colors.conf
```

Ubuntu 20.04 自带的 tmux 3.0a 不在此配色片段的支持范围内，不要直接加载；对应的兼容配置不包含这组配色选项。

## session 布局自动保存与恢复

配置使用 `tmux-resurrect` 保存 session、window、pane 的名称和布局、pane 顺序及工作目录；`tmux-continuum` 每 60 分钟自动保存，并在 tmux server 启动时自动恢复。自动保存通过 `~/.local/bin/tmux-resurrect-save-low-priority` 执行：CPU niceness 为 15，若系统有 `ionice`，I/O 使用 idle class；没有 `ionice` 时仍会降低 CPU 优先级。这样尽量把资源留给交互式终端，但不能保证高负载下完全无卡顿。恢复快照固定保存在 `~/.local/share/tmux/resurrect/`。自动恢复只会在 server 启动时触发，不是每次重载配置时触发。

### 当前 session/window/pane 清单

以下是 2026-10-19 16:28（Asia/Shanghai）导出的清单。精确 window 名称、pane 顺序、分割方向与尺寸、工作目录和恢复命令以 `session_layout_snapshot/last` 指向的 Resurrect 快照为准；pane 屏幕历史未纳入快照。

| Session | Windows | Panes |
| --- | ---: | ---: |
| `control` | 4 | 9 |
| `develop容器` | 5 | 17 |
| `fr_max` | 2 | 14 |
| `other` | 5 | 14 |
| `other_modules` | 5 | 13 |
| `planning` | 7 | 18 |
| `ranger_mini_v3_old` | 1 | 4 |
| **合计** | **29** | **89** |

仓库只保留当前和上一份迁移快照；本机 `~/.local/share/tmux/resurrect/` 中的自动保存历史不做全量同步。布局有重要变化时，按 `Ctrl-b Ctrl-s` 手动保存，再将最新快照同步到备份目录并更新 `last` 链接。

### 手动保存与恢复

```text
Ctrl-b Ctrl-s    立即保存当前 tmux 布局
Ctrl-b Ctrl-r    从最近一次保存恢复布局
```

首次安装插件后建议手动保存一次。大幅调整窗口或分屏后，也可以手动保存，不必等待自动保存。手动 `Ctrl-b Ctrl-s` 仍直接调用插件原始脚本，不经低优先级包装；若刚完成大量布局调整，可以手动保存，避免等到下一次 60 分钟自动保存。

### 意外关机后恢复

启用 Linux 用户级 systemd 自动启动后，登录该用户时 systemd 会自动启动 tmux server；Continuum 随后自动恢复最近一次保存的布局，不需要打开终端或手动输入命令。若没有启用该服务、服务未运行，或目标系统没有 systemd，则打开终端并手动启动：

```bash
tmux
```

新 tmux server 启动后，Continuum 会触发最近一次自动恢复；如果没有自动恢复，再按 `Ctrl-b Ctrl-r`。恢复的是最近保存的状态，因此突然断电时，最近一次保存之后新增或调整的布局可能还没写入；按当前 60 分钟间隔，理论上可能丢失最多约 60 分钟内的布局变更。重要布局调整后建议手动保存。

检查登录自动启动是否已启用：

```bash
systemctl --user is-enabled tmux.service
systemctl --user status tmux.service --no-pager
```

预期 `is-enabled` 输出 `enabled`。不重启也可以检查配置是否生效；本机配置后无需现在启动另一个 tmux server 或重启系统。若要关闭登录自动启动，在 `~/.tmux.conf` 将 `@continuum-boot` 改为 `off` 并重载配置；也可执行 `systemctl --user disable tmux.service`。这只关闭登录自动启动，不会删除恢复快照。

如果是在已经登录的桌面会话中刚启用服务，`systemctl --user status` 暂时显示 `inactive (dead)` 是正常的：`enable` 只安排它在下一次用户 systemd 会话启动时运行。当前已经有 tmux server 时，不要为了立即测试而盲目 `systemctl --user start tmux.service`，因为默认启动命令可能在现有 server 中额外创建一个 session。下次用户注销并重新登录即可验证，无需重启整台电脑。

### 恢复边界

- session/window/pane 名称、顺序、布局和工作目录可以恢复；pane 的完整屏幕历史默认不保证恢复。
- 插件只会恢复一小组已知程序。其他程序可以单独加入 `@resurrect-processes`，但应逐个验证；不要启用 `:all:`，以免意外重启不安全的命令。
- 重新打开程序不等于恢复它断电前的内部状态。Codex、Apollo 工具或容器内的交互进程需要分别验证；程序自己的会话/任务数据应由程序本身保存。
- 本目录的 `session_layout_snapshot/` 是本机 2026-10-19 16:28 导出的最新快照及上一份迁移快照副本，不包含本机完整自动保存历史。迁移时先安装配置和恢复插件，再在新机第一次启动 tmux 之前将它复制到 `~/.local/share/tmux/resurrect/`；仅保存配置文件不能还原以前的布局。
- 快照包含 session/window 名称、工作目录和 pane 运行命令（可能含内部主机地址）；本目录应只保存在私有代码库，不要公开分享或放入公共仓库。
- 该机制防止 tmux 布局因意外关机丢失，不替代独立磁盘备份；磁盘损坏时，存于同一磁盘的恢复快照也可能丢失。
