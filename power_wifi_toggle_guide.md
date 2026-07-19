# Ubuntu GNOME 锁屏省电与合盖策略复刻手册

本文档的目标不是单纯记录一次排查过程，而是服务于“复制当前电脑环境”：

* 在当前电脑上清楚记录最终配置状态。
* 将来重装系统或配置另一台 Ubuntu GNOME 笔记本时，可以按本文从零复刻同样功能。
* 记录已经踩过的坑、症状、日志关键词和修复方式，避免下次重复排查。

---

## 1. 目标功能

当前电脑最终目标行为如下：

* **锁屏时**：关闭 WiFi，并切换到 `power-saver` 节能模式。
* **解锁时**：打开 WiFi，并切换到 `performance` 性能模式。
* **接电时合盖**：不执行任何操作，系统继续运行。
* **电池供电时合盖**：先挂起，长时间后进入休眠，避免只锁屏导致电池耗尽。
* **外接显示器或扩展坞时合盖**：忽略合盖动作。

---

## 2. 组件关系

这套功能由多个系统组件协作完成：

* **GNOME ScreenSaver D-Bus**
  * 提供锁屏/解锁事件。
  * 脚本监听 `org.gnome.ScreenSaver` 的 `ActiveChanged` 信号。
* **NetworkManager**
  * 通过 `nmcli radio wifi off/on` 控制 WiFi radio。
* **power-profiles-daemon**
  * 通过 `powerprofilesctl set power-saver/performance` 切换电源模式。
* **systemd user service**
  * 让锁屏联动脚本随用户登录自动运行，并在失败后重启。
* **systemd-logind**
  * 控制合盖行为。
* **GNOME 电源设置**
  * 控制 GNOME 层面的接电/电池合盖动作。
* **Polkit**
  * 授权 systemd 用户服务执行 WiFi radio 和电源模式切换。

注意：合盖策略和 WiFi 省电服务不是同一个系统。它们通过“锁屏/解锁事件”间接关联。

---

## 3. 系统依赖

适用环境：

* Ubuntu GNOME。
* 使用 NetworkManager 管理网络。
* 使用 power-profiles-daemon 管理电源模式。
* 使用 systemd-logind 管理合盖。
* 用户名为 `mac`。如果新机器用户名不同，需要替换文中的 `/home/mac` 和 Polkit 规则里的 `subject.user == "mac"`。

需要的命令：

```bash
gdbus
nmcli
powerprofilesctl
systemctl
journalctl
systemd-analyze
gsettings
```

检查睡眠/休眠基础能力：

```bash
cat /sys/power/state
cat /sys/power/disk
free -h
systemctl cat systemd-suspend-then-hibernate.service --no-pager
```

当前机器验证结果：

```text
/sys/power/state: freeze mem disk
/sys/power/disk: [platform] shutdown reboot suspend test_resume
Swap: 61Gi
```

---

## 4. 文件清单

最终环境包含这些关键文件：

```text
/home/mac/toggle_power_wifi.sh
/home/mac/.config/systemd/user/toggle-power-wifi.service
/etc/systemd/logind.conf.d/90-lid-power-policy.conf
/etc/polkit-1/rules.d/49-mac-toggle-power-wifi.rules
/home/mac/macperson/computer_tools_backup/power_wifi_toggle_guide.md
```

---

## 5. 从零配置步骤

### 5.1 创建锁屏联动脚本

文件路径：`/home/mac/toggle_power_wifi.sh`

```bash
#!/bin/bash

# Ensure we have the correct DBus session bus address
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

echo "Starting WiFi and Power Profile Toggle Service..."

# Function to handle lock event
handle_lock() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Screen Locked: Disabling WiFi and setting power-saver mode..."
    nmcli radio wifi off
    powerprofilesctl set power-saver
}

# Function to handle unlock event
handle_unlock() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Screen Unlocked: Enabling WiFi and setting performance mode..."
    nmcli radio wifi on
    powerprofilesctl set performance
}

# Check initial screen saver state at start
IS_LOCKED=$(gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive 2>/dev/null)

if [[ "$IS_LOCKED" == "(true,)" ]]; then
    handle_lock
else
    # Default to unlock setup if unlocked or call fails
    handle_unlock
fi

# Monitor GNOME ScreenSaver signals
gdbus monitor --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver | while read -r line; do
    if echo "$line" | grep -q "ActiveChanged (true,)"; then
        handle_lock
    elif echo "$line" | grep -q "ActiveChanged (false,)"; then
        handle_unlock
    fi
done
```

设置可执行权限：

```bash
chmod +x /home/mac/toggle_power_wifi.sh
```

### 5.2 创建 systemd 用户服务

文件路径：`/home/mac/.config/systemd/user/toggle-power-wifi.service`

```ini
[Unit]
Description=Toggle WiFi and Power Profile on Lock/Unlock
After=graphical-session.target

[Service]
Type=simple
ExecStart=/home/mac/toggle_power_wifi.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

启用并启动：

```bash
systemctl --user daemon-reload
systemctl --user enable toggle-power-wifi.service
systemctl --user start toggle-power-wifi.service
```

### 5.3 配置 Polkit 最小权限

systemd user service 不等同于普通终端命令。即使终端里能执行 `nmcli` 或 `powerprofilesctl`，用户服务里也可能被 Polkit 拒绝。

文件路径：`/etc/polkit-1/rules.d/49-mac-toggle-power-wifi.rules`

```javascript
// Allow the local lock/unlock automation for user mac to toggle WiFi and power profiles.
polkit.addRule(function(action, subject) {
    var allowedActions = [
        "org.freedesktop.NetworkManager.enable-disable-wifi",
        "org.freedesktop.UPower.PowerProfiles.switch-profile"
    ];

    if (subject.user == "mac" && allowedActions.indexOf(action.id) >= 0) {
        return polkit.Result.YES;
    }
});
```

授权范围：

* 仅用户 `mac`。
* 仅允许切换 WiFi radio。
* 仅允许切换电源模式。
* 不授予其它 NetworkManager、UPower、systemd 或管理员权限。

### 5.4 配置合盖策略

文件路径：`/etc/systemd/logind.conf.d/90-lid-power-policy.conf`

```ini
[Login]
HandleLidSwitch=suspend-then-hibernate
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```

含义：

* `HandleLidSwitch=suspend-then-hibernate`：电池供电合盖时先挂起，长时间后休眠。
* `HandleLidSwitchExternalPower=ignore`：接电合盖时忽略。
* `HandleLidSwitchDocked=ignore`：外接显示器或扩展坞场景合盖忽略。

注意：

* 写入该文件后，需要正常重启系统，或谨慎重启 `systemd-logind` 才能确保运行态完整加载。
* 重启 `systemd-logind` 可能影响当前图形会话。优先选择在方便时正常重启系统。

### 5.5 配置 GNOME 合盖与锁屏

```bash
gsettings set org.gnome.settings-daemon.plugins.power lid-close-ac-action 'nothing'
gsettings set org.gnome.settings-daemon.plugins.power lid-close-battery-action 'suspend'
gsettings set org.gnome.desktop.screensaver lock-enabled true
gsettings set org.gnome.desktop.screensaver lock-delay 0
```

### 5.6 修复 fwupd 版本不匹配

如果日志里出现类似错误：

```text
Failed to load daemon: failed to load engine: libfwupd version 1.9.34 does not match daemon 1.9.33
```

说明 `fwupd` 守护进程和 `libfwupd` 版本不匹配。当前机器的修复方式是升级 `fwupd`：

```bash
sudo apt-get install -y fwupd
```

当前机器修复后版本：

```text
fwupd: 2.0.20-1ubuntu2~24.04.2
libfwupd3: 2.0.20-1ubuntu2~24.04.2
```

验证：

```bash
fwupdmgr --version
```

预期关键输出：

```text
compile   org.freedesktop.fwupd         2.0.20
runtime   org.freedesktop.fwupd         2.0.20
```

---

## 6. 验证方法

### 6.1 验证合盖配置

```bash
systemd-analyze cat-config systemd/logind.conf | rg 'HandleLidSwitch|90-lid'
```

预期包含：

```text
# /etc/systemd/logind.conf.d/90-lid-power-policy.conf
HandleLidSwitch=suspend-then-hibernate
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```

确认 `systemd-logind` 已在配置写入后启动：

```bash
systemctl show systemd-logind -p ActiveState -p SubState -p ExecMainStartTimestamp --no-pager
stat -c '%y %n' /etc/systemd/logind.conf.d/90-lid-power-policy.conf
```

当前机器验证结果：

```text
systemd-logind ActiveState=active
systemd-logind SubState=running
ExecMainStartTimestamp=Sun 2026-07-19 21:03:44 CST
配置文件时间=2026-07-19 20:37:27 +0800
```

### 6.2 验证 GNOME 设置

```bash
gsettings get org.gnome.settings-daemon.plugins.power lid-close-ac-action
gsettings get org.gnome.settings-daemon.plugins.power lid-close-battery-action
gsettings get org.gnome.desktop.screensaver lock-enabled
gsettings get org.gnome.desktop.screensaver lock-delay
```

预期：

```text
'nothing'
'suspend'
true
uint32 0
```

### 6.3 验证锁屏联动服务

```bash
systemctl --user show toggle-power-wifi.service -p ActiveState -p SubState -p UnitFileState --no-pager
journalctl --user -u toggle-power-wifi.service -n 80 --no-pager
```

预期：

```text
ActiveState=active
SubState=running
UnitFileState=enabled
```

日志中应能看到：

```text
Screen Locked: Disabling WiFi and setting power-saver mode...
Screen Unlocked: Enabling WiFi and setting performance mode...
```

### 6.4 验证 Polkit 权限

测试前记录状态：

```bash
nmcli radio wifi
powerprofilesctl get
```

权限闭环测试：

```bash
nmcli radio wifi on
nmcli radio wifi
powerprofilesctl set power-saver
powerprofilesctl get
nmcli radio wifi off
nmcli radio wifi
powerprofilesctl set performance
powerprofilesctl get
```

当前机器测试结果：

```text
initial wifi: disabled
initial profile: performance
after wifi on: enabled
after power-saver: power-saver
after wifi restore: disabled
after profile restore: performance
```

测试结束后当前机器状态：

```text
WiFi radio: disabled
power profile: performance
```

### 6.5 验证 firmware-updater 不再崩溃

```bash
systemctl --user show snap.firmware-updater.firmware-notifier.service -p ActiveState -p SubState -p NRestarts --no-pager
journalctl --user -u snap.firmware-updater.firmware-notifier.service -b -n 30 --no-pager
```

当前机器验证结果：

```text
ActiveState=inactive
SubState=dead
NRestarts=0
```

---

## 7. 当前机器最终状态

当前机器最后确认状态：

* 合盖策略已加载：
  * 电池合盖：`suspend-then-hibernate`
  * 接电合盖：`ignore`
  * 外接显示器/扩展坞合盖：`ignore`
* GNOME 设置：
  * 接电合盖：`nothing`
  * 电池合盖：`suspend`
  * 锁屏开启：`true`
  * 锁屏延迟：`0`
* `toggle-power-wifi.service`：
  * `enabled`
  * `active`
  * `running`
* Polkit 规则：
  * 已允许用户 `mac` 切换 WiFi radio 和 power profile。
* `fwupd`：
  * compile/runtime 均为 `2.0.20`
  * `firmware-updater` 通知服务无崩溃循环。
* 当前测试结束状态：
  * WiFi radio：`disabled`
  * 电源模式：`performance`

---

## 8. 管理命令

用户服务管理：

```bash
systemctl --user daemon-reload
systemctl --user enable toggle-power-wifi.service
systemctl --user start toggle-power-wifi.service
systemctl --user stop toggle-power-wifi.service
systemctl --user status toggle-power-wifi.service
journalctl --user -u toggle-power-wifi.service -f
```

合盖配置检查：

```bash
systemd-analyze cat-config systemd/logind.conf
gsettings get org.gnome.settings-daemon.plugins.power lid-close-ac-action
gsettings get org.gnome.settings-daemon.plugins.power lid-close-battery-action
```

电源与 WiFi 状态：

```bash
nmcli radio wifi
powerprofilesctl get
```

---

## 9. 常见问题与踩坑记录

### 9.1 电池合盖只锁屏会耗尽电池

踩坑现象：

* 电池供电合盖后，机器过几个小时电池耗尽。

当时错误配置：

```text
HandleLidSwitch=lock
GNOME lid-close-battery-action='blank'
```

日志证据：

```text
2026-07-19 05:58:47 Lid closed.
2026-07-19 05:58:48 Locking sessions...
直到 10:02:15 没有 suspend 或 hibernate 记录
```

结论：

* `lock`/`blank` 只是锁屏/黑屏，不是睡眠。
* 长时间合盖必须使用 `suspend`、`suspend-then-hibernate` 或 `hibernate`。

最终修复：

```ini
HandleLidSwitch=suspend-then-hibernate
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```

```bash
gsettings set org.gnome.settings-daemon.plugins.power lid-close-battery-action 'suspend'
```

### 9.2 firmware-updater 反复崩溃

踩坑现象：

* 合盖期间 `snap.firmware-updater.firmware-notifier.service` 反复崩溃重启。
* 重启计数曾达到 1421。
* 在机器没有睡眠的情况下会加速耗电。

日志关键词：

```text
Failed to load daemon: failed to load engine: libfwupd version 1.9.34 does not match daemon 1.9.33
snap.firmware-updater.firmware-notifier.service: Scheduled restart job
```

原因：

* `fwupd` 守护进程和 `libfwupd` 版本不匹配。

修复：

```bash
sudo apt-get install -y fwupd
fwupdmgr --version
```

验证：

```text
compile   org.freedesktop.fwupd         2.0.20
runtime   org.freedesktop.fwupd         2.0.20
```

### 9.3 systemd user service 的 Polkit 授权不同于终端

踩坑现象：

* `toggle-power-wifi.service` 能收到锁屏/解锁事件。
* 但执行 WiFi 和电源模式切换时报错：

```text
Error: failed to set Wi-Fi radio: Not authorized to perform this operation
GDBus.Error:org.freedesktop.DBus.Error.AccessDenied: Not Authorized: org.freedesktop.UPower.PowerProfiles.switch-profile
```

原因：

* 该服务以 systemd 用户服务方式运行。
* Polkit 不一定把后台用户服务视为可直接授权的交互式 active session。
* 终端里能执行的命令，放到用户服务里不一定有同样权限。

修复：

* 添加最小范围 Polkit 规则，只允许用户 `mac` 执行两个必要 action。

### 9.4 合盖策略没有直接改坏 WiFi 服务

这次问题表面上像是“修改合盖策略后 WiFi 省电服务出问题”，但实际关系是：

* 合盖策略由 `systemd-logind` 和 GNOME 电源设置管理。
* WiFi 省电服务由 `toggle-power-wifi.service` 管理。
* 两者通过锁屏/解锁事件间接关联。
* 合盖、重启、挂起恢复流程让原本存在的 Polkit 授权问题更明显。

经验：

* 不能只看服务日志是否打印 `Screen Locked`。
* 必须检查 `nmcli` 和 `powerprofilesctl` 的 stderr，以及最终状态。

### 9.5 不要随意重启 systemd-logind

`systemd-logind` 与图形会话、登录、锁屏、合盖密切相关。

经验：

* 写配置可以先落盘。
* 优先通过正常系统重启让它加载。
* 如果要立即重启 `systemd-logind`，必须明确说明可能影响当前图形会话和未保存工作，并单独确认。

---

## 10. 历史操作记录

### 2026-07-18

* 初始需求：接电合盖不执行动作，电池合盖进入锁屏。
* 当时配置为：
  ```ini
  HandleLidSwitch=lock
  HandleLidSwitchExternalPower=ignore
  HandleLidSwitchDocked=ignore
  ```
* GNOME 配置为：
  ```bash
  lid-close-ac-action 'nothing'
  lid-close-battery-action 'blank'
  lock-enabled true
  lock-delay uint32 0
  ```
* 后续发现该方案只锁屏不睡眠，会导致电池耗尽。

### 2026-07-19

* 复盘电池耗尽问题。
* 将电池合盖策略改为 `suspend-then-hibernate`。
* 将 GNOME 电池合盖策略改为 `suspend`。
* 修复 `fwupd` / `libfwupd` 版本不匹配。
* 新增 Polkit 最小权限规则，修复 systemd 用户服务中 WiFi/电源模式切换权限问题。
* 系统重启后验证 `systemd-logind` 已加载 drop-in 配置。

---

## 11. 下次重装时的最短路径

在新机器上优先按这个顺序做：

1. 确认用户名。如果不是 `mac`，替换所有路径和 Polkit 用户名。
2. 安装并确认 `NetworkManager`、`power-profiles-daemon`、`fwupd` 正常。
3. 创建 `/home/mac/toggle_power_wifi.sh`。
4. 创建并启用 `toggle-power-wifi.service`。
5. 创建 Polkit 最小权限规则。
6. 创建 `systemd-logind` 合盖 drop-in。
7. 写入 GNOME 合盖与锁屏设置。
8. 正常重启系统。
9. 按“验证方法”逐项确认。
10. 最后实际测试一次锁屏/解锁、接电合盖、电池合盖。
