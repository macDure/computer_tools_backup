# Ubuntu 迁移到闲置 1T 硬盘的安全稳妥方案

生成时间：2026-07-31  
当前系统：Ubuntu 24.04.4 LTS，UEFI 启动  
当前主机：mac-ThinkPad-T14p-Gen-3

## 0. 结论：建议使用 Clonezilla 分区克隆，但不要整盘克隆

结合你当前电脑的磁盘结构，以及你“第一次迁移、关键是完整成功”的目标，我建议采用：

```text
Ubuntu Live USB/GParted 先给新盘分区
-> Clonezilla 再生龙只克隆 Ubuntu 根分区
-> Ubuntu Live USB 修正 UUID、fstab、GRUB
-> 从新盘启动并验证
```

这比纯 `rsync` 更适合你：

- Clonezilla 做分区克隆，能最大程度保持原 Ubuntu 根分区内容、权限、ACL、扩展属性、系统文件结构，手工遗漏风险更低。
- 不做整盘克隆，可以避免把 Windows、WinRE、旧 EFI 一起复制到新盘。
- 新盘单独建 EFI 分区和 GRUB，迁移后 Ubuntu 可以独立从新盘启动。
- 旧盘不动，迁移失败也能回到原 Ubuntu 或 Windows，回滚简单。

注意：Clonezilla 负责“复制系统内容”，但你的机器是 UEFI 双系统，克隆后仍必须修 `fstab` 和 GRUB。否则两块盘同时在线时，旧分区和新分区 UUID 重复，可能启动到旧系统或挂载错分区。

## 1. 当前磁盘情况

当前检查结果：

```text
源硬盘：/dev/nvme0n1  953.9G  YMTC YMSS2CD08D25MC
├─nvme0n1p1   260M  vfat   EFI 分区，挂载 /boot/efi，UUID=3484-B896
├─nvme0n1p2    16M  Microsoft 保留分区
├─nvme0n1p3   450G  ntfs   Windows，UUID=26C88778C88744D1
├─nvme0n1p4     2G  ntfs   WinRE_DRV，UUID=1E0A87E60A87B973
├─nvme0n1p5    61G  swap   Linux swap，UUID=6f0ad98e-177e-48d7-8c52-46fd7299b995
└─nvme0n1p6 440.6G  ext4   Ubuntu 根分区 /，UUID=5d4f34d0-6fee-4493-8357-bc158ffb645b

目标硬盘：/dev/nvme1n1  953.9G  UMIS RPJYJ1T24MLR1HWY
当前未看到分区、文件系统或挂载点。
```

`/etc/fstab` 当前内容依赖旧盘 UUID：

```text
/dev/disk/by-uuid/6f0ad98e-177e-48d7-8c52-46fd7299b995 none swap sw 0 0
/dev/disk/by-uuid/5d4f34d0-6fee-4493-8357-bc158ffb645b / ext4 defaults 0 1
/dev/disk/by-uuid/3484-B896 /boot/efi vfat defaults 0 1
```

风险点：

- 当前 Linux 和 Windows 共用 `/dev/nvme0n1`。
- 如果整盘克隆，会把 Windows 一起复制到新盘，而且 EFI/root/swap UUID 会重复。
- 如果只克隆 Linux 根分区，也会复制根分区 UUID，所以克隆后必须给新根分区生成新 UUID 并修改 `fstab`。

## 2. 目标新盘分区布局

目标盘 `/dev/nvme1n1` 建议使用 GPT：

```text
/dev/nvme1n1p1   1G     FAT32   EFI System Partition    /boot/efi
/dev/nvme1n1p2   64G    linux-swap                     swap
/dev/nvme1n1p3   剩余   ext4                            /
```

说明：

- `/dev/nvme1n1p3` 用来接收 Clonezilla 从 `/dev/nvme0n1p6` 克隆来的 Ubuntu 根分区。
- `/dev/nvme1n1p1` 是新盘自己的 EFI 分区，不复制旧 EFI，后面用 `grub-install` 生成。
- `/dev/nvme1n1p2` 是新 swap，直接新建，不需要克隆旧 swap。

## 3. 迁移前准备

### 3.1 备份

即使方案以保留旧盘为回滚基础，仍建议先备份关键数据：

```text
/home/mac
/etc
重要项目目录
浏览器资料
SSH key
密码库
Docker 数据
虚拟机镜像
```

建议保存当前磁盘和启动信息：

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,PARTUUID,MOUNTPOINTS,MODEL > ~/disk-layout-before-migration.txt
sudo efibootmgr -v > ~/efi-boot-before-migration.txt
sudo cp -a /etc/fstab ~/fstab.before-migration
```

### 3.2 准备两个启动盘

建议准备：

- Clonezilla Live USB：用于克隆 Ubuntu 根分区。
- Ubuntu 24.04 Live USB：用于分区、改 UUID、改 `fstab`、修 GRUB、排查启动问题。

如果只想准备一个，也可以只准备 Ubuntu Live USB，然后用 `rsync` 方案。但从“第一次迁移、降低遗漏风险”的角度，两个启动盘更稳。

## 4. 第一步：用 Ubuntu Live USB 给新盘分区

1. 重启，从 Ubuntu Live USB 启动。
2. 选择 `Try Ubuntu`。
3. 打开终端，确认磁盘：

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL
```

必须确认：

```text
源盘：包含 Windows、EFI、Ubuntu 的 YMTC YMSS2CD08D25MC
目标盘：闲置的 UMIS RPJYJ1T24MLR1HWY
```

警告：Live USB 下 `/dev/nvme0n1` 和 `/dev/nvme1n1` 顺序理论上可能变化。必须同时看 `MODEL`、容量、分区结构。

以下命令假设目标盘仍是 `/dev/nvme1n1`。

```bash
sudo sgdisk --zap-all /dev/nvme1n1
sudo parted -s /dev/nvme1n1 mklabel gpt
sudo parted -s /dev/nvme1n1 mkpart ESP fat32 1MiB 1025MiB
sudo parted -s /dev/nvme1n1 set 1 esp on
sudo parted -s /dev/nvme1n1 mkpart primary linux-swap 1025MiB 66561MiB
sudo parted -s /dev/nvme1n1 mkpart primary ext4 66561MiB 100%
sudo partprobe /dev/nvme1n1
```

格式化 EFI 和 swap。根分区可以先格式化，也可以让 Clonezilla 覆盖；这里先格式化便于确认分区无误：

```bash
sudo mkfs.vfat -F32 -n EFI_UBUNTU /dev/nvme1n1p1
sudo mkswap -L swap_ubuntu /dev/nvme1n1p2
sudo mkfs.ext4 -L ubuntu-root /dev/nvme1n1p3
```

关机或重启，准备进入 Clonezilla。

## 5. 第二步：用 Clonezilla 只克隆 Ubuntu 根分区

从 Clonezilla Live USB 启动。

推荐选择路径：

```text
Clonezilla live
-> Start Clonezilla
-> device-device
-> Beginner mode
-> part_to_local_part
```

源分区选择：

```text
/dev/nvme0n1p6   ext4   当前 Ubuntu 根分区
```

目标分区选择：

```text
/dev/nvme1n1p3   ext4   新盘根分区
```

不要选择：

```text
disk_to_local_disk
/dev/nvme0n1 整盘 -> /dev/nvme1n1 整盘
```

不要克隆这些分区：

```text
/dev/nvme0n1p1 EFI
/dev/nvme0n1p2 Microsoft 保留分区
/dev/nvme0n1p3 Windows
/dev/nvme0n1p4 WinRE
/dev/nvme0n1p5 swap
```

Clonezilla 如果询问是否检查/修复文件系统，建议选择检查源文件系统、完成后检查目标文件系统。时间会更长，但更稳。

Clonezilla 完成后关机，不要急着直接从新盘启动。先进入 Ubuntu Live USB 做收尾。

## 6. 第三步：修正新系统 UUID、fstab 和 GRUB

从 Ubuntu Live USB 启动，选择 `Try Ubuntu`。

再次确认分区：

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL
```

### 6.1 给新根分区生成新 UUID

Clonezilla 分区克隆通常会把源根分区 UUID 也复制过来。现在旧根分区和新根分区可能都是：

```text
5d4f34d0-6fee-4493-8357-bc158ffb645b
```

必须给新根分区改 UUID：

```bash
sudo e2fsck -f /dev/nvme1n1p3
sudo tune2fs -U random /dev/nvme1n1p3
sudo e2fsck -f /dev/nvme1n1p3
sudo resize2fs /dev/nvme1n1p3
```

说明：

- `tune2fs -U random` 只改新根分区 UUID，避免和旧根分区冲突。
- `resize2fs` 让克隆后的 ext4 文件系统扩展到整个新分区。

### 6.2 挂载新系统

```bash
sudo mkdir -p /mnt/new
sudo mount /dev/nvme1n1p3 /mnt/new
sudo mkdir -p /mnt/new/boot/efi
sudo mount /dev/nvme1n1p1 /mnt/new/boot/efi
```

查看新分区 UUID：

```bash
sudo blkid /dev/nvme1n1p1 /dev/nvme1n1p2 /dev/nvme1n1p3
```

记录：

```text
新 EFI UUID：/dev/nvme1n1p1 的 UUID
新 swap UUID：/dev/nvme1n1p2 的 UUID
新 root UUID：/dev/nvme1n1p3 的 UUID
```

### 6.3 修改新系统 fstab

编辑：

```bash
sudo nano /mnt/new/etc/fstab
```

把旧 UUID 替换成新 UUID。最终结构应类似：

```text
UUID=<新swap分区UUID> none swap sw 0 0
UUID=<新root分区UUID> / ext4 defaults 0 1
UUID=<新EFI分区UUID> /boot/efi vfat defaults 0 1
```

不能继续使用旧 UUID：

```text
3484-B896
6f0ad98e-177e-48d7-8c52-46fd7299b995
5d4f34d0-6fee-4493-8357-bc158ffb645b
```

### 6.4 chroot 并安装新盘 GRUB

```bash
sudo mount --bind /dev /mnt/new/dev
sudo mount --bind /dev/pts /mnt/new/dev/pts
sudo mount --bind /proc /mnt/new/proc
sudo mount --bind /sys /mnt/new/sys
sudo mount --bind /run /mnt/new/run
sudo chroot /mnt/new
```

在 chroot 里执行：

```bash
grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Ubuntu-NewDisk --recheck
update-initramfs -u -k all
update-grub
exit
```

如果 Live USB 网络可用，也可以在 chroot 中先重装 GRUB 包：

```bash
apt update
apt install --reinstall grub-efi-amd64 shim-signed
```

网络不可用时，不重装包也可以先执行 `grub-install`。

### 6.5 卸载并重启

```bash
sudo umount -R /mnt/new
sudo reboot
```

重启时进入 BIOS/UEFI 启动菜单，选择：

```text
Ubuntu-NewDisk
```

或选择目标盘：

```text
UMIS RPJYJ1T24MLR1HWY
```

## 7. 第四步：首次从新盘启动后的验证

进入系统后执行：

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL
findmnt /
findmnt /boot/efi
swapon --show
df -hT /
sudo efibootmgr -v
```

必须确认：

```text
/          来自 /dev/nvme1n1p3
/boot/efi  来自 /dev/nvme1n1p1
swap       来自 /dev/nvme1n1p2
Windows    仍在旧盘 /dev/nvme0n1p3
```

如果 `/` 仍来自 `/dev/nvme0n1p6`，说明还没有真正从新系统启动，不能清理旧盘。

验证常用工作环境：

```bash
docker ps
snap list
systemctl --failed
ls -la /home/mac
```

根据你的当前挂载情况，Docker 数据和项目目录都在根分区 `/dev/nvme0n1p6` 内，Clonezilla 分区克隆会把它们作为根分区内容一起复制到新盘。

## 8. 回滚方案

迁移完成前不要删除旧盘任何分区。

如果新盘无法启动：

1. 进入 BIOS/UEFI。
2. 选择旧盘原来的 Ubuntu 或 Windows Boot Manager。
3. 原 Ubuntu 仍在 `/dev/nvme0n1p6`。
4. Windows 仍在 `/dev/nvme0n1p3`。
5. 从 Ubuntu Live USB 重新检查新盘 UUID、`/mnt/new/etc/fstab` 和 GRUB。

常见修复命令：

```bash
sudo mount /dev/nvme1n1p3 /mnt/new
sudo mount /dev/nvme1n1p1 /mnt/new/boot/efi
sudo mount --bind /dev /mnt/new/dev
sudo mount --bind /dev/pts /mnt/new/dev/pts
sudo mount --bind /proc /mnt/new/proc
sudo mount --bind /sys /mnt/new/sys
sudo mount --bind /run /mnt/new/run
sudo chroot /mnt/new
grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Ubuntu-NewDisk --recheck
update-initramfs -u -k all
update-grub
exit
sudo umount -R /mnt/new
```

## 9. 稳定运行后处理旧盘空间

建议从新盘正常工作 3 到 7 天后，再考虑处理旧盘 Linux 分区。

删除旧 Linux 分区前，再确认：

```bash
findmnt /
findmnt /boot/efi
```

只有当结果确认：

```text
/          来自 /dev/nvme1n1p3
/boot/efi  来自 /dev/nvme1n1p1
```

才可以处理旧盘上的：

```text
/dev/nvme0n1p5 旧 swap
/dev/nvme0n1p6 旧 Ubuntu
```

旧盘建议保留：

```text
/dev/nvme0n1p1 EFI
/dev/nvme0n1p2 Microsoft 保留分区
/dev/nvme0n1p3 Windows
/dev/nvme0n1p4 WinRE
```

## 10. 最低风险执行清单

```text
1. 备份 /home/mac 和重要工作数据。
2. 保存 lsblk、fstab、efibootmgr 输出。
3. Ubuntu Live USB 启动。
4. 用 MODEL 和分区结构确认源盘、目标盘。
5. 清空并分区目标盘 /dev/nvme1n1。
6. 创建新 EFI、新 swap、新 root 分区。
7. Clonezilla 启动。
8. 选择 device-device -> Beginner -> part_to_local_part。
9. 只克隆 /dev/nvme0n1p6 到 /dev/nvme1n1p3。
10. 回到 Ubuntu Live USB。
11. 对 /dev/nvme1n1p3 执行 e2fsck、tune2fs -U random、resize2fs。
12. 修改 /mnt/new/etc/fstab 为新盘 UUID。
13. chroot 新系统，grub-install 到新 EFI。
14. 重启，从 Ubuntu-NewDisk 或新盘启动。
15. 验证 /、/boot/efi、swap 全部来自 nvme1n1。
16. 稳定运行 3 到 7 天后再清理旧盘 Linux 分区。
```

## 11. 关键安全原则

- 不做整盘克隆。
- 只克隆 Ubuntu 根分区 `/dev/nvme0n1p6`。
- 目标一定是 `UMIS RPJYJ1T24MLR1HWY`，不要只凭 `/dev/nvme1n1`。
- Clonezilla 完成后必须修改新根分区 UUID。
- 新系统 `/etc/fstab` 必须写新盘 UUID。
- GRUB 安装到新盘 EFI 分区 `/dev/nvme1n1p1`。
- 旧盘在新系统稳定前完全保留，这是最重要的回滚保障。

