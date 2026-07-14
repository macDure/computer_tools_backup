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

### 第三步：配置默认使用 NVIDIA 独显输出

运行以下命令，将显示模式设置为独显直连/专有渲染模式：

```bash
sudo prime-select nvidia
```

设置成功后，系统会提示 `Info: selecting the nvidia profile`，并自动更新 `initramfs`。

### 第四步：重启系统

为使内核重新加载 NVIDIA 开源模块以及图形服务应用配置，请重启电脑：

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

---

## 自动化一键配置脚本

您也可以将以下内容保存为 `setup_nvidia.sh` 脚本，在另一台电脑上直接一键执行：

```bash
#!/bin/bash
set -e

echo "=== 开始配置 NVIDIA 驱动及默认显卡 ==="

# 1. 清理冲突
echo "[1/4] 清理旧驱动..."
sudo apt-get purge -y "*nvidia*"
sudo apt-get autoremove -y

# 2. 更新源并安装驱动
echo "[2/4] 安装开源版 NVIDIA 595 驱动..."
sudo apt-get update
sudo apt-get install -y nvidia-driver-595-open nvidia-prime nvidia-settings

# 3. 切换默认显卡
echo "[3/4] 设置独显为默认输出设备..."
sudo prime-select nvidia

# 4. 提示重启
echo "[4/4] 配置完成！"
echo "=========================================================="
echo "请手动重启您的电脑以应用更改: sudo reboot"
echo "重启后可使用 nvidia-smi 和 prime-select query 进行验证。"
echo "=========================================================="
```

**执行脚本方法**：
```bash
chmod +x setup_nvidia.sh
./setup_nvidia.sh
```
