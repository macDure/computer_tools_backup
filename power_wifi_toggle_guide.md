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
* **接电时合盖**：已回退为系统默认 `suspend`。
* **电池供电时合盖**：已回退为系统默认 `suspend`。
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
cat /sys/power/mem_sleep
free -h
swapon --show
```

当前机器验证结果：

```text
/sys/power/state: freeze mem disk
/sys/power/disk: [platform] shutdown reboot suspend test_resume
/sys/power/mem_sleep: [s2idle]
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

### 5.4 合盖策略：保留系统默认

当前机器已经回退到提出“接电合盖不动作”需求之前的保守状态：不再使用本手册创建 `logind` 合盖 drop-in。

确认该文件不存在：

```bash
test ! -e /etc/systemd/logind.conf.d/90-lid-power-policy.conf
```

系统默认值来自 `/etc/systemd/logind.conf`：

```text
#HandleLidSwitch=suspend
#HandleLidSwitchExternalPower=suspend
#HandleLidSwitchDocked=ignore
```

注意：

* 如果修改过 `/etc/systemd/logind.conf.d/90-lid-power-policy.conf`，回退后需要正常重启系统，或谨慎重启 `systemd-logind`，才能确保运行态完整加载。
* 重启 `systemd-logind` 可能影响当前图形会话，必须提前保存工作并单独确认。

### 5.5 配置 GNOME 合盖与锁屏

```bash
gsettings reset org.gnome.settings-daemon.plugins.power lid-close-ac-action
gsettings reset org.gnome.settings-daemon.plugins.power lid-close-battery-action
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

### 5.7 不启用休眠 resume

当前机器已撤销直接 `hibernate` 方案，因此不再保留 `/etc/initramfs-tools/conf.d/resume`，`/etc/default/grub` 也不再包含 `resume=UUID=...`。

确认方式：

```bash
test ! -e /etc/initramfs-tools/conf.d/resume
grep '^GRUB_CMDLINE_LINUX_DEFAULT=' /etc/default/grub
```

预期：

```text
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
```

---

## 6. 验证方法

### 6.1 验证合盖配置

```bash
systemd-analyze cat-config systemd/logind.conf | rg 'HandleLidSwitch|90-lid'
```

预期只看到系统默认注释值，不应再看到 `/etc/systemd/logind.conf.d/90-lid-power-policy.conf`：

```text
#HandleLidSwitch=suspend
#HandleLidSwitchExternalPower=suspend
#HandleLidSwitchDocked=ignore
```

回退后确认 `systemd-logind` 运行态是否已经在配置删除后启动：

```bash
systemctl show systemd-logind -p ActiveState -p SubState -p ExecMainStartTimestamp --no-pager
stat -c '%y %n' /etc/systemd/logind.conf.d/90-lid-power-policy.conf
```

当前机器说明：

```text
磁盘配置已回退为系统默认。
未重启 systemd-logind。
需要用户保存工作后正常重启一次，再确认运行态已加载默认策略。
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
'suspend'
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

* 合盖策略已回退到系统默认：
  * 电池合盖：`suspend`
  * 接电合盖：`suspend`
  * 外接显示器/扩展坞合盖：`ignore`
* GNOME 设置：
  * 接电合盖：`suspend`
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
* 2026-07-20 已按用户要求回退合盖/休眠相关改动：
  * 删除 `/etc/systemd/logind.conf.d/90-lid-power-policy.conf`。
  * 删除 `/etc/initramfs-tools/conf.d/resume`。
  * 从 `/etc/default/grub` 移除 `resume=UUID=...`，恢复为 `GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"`。
  * 已执行 `update-initramfs -u` 和 `update-grub`。
  * 未重启系统、未重启 `systemd-logind`；需要用户在保存工作后自行正常重启，让运行态完整加载回退后的策略。

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
* 长时间合盖不能只用 `lock`/`blank`。
* 把电池合盖改成 `lock`/`blank` 是错误扩展需求；原需求只要求接电合盖不动作，不应该改变电池合盖行为。

错误配置示例，不要复刻：

```ini
HandleLidSwitch=lock
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```

```bash
gsettings set org.gnome.settings-daemon.plugins.power lid-close-battery-action 'blank'
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

### 9.3 suspend-then-hibernate 在本机上仍会发热

踩坑现象：

* 2026-07-19 晚上，电池供电合盖后电脑明显发热。
* 当时已从 `lock` 改为 `suspend-then-hibernate`，但仍未达到预期。

日志证据：

```text
2026-07-19 21:33:33 Lid closed.
2026-07-19 21:33:42 Suspending, then hibernating...
2026-07-19 21:33:42 PM: suspend entry (s2idle)
2026-07-19 21:35:48 workqueue: output_poll_execute hogged CPU for >10000us 4 times
2026-07-19 23:04:11 workqueue: output_poll_execute hogged CPU for >10000us 131 times
```

同时合盖后系统仍在运行定时任务：

```text
CRON: debian-sa1
sysstat-collect.service
fwupd-refresh.service
dpkg-db-backup.service
```

判断：

* 不是某个普通用户程序在后台“疯狂运行”。
* 根因是本机 suspend 只有 `s2idle`，没有传统 `deep` 睡眠：
  ```text
  /sys/power/mem_sleep: [s2idle]
  ```
* `s2idle` 属于现代待机，系统没有完全断电式睡眠，内核、定时器、显示输出轮询仍可能活动。
* 日志中的 `output_poll_execute hogged CPU` 指向显示/显卡输出轮询，和本机 NVIDIA/i915 混合显卡环境高度相关。
* 由于 `/proc/cmdline` 当时没有 `resume=UUID=...`，`/etc/initramfs-tools/conf.d/resume` 也不存在，休眠恢复链路不完整。

当时尝试过但后来回退的方案：

* 电池合盖从 `suspend-then-hibernate` 改为直接 `hibernate`。
* GNOME 电池合盖从 `suspend` 改为 `hibernate`。
* 补齐 swap resume 配置：
  ```text
  RESUME=UUID=6f0ad98e-177e-48d7-8c52-46fd7299b995
  ```
* GRUB 增加：
  ```text
  resume=UUID=6f0ad98e-177e-48d7-8c52-46fd7299b995
  ```
* 已执行：
  ```bash
  sudo update-initramfs -u
  sudo update-grub
  ```

后续结论：

* 该方案虽然理论上能绕开 `s2idle`，但继续扩大了原始需求范围。
* 用户明确要求回退到提出合盖需求之前的状态后，已撤销该方案。
* 当前不再保留 `hibernate` 合盖策略，也不再保留 `resume=UUID=...`。

经验：

* 对只有 `s2idle` 的笔记本，不能假设 `suspend` 就足够省电。
* 如果以后真的要启用 `hibernate`，必须把它作为单独需求处理，并提前说明风险、检查 swap、`/etc/initramfs-tools/conf.d/resume`、GRUB `resume=UUID=...`，最后由用户手动选择重启和测试时间。

### 9.4 合盖需求必须严格控制变更范围

这次最大的教训：

* 原始需求是“接电合盖不执行任何操作”。
* 正确的最小变更应该只改接电合盖行为，保留电池合盖原有策略。
* 实际操作中把电池合盖也改成了 `lock`/`blank`，导致合盖后机器没有睡眠，电池被耗空。
* 后续又把电池合盖推进到 `suspend-then-hibernate` 和 `hibernate`，继续扩大了系统电源链路的变更面。

以后处理这类系统配置时必须遵守：

* 先记录改动前配置。
* 只改用户明确要求的分支。
* 对电源、登录、图形会话、休眠、启动参数这类高风险项，必须先解释风险并获得明确同意。
* 不能用“看起来更省电”的推断替代实际验证。
* 涉及重启、休眠、重启 `systemd-logind`、重启图形会话的动作，必须单独确认。

### 9.5 systemd user service 的 Polkit 授权不同于终端

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

### 9.6 合盖策略没有直接改坏 WiFi 服务

这次问题表面上像是“修改合盖策略后 WiFi 省电服务出问题”，但实际关系是：

* 合盖策略由 `systemd-logind` 和 GNOME 电源设置管理。
* WiFi 省电服务由 `toggle-power-wifi.service` 管理。
* 两者通过锁屏/解锁事件间接关联。
* 合盖、重启、挂起恢复流程让原本存在的 Polkit 授权问题更明显。

经验：

* 不能只看服务日志是否打印 `Screen Locked`。
* 必须检查 `nmcli` 和 `powerprofilesctl` 的 stderr，以及最终状态。

### 9.7 不要随意重启 systemd-logind

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

### 2026-07-20

* 复盘电池合盖后电脑发热问题。
* 发现本机 `/sys/power/mem_sleep` 只有 `[s2idle]`，没有 `deep`。
* 日志显示合盖后进入 `PM: suspend entry (s2idle)`，随后系统仍执行 `CRON`、`sysstat`、`fwupd-refresh` 等任务。
* 日志反复出现 `workqueue: output_poll_execute hogged CPU`，指向显示/显卡输出轮询在 `s2idle` 中持续耗 CPU。
* 发现休眠恢复配置不完整：`/proc/cmdline` 没有 `resume=UUID=...`，`/etc/initramfs-tools/conf.d/resume` 不存在。
* 将电池合盖策略改为直接 `hibernate`。
* 将 GNOME 电池合盖策略改为 `hibernate`。
* 写入 `/etc/initramfs-tools/conf.d/resume`：
  ```text
  RESUME=UUID=6f0ad98e-177e-48d7-8c52-46fd7299b995
  ```
* 将 `/etc/default/grub` 更新为包含：
  ```text
  resume=UUID=6f0ad98e-177e-48d7-8c52-46fd7299b995
  ```
* 已执行：
  ```bash
  sudo update-initramfs -u
  sudo update-grub
  ```
* 未执行休眠测试，未重启系统；需要在方便时正常重启后，再测试电池合盖直接休眠。

### 2026-07-20 回退记录

用户指出：在提出“接电合盖不动作”需求之前，电池和接电合盖都不会明显发热，也不会快速耗电；后续问题来自合盖策略改动范围扩大。

已执行回退：

* 创建 `/home/mac/rollback_lid_policy_to_default.sh`。
* 删除 `/etc/systemd/logind.conf.d/90-lid-power-policy.conf`，并保留时间戳备份。
* 删除 `/etc/initramfs-tools/conf.d/resume`，并保留时间戳备份。
* 将 `/etc/default/grub` 从 `/etc/default/grub.bak-20260720-071011` 恢复。
* 执行 `update-initramfs -u`。
* 执行 `update-grub`。
* 重置 GNOME 合盖设置：
  ```text
  lid-close-ac-action 'suspend'
  lid-close-battery-action 'suspend'
  ```

回退后验证：

```text
systemd-analyze cat-config systemd/logind.conf:
#HandleLidSwitch=suspend
#HandleLidSwitchExternalPower=suspend
#HandleLidSwitchDocked=ignore

/etc/systemd/logind.conf.d/90-lid-power-policy.conf: 不存在
/etc/initramfs-tools/conf.d/resume: 不存在
/etc/default/grub:
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
```

注意：

* 未重启系统。
* 未重启 `systemd-logind`。
* 运行中的 `systemd-logind` 可能仍需要用户保存工作后正常重启一次，才能完整加载回退后的磁盘配置。

---

## 11. 下次重装时的最短路径

在新机器上优先按这个顺序做：

1. 确认用户名。如果不是 `mac`，替换所有路径和 Polkit 用户名。
2. 安装并确认 `NetworkManager`、`power-profiles-daemon`、`fwupd` 正常。
3. 创建 `/home/mac/toggle_power_wifi.sh`。
4. 创建并启用 `toggle-power-wifi.service`。
5. 创建 Polkit 最小权限规则。
6. 不创建 `systemd-logind` 合盖 drop-in，保留 Ubuntu 默认合盖策略。
7. 重置 GNOME 合盖设置，并写入锁屏设置。
8. 正常重启系统。
9. 按“验证方法”逐项确认。
10. 最后实际测试一次锁屏/解锁、接电合盖、电池合盖。
