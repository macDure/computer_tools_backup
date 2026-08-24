# `/dev/sda` 移动硬盘格式化与 Orin 挂载指南

## 设备信息

当前系统识别到：

- 设备：`/dev/sda`
- 容量：约 `1.82 TiB`
- 类型：USB 移动硬盘
- 型号：`KINGSTON SNV3S2000G`

本文采用 `GPT + 单个 ext4 分区`。ext4 适合 Linux/Orin 使用；如果还需要在 Windows/macOS 上直接读写，请改用 exFAT，不要执行本文的 ext4 格式化命令。

> 兼容性说明：部分旧版 Orin 系统的 `lsblk` 不支持 `MOUNTPOINTS`、`MODEL`、`TRAN` 字段，因此本文使用兼容性更好的 `lsblk -f` 和单数形式 `MOUNTPOINT`。

## 一、在当前电脑上格式化

> **警告：以下操作会删除 `/dev/sda` 上的全部数据。执行前必须再次确认型号、容量和 USB 连接状态。不要把系统盘 `/dev/nvme0n1` 当作目标盘。**

### 1. 确认目标盘

```bash
lsblk -d -o NAME,PATH,SIZE
lsblk -f /dev/sda
```

确认输出中的 `/dev/sda` 是约 1.82 TiB 的 `KINGSTON SNV3S2000G`，且没有需要保留的挂载点。

### 2. 卸载可能存在的分区

```bash
lsblk -lnpo NAME,MOUNTPOINT /dev/sda
sudo umount /dev/sda1 2>/dev/null || true
sudo umount /dev/sda2 2>/dev/null || true
```

如果实际显示了其他分区（例如 `/dev/sda3`），也先卸载对应分区：

```bash
sudo umount /dev/sda3
```

### 3. 创建 GPT 分区表和单个分区

```bash
sudo wipefs --all /dev/sda
sudo parted -s /dev/sda mklabel gpt
sudo parted -s -a optimal /dev/sda mkpart primary ext4 0% 100%
sudo partprobe /dev/sda
```

### 4. 创建 ext4 文件系统

```bash
sudo mkfs.ext4 -L orin-data /dev/sda1
```

检查结果并记录 UUID：

```bash
lsblk -f /dev/sda
sudo blkid /dev/sda1
```

输出应包含类似下面的内容（UUID 以实际输出为准）：

```text
/dev/sda1: LABEL="orin-data" UUID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" TYPE="ext4"
```

## 二、在当前电脑上测试挂载

```bash
sudo mkdir -p /home/mac/mkcode/application-core/data
sudo mount /dev/sda1 /home/mac/mkcode/application-core/data
df -hT /home/mac/mkcode/application-core/data
sudo touch /home/mac/mkcode/application-core/data/.mount-test
sudo rm /home/mac/mkcode/application-core/data/.mount-test
```

测试完成后安全卸载：

```bash
sync
sudo umount /home/mac/mkcode/application-core/data
```

## 三、在另一台 Orin 上挂载

把移动硬盘连接到 Orin 后，先确认设备名称。设备名称不一定是 `/dev/sda1`，应以 UUID 或实际 `lsblk` 输出为准。

```bash
lsblk -f
sudo blkid
```

找到标签为 `orin-data`、类型为 `ext4` 的分区，然后执行：

```bash
sudo mkdir -p /data/orin-disk
sudo mount /dev/sda1 /data/orin-disk
df -hT /data/orin-disk
```

如果 Orin 上分区名称不是 `/dev/sda1`，将上面命令中的设备名替换为实际名称，例如 `/dev/sdb1`。

## 四、配置 Orin 开机自动挂载（推荐）

在 Orin 上取得 UUID：

```bash
sudo blkid /dev/sda1
```

编辑 `/etc/fstab`：

```bash
sudo cp -a /etc/fstab /etc/fstab.bak.$(date +%Y%m%d-%H%M%S)
sudo nano /etc/fstab
```

追加一行，把 `实际UUID` 替换成 `blkid` 输出的 UUID：

```fstab
UUID=实际UUID  /data/orin-disk  ext4  defaults,nofail,x-systemd.device-timeout=10  0  2
```

验证配置：

```bash
sudo umount /data/orin-disk 2>/dev/null || true
sudo mount -a
findmnt /data/orin-disk
df -hT /data/orin-disk
```

`nofail` 表示移动硬盘未连接时 Orin 仍可正常启动。

## 五、权限设置（可选）

如果普通用户需要读写挂载目录，在 Orin 上执行。将用户名替换为实际用户名：

```bash
sudo chown -R 用户名:用户名 /data/orin-disk
```

如果该硬盘用于多个用户或服务，也可以使用用户组和权限管理，不建议盲目执行 `chmod -R 777`。

## 六、安全卸载

```bash
sync
sudo umount /data/orin-disk
```

如果提示设备忙，先退出该目录，并检查占用进程：

```bash
sudo lsof +f -- /data/orin-disk
```

## 七、根据本次格式化结果，在 Orin 上直接执行

本次硬盘实际信息如下：

```text
文件系统：ext4
标签：orin-data
UUID：1210cbf9-ca8f-41a9-adbe-fb40d2ff024c
```

将硬盘连接到 Orin 后，按顺序执行：

```bash
lsblk -f
sudo mkdir -p /data/orin-disk
sudo mount UUID=1210cbf9-ca8f-41a9-adbe-fb40d2ff024c /data/orin-disk
df -hT /data/orin-disk
```

确认能正常访问后，配置开机自动挂载：

```bash
sudo cp -a /etc/fstab /etc/fstab.bak.$(date +%Y%m%d-%H%M%S)
printf '%s\n' 'UUID=1210cbf9-ca8f-41a9-adbe-fb40d2ff024c  /data/orin-disk  ext4  defaults,nofail,x-systemd.device-timeout=10  0  2' | sudo tee -a /etc/fstab
sudo umount /data/orin-disk
sudo mount -a
findmnt /data/orin-disk
df -hT /data/orin-disk
```

如果最后的 `findmnt` 能看到 `/data/orin-disk`，说明配置成功。

> 注意：上面的普通 `fstab` 配置主要适用于开机时硬盘已经连接的情况。若 Orin 开机时没有插入硬盘，之后再热插入，系统不一定会主动重新执行挂载。插入后可手动执行：

```bash
sudo mount /data/orin-disk
```

`nofail` 只表示硬盘未连接时不阻塞开机，并不等于 USB 热插入后一定自动挂载。

如果希望“插入后，在访问目录时自动挂载”，可将 `/etc/fstab` 中原来的这一行：

```fstab
UUID=1210cbf9-ca8f-41a9-adbe-fb40d2ff024c  /data/orin-disk  ext4  defaults,nofail,x-systemd.device-timeout=10  0  2
```

替换为：

```fstab
UUID=1210cbf9-ca8f-41a9-adbe-fb40d2ff024c  /data/orin-disk  ext4  defaults,nofail,x-systemd.automount,x-systemd.device-timeout=10  0  2
```

然后重新加载配置：

```bash
sudo systemctl daemon-reload
sudo systemctl restart "$(systemd-escape -p --suffix=automount /data/orin-disk)"
```

之后硬盘插入 Orin，再访问 `/data/orin-disk` 时会触发挂载：

```bash
ls -la /data/orin-disk
findmnt /data/orin-disk
```

## 八、在 Orin 拷贝完成后安全卸载，再接回本机

### 1. 在 Orin 上安全卸载

先确认当前终端没有位于移动硬盘目录中：

```bash
cd ~
sync
```

检查是否仍有程序占用硬盘：

```bash
sudo lsof +f -- /data/orin-disk
```

如果只看到类似下面的警告，而没有列出占用 `/data/orin-disk` 的进程，通常可以忽略：

```text
lsof: WARNING: can't stat() fuse.gvfsd-fuse file system /run/user/xxx/gvfs
Output information may be incomplete.
```

这是桌面环境 GVFS 虚拟文件系统的提示，不代表移动硬盘有故障。确认没有其他占用输出后，可以继续执行卸载。如果卸载仍提示 `target is busy`，使用下面的命令查看占用进程：

```bash
sudo fuser -vm /data/orin-disk
```

如果没有输出，执行卸载：

```bash
sudo umount /data/orin-disk
```

确认已经卸载：

```bash
findmnt /data/orin-disk || echo "已卸载"
```

看到 `已卸载` 后，再拔出移动硬盘。不要在 `umount` 仍未返回时直接拔盘。

如果提示 `target is busy`，先关闭正在使用该目录的程序和终端，再检查：

```bash
sudo lsof +f -- /data/orin-disk
```

### 2. 接回本机后挂载

将硬盘连接回本机后，先确认设备和文件系统：

```bash
lsblk -f
sudo blkid /dev/sda1
```

确认看到标签 `orin-data` 和 UUID `1210cbf9-ca8f-41a9-adbe-fb40d2ff024c` 后，在本机执行：

```bash
sudo mkdir -p /home/mac/mkcode/application-core/data
sudo mount UUID=1210cbf9-ca8f-41a9-adbe-fb40d2ff024c /home/mac/mkcode/application-core/data
df -hT /home/mac/mkcode/application-core/data
```

以后在本机复制数据时使用目录：

```text
/home/mac/mkcode/application-core/data
```

设备名可能不是 `/dev/sda1`，所以推荐使用 UUID 挂载，不要依赖 `/dev/sda1` 这个设备名。

### 3. 本机拷贝完成后再次安全卸载

```bash
cd ~
sync
sudo lsof +f -- /home/mac/mkcode/application-core/data
sudo umount /home/mac/mkcode/application-core/data
```

如果卸载提示 `target is busy`，确认没有终端或程序正在使用该目录，然后执行：

```bash
sudo fuser -vm /home/mac/mkcode/application-core/data
```

确认卸载成功后，再把硬盘接回 Orin。

## 九、Orin 上挂载当前识别到的 exFAT 分区

如果 Orin 上显示：

```text
/dev/sda2  exfat  UUID=F2E9-D436
```

说明当前要挂载的是 exFAT 分区 `/dev/sda2`，不要使用之前 ext4 分区的 UUID。桌面自动挂载目录（例如 `/media/tel`）可能随插拔变化或消失，推荐使用固定目录挂载：

```bash
lsblk -f
sudo blkid /dev/sda2
sudo mkdir -p /data/orin-disk
sudo mount -t exfat UUID=F2E9-D436 /data/orin-disk
df -hT /data/orin-disk
ls -la /data/orin-disk
```

如果提示系统不支持 exFAT，安装所需工具：

```bash
sudo apt update
sudo apt install exfatprogs
```

安装后重新挂载：

```bash
sudo mount -t exfat UUID=F2E9-D436 /data/orin-disk
```

如果挂载失败，查看实际挂载状态和内核日志：

```bash
findmnt -rn -S /dev/sda2
sudo dmesg -T | tail -n 80
```
