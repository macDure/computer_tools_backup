# Docker & NVIDIA Container Toolkit Ubuntu 24.04 安装指南

本指南记录了在 Ubuntu 24.04 LTS 系统上，从零安装 Docker 社区版 (Docker CE) 并配置 NVIDIA Container Toolkit，使 Docker 容器内能正常使用主机 NVIDIA 显卡显存与算力的完整步骤。

---

## 前提条件

在执行本指南前，请确保主机的 NVIDIA 驱动已正确安装并处于正常工作状态。
可执行以下命令进行检查：
```bash
nvidia-smi
```
如果能输出显卡型号、驱动版本及 CUDA 版本等信息，则说明驱动正常。

### 重要避坑：宿主机 NVIDIA 驱动必须先稳定

Docker 和 NVIDIA Container Toolkit 只负责把宿主机已经可用的 NVIDIA 设备映射进容器。它们不会修复宿主机显卡驱动。

如果宿主机执行 `nvidia-smi` 已经失败，例如：

```text
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.
```

则不要继续排查 Docker。先修宿主机驱动。

### 已遇到的坑：NVIDIA 用户态包和内核模块版本不一致

典型现象：

```bash
nvidia-smi
```

输出：

```text
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.
```

同时日志里出现类似：

```text
NVRM: API mismatch: the client 'nvidia-smi' has the version 595.84,
but this kernel module has the version 595.71.05.
```

这表示系统里 NVIDIA 用户态组件已经升级到新版本，但当前内存里仍加载着旧版 NVIDIA 内核模块。常见触发方式是：

1. 系统运行中执行了 `apt upgrade` 或自动更新；
2. NVIDIA 包从旧版本升级到新版本；
3. DKMS 已经在磁盘上编译/安装了新版模块；
4. 但旧模块仍在当前内核里运行；
5. 没有重启，于是 `nvidia-smi` 调用新版用户态库时，和旧内核模块发生 API mismatch。

这不是 Docker 或 NVIDIA Container Toolkit 导致的问题。Docker 文档里的步骤只是在宿主机驱动正常后配置容器运行时。

#### 快速诊断命令

检查用户态工具版本：

```bash
nvidia-smi
```

检查当前已加载的内核模块版本：

```bash
cat /sys/module/nvidia/version
```

检查 DKMS 已安装模块：

```bash
dkms status
```

检查当前磁盘上的模块信息：

```bash
modinfo nvidia | grep -E '^(filename|version):'
```

检查内核日志中的 NVIDIA 错误：

```bash
journalctl -k --no-pager | grep -Ei 'nvidia|nvrm|gsp|xid|firmware' | tail -n 120
```

检查设备节点是否存在：

```bash
ls -l /dev/nvidia*
```

如果 `/dev/nvidia*` 不存在，同时日志里有 `API mismatch`，优先按版本错配处理。

#### 最小修复方案

先重启：

```bash
sudo reboot
```

重启后验证：

```bash
nvidia-smi
cat /sys/module/nvidia/version
```

两边版本应一致。例如用户态和内核模块都应是 `595.84`。

#### 如果重启后仍失败

重新安装驱动包并重建 initramfs：

```bash
sudo apt-get install --reinstall nvidia-driver-595-open nvidia-dkms-595-open nvidia-utils-595 nvidia-firmware-595-595.84
sudo update-initramfs -u -k all
sudo reboot
```

重启后再次验证：

```bash
nvidia-smi
docker run --rm --gpus all ubuntu nvidia-smi
```

#### 如何尽量避免再次被坑

这个坑不能完全靠 Docker 配置绕过，因为根因是 Linux 内核模块和 NVIDIA 用户态组件的运行时版本不一致。可采取以下规避策略：

1. **每次 NVIDIA 驱动包升级后立即重启**

   看到 apt 升级了这些包时，不要继续跑 GPU 任务：

   ```text
   nvidia-driver-*
   nvidia-dkms-*
   nvidia-utils-*
   libnvidia-*
   nvidia-firmware-*
   linux-image-*
   linux-headers-*
   ```

   升级完成后直接：

   ```bash
   sudo reboot
   ```

2. **重启后先验证宿主机，再验证 Docker**

   ```bash
   nvidia-smi
   docker run --rm --gpus all ubuntu nvidia-smi
   ```

3. **如果机器要长期跑 GPU 任务，避免无人值守自动升级 NVIDIA 驱动**

   可以考虑暂时 hold 住 NVIDIA 驱动相关包，等有维护窗口时再手动升级：

   ```bash
   sudo apt-mark hold nvidia-driver-595-open nvidia-dkms-595-open nvidia-utils-595 nvidia-firmware-595-595.84
   ```

   需要升级时再解除：

   ```bash
   sudo apt-mark unhold nvidia-driver-595-open nvidia-dkms-595-open nvidia-utils-595 nvidia-firmware-595-595.84
   sudo apt-get update
   sudo apt-get upgrade
   sudo reboot
   ```

   注意：长期 hold 驱动会减少意外损坏，但也会延迟安全修复和兼容性更新。适合稳定优先的工作站，不适合无脑永久锁死。

---

## 第一步：安装 Docker CE

使用 Docker 官方推荐的方式，配置 apt 仓库并进行安装。

1. **更新包索引并安装必要依赖**：
   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl gnupg
   ```

2. **添加 Docker 官方 GPG 密钥**：
   ```bash
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   sudo chmod a+r /etc/apt/keyrings/docker.asc
   ```

3. **配置 Docker 官方 apt 仓库**：
   ```bash
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
     sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   ```

4. **安装 Docker 核心及插件**：
   ```bash
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

---

## 第二步：安装 NVIDIA Container Toolkit

1. **添加 NVIDIA Container Toolkit GPG 密钥和 APT 源**：
   ```bash
   sudo curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg --yes
   
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   ```

2. **更新软件源并进行安装**：
   ```bash
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   ```

---

## 第三步：配置 Docker 并重启守护进程

1. **使用 `nvidia-ctk` 配置 Docker 运行时**：
   此命令会自动修改 `/etc/docker/daemon.json` 配置文件，添加 `nvidia` 容器运行时选项。
   ```bash
   sudo nvidia-ctk runtime configure --runtime=docker
   ```

2. **重启 Docker 服务使配置生效**：
   ```bash
   sudo systemctl restart docker
   ```

---

## 第四步：配置免 sudo 运行 Docker（可选但推荐）

默认情况下，只有 root 用户和 docker 组的用户才能直接运行 docker 命令。为当前用户配置免 `sudo` 权限：

1. **将当前用户加入 `docker` 组**（此处以当前用户为例，或直接替换 `mac` 为您的具体用户名）：
   ```bash
   sudo usermod -aG docker $USER
   ```

2. **使组配置在当前终端会话中立即生效**：
   ```bash
   newgrp docker
   ```
   *(注：在其他已打开的终端中，您可能需要重新打开终端或重新登录系统才能使该配置生效。)*

---

## 第五步：验证测试

使用官方 ubuntu 镜像或 nvidia/cuda 镜像来测试显卡直通功能。

运行以下命令：
```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

### 预期输出
如果安装配置成功，您将看到类似下方的 NVIDIA-SMI 输出界面，表示 Docker 容器已经成功挂载并可以使用宿主机的 NVIDIA 显卡：

```text
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.71.05              Driver Version: 595.71.05      CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 5050 ...    Off |   00000000:01:00.0 Off |                  N/A |
| N/A   50C    P4             11W /   35W |    1510MiB /   8151MiB |      9%      Default |
+-----------------------------------------+------------------------+----------------------+
```
