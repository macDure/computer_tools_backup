# Terminator 终端中文输入法（Fcitx / 搜狗）修复指南与备份工具

本目录用于备份针对 Linux（Ubuntu / Debian 等）环境下 **Terminator 终端无法切换/输入中文** 的修复方案、补丁文件及一键安装脚本。

---

## 目录结构

```text
terminator_chinese_input_fix/
├── README.md             # 本详细故障排查与修复说明文档
├── install_fix.sh        # 一键自动化检测与修复脚本（推荐在新电脑上使用）
├── terminator            # 已打补丁的 Terminator 可执行文件副本（Terminator 2.1.2+）
└── terminator.desktop    # 配置正确的桌面启动项模板
```

---

## 一、 问题现象与根因诊断

### 现象
在系统其他应用（如 Chrome、文本编辑器、VS Code）中中文输入法正常，但在 Terminator 终端内按下 `Shift`、`Ctrl + Space` 或 `Ctrl + Shift` 时**无法唤出候选词框，只能输入英文**。

### 深入根因分析（三重阻断）

1. **Terminator 官方源码硬编码 Bug（核心致命点）**：
   在 Terminator 2.1.2 等版本中，官方为了解决在广播模式（Broadcast）下的“按键双重输入”问题（issue #78），在启动入口（`/usr/bin/terminator` 第 59~60 行）硬编码了以下逻辑：
   ```python
   if os.environ.get('GTK_IM_MODULE') is not None:
       del os.environ['GTK_IM_MODULE']
   ```
   **影响**：无论外部会话或脚本如何 `export GTK_IM_MODULE=fcitx`，Terminator 一启动就会在 Python 内部强行删除该环境变量。导致随后的 GTK3 / VTE 终端控件根本不会加载 `im-fcitx.so` 输入法前端模块（内存映射中 Fcitx 模块加载数为 0）。

2. **Fcitx 核心热键配置被清空**：
   在 `~/.config/fcitx/config` 中，`TriggerKey` 被设为空、`SwitchKey` 被设为 `Disabled`、`IMSwitchKey` 被设为 `False`。此时 Fcitx 全局失去了一切唤醒/切换热键，按任何键系统都不会响应该窗口的输入法请求。

3. **桌面启动项被误设置为 `xim`**：
   网络上许多流传的过时教程建议在 `terminator.desktop` 中添加 `Exec=env GTK_IM_MODULE=xim terminator`。现代 GTK3 / VTE 对过时的 XIM 协议兼容性极差，这反而彻底掐断了原生的 DBus 通信链路。

4. **IBus 与 Terminator 的 `Ctrl+Shift+E` 快捷键冲突**：
   Ubuntu GNOME 后台默认保留的 IBus 将 `Ctrl+Shift+E` 绑定为表情符号选择器（Emoji Picker），导致 Terminator 的垂直分屏快捷键失效。

---

## 二、 快速修复（在新电脑上直接使用）

进入备份目录并执行一键安装脚本：

```bash
cd /home/mac/macperson/computer_tools_backup/terminator_chinese_input_fix
./install_fix.sh
```

该脚本会自动执行：
1. 检测并提示安装 `fcitx-frontend-gtk3` 依赖；
2. 动态读取系统的 `/usr/bin/terminator`，移除其中的 `del os.environ['GTK_IM_MODULE']` 逻辑，并将补丁版安全部署到用户优先执行目录 `~/.local/bin/terminator`；
3. 更新 `~/.local/share/applications/terminator.desktop`，确保桌面图标启动时走补丁版本；
4. 检查并恢复 `~/.config/fcitx/config` 中的 `TriggerKey`、`SwitchKey` 与 `IMSwitchKey` 并热重载；
5. 自动禁用 IBus 的 Emoji 快捷键，消除 `Ctrl+Shift+E` 分屏冲突。

---

## 三、 手动分步修复指南（备忘手册）

如果需要在没有该脚本的裸机上快速手动修复，可按以下步骤操作：

### 步骤 1：安装 GTK3 前端依赖
```bash
sudo apt update
sudo apt install -y fcitx-frontend-gtk3
```

### 步骤 2：部署修复版 Terminator
复制系统的 Terminator 并修改源码：
```bash
mkdir -p ~/.local/bin
cp /usr/bin/terminator ~/.local/bin/terminator

# 用文本编辑器打开 ~/.local/bin/terminator
nano ~/.local/bin/terminator
```
找到以下代码（约第 57~60 行）：
```python
# Deleting env variable fixes double char problem when broadcasting (#78)
# Only delete if it exists, or exception occurs
if os.environ.get('GTK_IM_MODULE') is not None:
    del os.environ['GTK_IM_MODULE']
```
修改为：
```python
# 保留 GTK_IM_MODULE，并显式锁定为 fcitx
os.environ['GTK_IM_MODULE'] = 'fcitx'
os.environ['QT_IM_MODULE'] = 'fcitx'
os.environ['XMODIFIERS'] = '@im=fcitx'
```
保存后赋予执行权限：
```bash
chmod +x ~/.local/bin/terminator
```
*(确保 `~/.local/bin` 在 `~/.bashrc` 的 `$PATH` 前列)*

### 步骤 3：修复桌面启动文件
```bash
mkdir -p ~/.local/share/applications
cp /usr/share/applications/terminator.desktop ~/.local/share/applications/terminator.desktop
sed -i "s|Exec=.*terminator|Exec=${HOME}/.local/bin/terminator|g" ~/.local/share/applications/terminator.desktop
sed -i "s|TryExec=.*|TryExec=${HOME}/.local/bin/terminator|g" ~/.local/share/applications/terminator.desktop
```

### 步骤 4：恢复 Fcitx 核心快捷键
编辑 `~/.config/fcitx/config`，确保 `[Hotkey]` 区域如下：
```ini
[Hotkey]
TriggerKey=CTRL_SPACE
SwitchKey=SHIFT Both
IMSwitchKey=True
IMSwitchHotkey=CTRL_SHIFT
```
重载 Fcitx 配置：
```bash
fcitx-remote -r
```

### 步骤 5：消除垂直分屏冲突
```bash
gsettings set org.freedesktop.ibus.panel.emoji hotkey "[]"
```

---

## 四、 状态验证方法

1. **检查 Terminator 加载的动态库**：
   打开 Terminator 终端后，在另一个终端执行：
   ```bash
   cat /proc/$(pgrep -f "terminator" | head -n 1)/maps | grep im-fcitx
   ```
   若输出包含 `/usr/lib/x86_64-linux-gnu/gtk-3.0/3.0.0/immodules/im-fcitx.so`，说明模块加载成功。

2. **按键测试**：
   - 按 **`Shift`**：在搜狗/中文与英文之间切换；
   - 按 **`Ctrl + Space`**：激活或注销输入法；
   - 按 **`Ctrl + Shift + E`**：垂直分屏，终端左右切分且不出现 Emoji 弹窗。
