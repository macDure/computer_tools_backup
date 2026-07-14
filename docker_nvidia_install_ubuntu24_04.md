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
