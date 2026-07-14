# Linux 屏幕锁屏/解锁自动切换 WiFi 与节能模式

本文档整理了为您的系统设计的自动切换脚本与配置方案。该方案在屏幕锁屏时自动关闭 WiFi 并进入节能模式，在屏幕解锁时自动打开 WiFi 并进入性能模式。

---

## 🛠️ 设计方案与原理

对于 **Ubuntu GNOME** 系统，本方案利用以下三个核心组件实现自动化管理：

1. **D-Bus 信号监听 (GNOME ScreenSaver)**
   - 使用 `gdbus monitor` 监听会话总线上的 `org.gnome.ScreenSaver` 接口的 `ActiveChanged` 信号。该信号在锁屏时变为 `true`，解锁时变为 `false`。
2. **WiFi 状态切换 (NetworkManager)**
   - 使用 `nmcli radio wifi off` 和 `nmcli radio wifi on` 实现物理或软件层面的 WiFi 无线网卡启闭。
3. **能耗模式切换 (power-profiles-daemon)**
   - 使用 `powerprofilesctl set power-saver`（节能模式）和 `powerprofilesctl set performance`（性能模式）进行能效配置切换，无需 `sudo` 提权。
4. **服务常驻化 (Systemd User Service)**
   - 将脚本打包为 Systemd 用户级服务（User Service），随用户登录自动启动，并在意外退出时自动重启，无需 root 权限。

---

## 📄 脚本与配置文件

### 1. 自动化控制脚本

脚本路径：[toggle_power_wifi.sh](file:///home/mac/toggle_power_wifi.sh)

```bash
#!/bin/bash

# 确保获取正确的 D-Bus 会话总线地址
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

echo "Starting WiFi and Power Profile Toggle Service..."

# 锁屏处理函数
handle_lock() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Screen Locked: Disabling WiFi and setting power-saver mode..."
    nmcli radio wifi off
    powerprofilesctl set power-saver
}

# 解锁处理函数
handle_unlock() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Screen Unlocked: Enabling WiFi and setting performance mode..."
    nmcli radio wifi on
    powerprofilesctl set performance
}

# 启动时检查初始屏幕锁定状态
IS_LOCKED=$(gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive 2>/dev/null)

if [[ "$IS_LOCKED" == "(true,)" ]]; then
    handle_lock
else
    # 默认解锁状态
    handle_unlock
fi

# 持续监控 GNOME ScreenSaver 信号
gdbus monitor --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver | while read -r line; do
    if echo "$line" | grep -q "ActiveChanged (true,)"; then
        handle_lock
    elif echo "$line" | grep -q "ActiveChanged (false,)"; then
        handle_unlock
    fi
done
```

### 2. Systemd 用户服务配置

服务文件路径：[toggle-power-wifi.service](file:///home/mac/.config/systemd/user/toggle-power-wifi.service)

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

---

## ⚙️ 管理命令

所有的服务管理均在**用户权限**下进行，无需 `sudo`：

* **重新加载 systemd 守护进程**（当修改服务文件后）：
  ```bash
  systemctl --user daemon-reload
  ```
* **启用服务（开机/登录自动运行）**：
  ```bash
  systemctl --user enable toggle-power-wifi.service
  ```
* **手动启动服务**：
  ```bash
  systemctl --user start toggle-power-wifi.service
  ```
* **手动停止服务**：
  ```bash
  systemctl --user stop toggle-power-wifi.service
  ```
* **查看服务状态**：
  ```bash
  systemctl --user status toggle-power-wifi.service
  ```
* **实时查看运行日志**：
  ```bash
  journalctl --user -u toggle-power-wifi.service -f
  ```

---

## 💡 注意事项与自定义

1. **修改为平衡模式（Balanced）**
   如果您觉得性能模式（performance）发热量过大，可以在脚本中将 `powerprofilesctl set performance` 修改为 `powerprofilesctl set balanced`。
2. **测试与排查**
   如果发现锁屏后 WiFi 未断开，可先运行以下命令查看是否有报错日志：
   `journalctl --user -u toggle-power-wifi.service -n 50`
