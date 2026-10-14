# ThinkPad T14p Gen3 (Ubuntu 24.04) NVIDIA 显卡驱动安装与配置指南

本指南整理了针对搭载 NVIDIA 独显（Ada Lovelace 架构，如 RTX 4050/4060 等）的 ThinkPad T14p Gen3 笔记本电脑在 Ubuntu 24.04 系统下安装显卡驱动并设置为默认显示显卡的完整步骤。

---

## 核心问题背景

对于较新的 NVIDIA 显卡（如 Ada Lovelace 架构），在较新的 Linux 内核中，NVIDIA 驱动要求必须使用**开源内核模块（Open Kernel Modules）**。
如果安装了标准的闭源驱动（例如 `nvidia-driver-580` 或 `nvidia-driver-595`），可能会导致内核无法正常分配设备，报错：
> `NVRM: installed in this system requires use of the NVIDIA open kernel modules.`

此时运行 `nvidia-smi` 会提示 `No devices were found`。因此，必须安装带 **`-open`** 后缀的开源驱动版本。

---

## 安装步骤

### 第一步：清理现有驱动（可选但推荐）

如果系统内已尝试安装过其他版本的 NVIDIA 驱动，建议先彻底清理，避免出现依赖冲突或内核模块冲突。

打开终端执行以下命令：

```bash
sudo apt-get purge -y "*nvidia*"
sudo apt-get autoremove -y
```

### 第二步：更新软件源并安装开源版驱动

1. **更新本地包列表**：
   ```bash
   sudo apt-get update
   ```

2. **安装推荐的开源驱动（以目前推荐的 595 版本为例）**：
   同时安装 `nvidia-prime`（用于显卡切换管理）和 `nvidia-settings`（NVIDIA 控制面板）。
   ```bash
   sudo apt-get install -y nvidia-driver-595-open nvidia-prime nvidia-settings
   ```
   > **提示**：如果您想查看当前系统推荐的最新版本，可以运行 `ubuntu-drivers devices`。如果推荐了其他版本（如 `600-open`），可将上述命令中的 `595-open` 替换为推荐的版本号。

### 第三步：安装后立即禁止 NVIDIA 驱动自动更新（必做）

Ubuntu 的 `unattended-upgrades` 默认会自动安装安全更新；NVIDIA 驱动如果发布在 `noble-security` 中，也会被自动升级。2026-10-10 本机自动更新曾将驱动从 `595.84` 升至 `595.99.02`，但内存中仍运行旧版内核模块，导致 `nvidia-smi` 报 `Driver/library version mismatch`，并使 GPU 容器启动失败。

**每次新装系统后，首次安装 NVIDIA 驱动完成就执行以下配置；本指南的一键脚本已包含此步骤，会在安装成功后自动写入。** 配置持久保存在 `/etc/apt/apt.conf.d/`，不限定 `595` 分支，后续通过 APT 重装驱动或更换驱动分支时仍有效。

```bash
sudo tee /etc/apt/apt.conf.d/99-local-nvidia-driver-no-auto-upgrades > /dev/null <<'EOF'
// NVIDIA driver updates are installed manually during maintenance.
// Other automatic security updates remain enabled.
Unattended-Upgrade::Package-Blacklist {
    "^nvidia-(driver|dkms|kernel|firmware|compute-utils|utils)-";
    "^libnvidia-(cfg1|common|compute|decode|encode|extra|fbc1|gl)-";
    "^xserver-xorg-video-nvidia-";
    "^linux-(modules|objects|signatures)-nvidia-";
};
EOF
```

规则排除 NVIDIA 驱动、配套用户态库、固件和预编译内核模块的自动升级；保留其它系统安全更新，也不排除 `nvidia-container-toolkit`、`libnvidia-container1` 等容器工具。单独排除 `nvidia-driver-595-open` 元包不够，NVML 等组件也必须一起覆盖。

此配置只控制 `unattended-upgrades`，**手动执行 `apt upgrade`、`apt full-upgrade`、`apt install` 仍可能更新驱动**。需要升级时，应在保存工作后的维护窗口手动完成整套驱动更新，并核对内核模块和用户态库版本一致。无需为手动升级临时删除本规则，也无需关闭整个系统的自动安全更新。

官方机制说明：[Ubuntu 自动更新文档](https://ubuntu.com/server/docs/how-to/software/automatic-updates/)。

### 第四步：配置默认使用 NVIDIA 独显输出

运行以下命令，将显示模式设置为独显直连/专有渲染模式：

```bash
sudo prime-select nvidia
```

设置成功后，系统会提示 `Info: selecting the nvidia profile`，并自动更新 `initramfs`。

### 第五步：保存工作后按需手动重启

首次安装驱动或切换显卡模式后，需要安排重启以加载内核模块及图形配置。**先保存所有工作，再由用户手动执行；一键脚本不会自动重启电脑或图形桌面。** 若已有工作尚未保存，留待维护窗口操作：

```bash
sudo reboot
```

---

## 安装后验证

系统重启后，打开终端，执行以下命令进行检查：

### 1. 验证驱动加载状态
```bash
nvidia-smi
```
* **正常现象**：应该能够看到显卡型号（如 GeForce RTX 4050 Laptop）、显存使用情况以及驱动版本号（595.xx）。

### 2. 验证当前主显卡状态
```bash
prime-select query
```
* **正常输出**：`nvidia`

### 3. 验证运行模式 (X11/Wayland)
```bash
echo $XDG_SESSION_TYPE
```
* **说明**：在 X11 下 `prime-select nvidia` 的性能和兼容性最佳。

### 4. 验证驱动自动更新排除规则

```bash
apt-config dump | sed -n '/^Unattended-Upgrade::Package-Blacklist/p; /^APT::Periodic::Unattended-Upgrade/p'
```

应能看到上述四条驱动排除规则。如果系统原本开启自动安全更新，`APT::Periodic::Unattended-Upgrade` 应继续为 `"1"`；本指南只排除驱动，不更改系统原有的其它更新设置。

### 5. 需要恢复驱动自动更新时

仅在明确决定恢复自动升级后，删除本指南创建的单个配置文件：

```bash
sudo rm /etc/apt/apt.conf.d/99-local-nvidia-driver-no-auto-upgrades
```

随后重新运行第 4 项验证，确认这四条规则已消失。删除配置不会立即升级驱动；之后它们会重新参与自动安全更新。本方法没有设置 `apt-mark hold`，因此无需执行 `apt-mark unhold`。

---

## 自动化一键配置脚本

您也可以将以下内容保存为 `setup_nvidia.sh` 脚本，在另一台电脑上执行安装、驱动自动更新排除配置和默认显卡设置。**安装成功后脚本会自动禁止驱动自动升级；不会自动重启电脑或图形桌面。**

```bash
#!/bin/bash
set -euo pipefail

echo "=== 开始配置 NVIDIA 驱动、自动更新排除规则及默认显卡 ==="

# 1. 清理冲突
echo "[1/5] 清理旧驱动..."
sudo apt-get purge -y "*nvidia*"
sudo apt-get autoremove -y

# 2. 更新源并安装驱动
echo "[2/5] 安装开源版 NVIDIA 595 驱动..."
sudo apt-get update
sudo apt-get install -y nvidia-driver-595-open nvidia-prime nvidia-settings

# 3. 安装成功后自动禁止驱动自动升级，保留其它系统安全更新
echo "[3/5] 配置 NVIDIA 驱动自动更新排除规则..."
sudo tee /etc/apt/apt.conf.d/99-local-nvidia-driver-no-auto-upgrades > /dev/null <<'EOF'
// NVIDIA driver updates are installed manually during maintenance.
// Other automatic security updates remain enabled.
Unattended-Upgrade::Package-Blacklist {
    "^nvidia-(driver|dkms|kernel|firmware|compute-utils|utils)-";
    "^libnvidia-(cfg1|common|compute|decode|encode|extra|fbc1|gl)-";
    "^xserver-xorg-video-nvidia-";
    "^linux-(modules|objects|signatures)-nvidia-";
};
EOF
apt-config dump | sed -n '/^Unattended-Upgrade::Package-Blacklist/p'

# 4. 切换默认显卡
echo "[4/5] 设置独显为默认输出设备..."
sudo prime-select nvidia

# 5. 仅提示用户，不执行重启或图形桌面重启
echo "[5/5] 配置完成，NVIDIA 驱动自动升级已禁用！"
echo "=========================================================="
echo "请先保存所有工作，再在维护窗口手动重启以应用更改: sudo reboot"
echo "重启后可使用 nvidia-smi 和 prime-select query 进行验证。"
echo "=========================================================="
```

**执行脚本方法**：
```bash
chmod +x setup_nvidia.sh
./setup_nvidia.sh
```
