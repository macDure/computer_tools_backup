# Ubuntu 迁移到闲置 1T NVMe 的执行方案

更新时间：2026-09-16<br>
主机：`mac-ThinkPad-T14p-Gen-3`<br>
系统：Ubuntu 24.04.4 LTS，UEFI 启动

## 1. 已确认的目标与结论

本次只把现有磁盘上的 Ubuntu 迁移到闲置的 1T NVMe；旧盘上的 Windows 和旧 Ubuntu 都保留，不做整盘覆盖。

推荐流程：

```text
关键数据备份到服务器
  -> Ubuntu Live USB 中确认磁盘型号
  -> 给新盘建立 GPT/EFI/swap/ext4
  -> Clonezilla 仅复制 Ubuntu 根分区
  -> 为新根分区生成新 UUID，更新 fstab
  -> 将 GRUB 安装到新盘 EFI 分区
  -> 从新盘启动并验证，旧盘保留作为回滚
```

Clonezilla 的 `part_to_local_part` 支持分区到本地分区复制，`-r` 可用于让文件系统使用目标分区的更大空间；本方案在图形界面中选择对应的分区复制项，完成后再显式执行 `resize2fs`。[Clonezilla ocs-sr 手册](https://clonezilla.org/fine-print-live-doc.php?fullmode=0&path=.%2Fclonezilla-live%2Fdoc%2F98_ocs_related_command_manpages%2F01-ocs-sr.doc)

### 重要回答：迁移失败是否影响旧盘？

只要严格选择“分区到本地分区”，源分区是 `/dev/nvme0n1p6`、目标分区是新盘 `/dev/nvme1n1p3`，并且不执行任何写入 `/dev/nvme0n1` 的命令，Clonezilla 的失败通常只会使新盘不完整，**不会改写旧盘**。因此旧 Ubuntu 和 Windows 仍可从 BIOS/UEFI 启动。

这不是绝对保险：误选 `disk_to_local_disk`、把源目标选反、或在分区命令中写错设备名，都可能破坏源盘。因此每个破坏性命令前都必须用 `MODEL`、序列号、容量和分区结构复核；不要只凭 `/dev/nvme*` 名称。

服务器备份仍建议保留。它防范的是误操作、文件系统损坏、SSD 突发故障以及迁移后才发现文件损坏；“旧盘未被写入”只能提供回滚，不能替代独立副本。

## 2. 当前磁盘事实

```text
源盘 /dev/nvme0n1  953.9G  YMTC YMSS2CD08D25MC  serial=YMB51T0JA2546513J9
├─p1 260M  vfat  EFI，挂载 /boot/efi，UUID=3484-B896
├─p2 16M   Microsoft reserved
├─p3 450G  ntfs  Windows，UUID=26C88778C88744D1
├─p4 2G    ntfs  WinRE，UUID=1E0A87E60A87B973
├─p5 61G   swap  UUID=6f0ad98e-177e-48d7-8c52-46fd7299b995
└─p6 440.6G ext4 Ubuntu 根分区 /，UUID=5d4f34d0-6fee-4493-8357-bc158ffb645b

目标盘 /dev/nvme1n1  953.9G  UMIS RPJYJ1T24MLR1HWY  serial=SS1M63311Z3CD4AB25HT
当前无分区、文件系统、挂载点。
```

旧系统的 `/etc/fstab` 使用旧盘的三个 UUID。克隆后新根分区会继承旧 UUID，必须改成新 UUID；否则两块盘同时在线时可能挂载到错误的根分区。

## 3. 已执行的服务器关键备份

服务器：`lenovo@172.20.149.215`<br>
目标目录：

```text
/data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/home/mac/
```

备份策略是“关键数据优先”，不是完整镜像：

- 保留代码、文档、下载、配置、SSH/GPG、研究资料、Apollo records/maps、Docker Compose/配置等非缓存数据。
- Apollo 的 `data/log` 不备份；records/maps 保留。
- 不暂停容器；正在写入的数据库/日志属于在线一致性风险，迁移前应再执行一次增量同步，必要时再短暂停相关服务。
- 不保存 Docker 镜像层；完整系统迁移会复制 `/var/lib/docker`。服务器只保存 Docker 容器、镜像、卷和磁盘占用清单，便于恢复核对。

明确排除：

```text
.cache/**
mkcode/application-core/.cache/**
mkcode/application-core/.aem/**
mkcode/application-core/data/log/**
.vscode/extensions/**
.vscode-server/**
.npm/_cacache/**
macperson/deepseek-harness/node_modules/**
tmp/**
.local/share/Trash/**
v2raya-tproxy-kit/backups/legacy/**
```

首次 rsync 清单为 `556,619` 个文件/目录项，逻辑文件大小约 `132.50G`；收尾同步最终返回码为 0。最后一次只读 dry-run 仍看到 34 个在线变化项（主要是 SQLite WAL/SHM、日志、浏览器状态和心跳），这是服务继续写入造成的时间差，不是传输错误；若要求某一时刻完全一致，应在迁移前短暂停相关服务再同步。远端核对得到约 `126G`（含 SQLite 快照和 Docker 清单）、`476,541` 个普通文件、`75,808` 个目录、`4,340` 个符号链接、`5` 个特殊文件。备份目录权限设为远端用户私有（`0700`）。

由于服务器端不能无密码提权，备份采用普通用户 rsync：文件内容和符号链接已保留，但源文件的 root/特殊 ACL/xattr 所有权不承诺逐字节复原。两个由容器 root 创建、普通用户不可读的 Hermes 备份文件通过 Hermes 容器只读导出后单独保存：`.hermes/.env.bak-feishu-202608261740`、`.hermes/config.yaml.backup-20260826-160553-pre-migrate`。

另外生成了 18 个 SQLite Online Backup 快照（`.codex`、`.hermes`）到：

```text
/data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/application-consistent/sqlite/
```

快照清单为 `manifest.json`；其中 `goals_1.sqlite` 和 `memories_1.sqlite` 使用 immutable 只读模式（无 WAL sidecar），其余数据库使用 SQLite Online Backup API。

建议在备份完成后验证：

```bash
ssh lenovo@172.20.149.215 \
  'du -sh /data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme; \
   find /data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/home/mac -type f | wc -l; \
   find /data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/home/mac -type l | wc -l; \
   df -h /data'
```

再次同步（迁移前建议执行）：

```bash
rsync -aHSlx --numeric-ids --partial --info=progress2,stats2 \
  --exclude='.cache/***' \
  --exclude='mkcode/application-core/.cache/***' \
  --exclude='mkcode/application-core/.aem/***' \
  --exclude='mkcode/application-core/data/log/***' \
  --exclude='.vscode/extensions/***' \
  --exclude='.vscode-server/***' \
  --exclude='.npm/_cacache/***' \
  --exclude='macperson/deepseek-harness/node_modules/***' \
  --exclude='tmp/***' \
  --exclude='.local/share/Trash/***' \
  --exclude='v2raya-tproxy-kit/backups/legacy/***' \
  /home/mac/ \
  lenovo@172.20.149.215:/data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/home/mac/
```

## 4. 迁移前检查（在当前系统只读执行）

保存证据：

```bash
mkdir -p /home/mac/macperson/computer_tools_backup/migration-inventory-20260916
lsblk -e7 -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,PARTUUID,MOUNTPOINTS,MODEL,SERIAL \
  | tee /home/mac/macperson/computer_tools_backup/migration-inventory-20260916/lsblk.txt
findmnt -R / | tee /home/mac/macperson/computer_tools_backup/migration-inventory-20260916/findmnt.txt
df -hT | tee /home/mac/macperson/computer_tools_backup/migration-inventory-20260916/df.txt
sudo efibootmgr -v | tee /home/mac/macperson/computer_tools_backup/migration-inventory-20260916/efibootmgr.txt
cp -a /etc/fstab /home/mac/macperson/computer_tools_backup/migration-inventory-20260916/fstab.before
```

确认目标盘没有挂载点：

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL /dev/nvme1n1
findmnt -S /dev/nvme1n1
# `findmnt` 无输出才可继续。
```

不要在运行中的根系统上执行 `sgdisk`/`parted`/`mkfs`；以下破坏性步骤必须从 Ubuntu Live USB 执行。

## 5. 工具、两个 U 盘和启动顺序

建议准备两个 U 盘，并且每次只插入当前要启动的那个：

```text
U 盘 A：Ubuntu 24.04 Desktop Live USB（建议 8GB 或更大）
       用于分区、修改 UUID、fstab 和 GRUB
U 盘 B：Clonezilla Live USB（建议 2GB 或更大）
       用于复制 nvme0n1p6 -> nvme1n1p3
```

ISO 只从官方站点下载：Ubuntu Desktop（`ubuntu.com/download/desktop`）和 Clonezilla（`clonezilla.org/downloads.php`）。写盘时优先使用 Ubuntu 的“启动盘创建器”或“磁盘”应用：选择 ISO，选择正确的 U 盘，执行“恢复磁盘映像”。这会清空 U 盘，不会触碰 NVMe，前提是设备选择正确。

若使用终端写盘，先只插入一个 U 盘并确认设备名：

```bash
lsblk -dpno NAME,SIZE,MODEL,TRAN
```

然后把下面的占位符替换成明确的 ISO 路径和 U 盘**整盘**设备（例如 `/dev/sdb`，不要写 `/dev/sdb1`，更不能写 `/dev/nvme0n1` 或 `/dev/nvme1n1`）：

```bash
ISO_PATH="$HOME/Downloads/明确的镜像文件.iso"
USB_DEV=/dev/sdX       # 再次用 lsblk 核对型号和容量
sudo dd if="$ISO_PATH" of="$USB_DEV" bs=16M status=progress conv=fsync
sync
```

先制作 Ubuntu U 盘 A，再安全弹出并拔下；插入 U 盘 B，重复上述步骤制作 Clonezilla U 盘。制作完成后不要把两个 U 盘同时插着，以免启动时选错设备。

### Lenovo ThinkPad 一次性启动菜单

你的主机是 ThinkPad。重启或开机看到 Lenovo/ThinkPad 标志后，连续按 `F12`（功能键锁定时按 `Fn+F12`），进入一次性启动菜单；选择带有 `UEFI:` 前缀的对应 U 盘，然后回车。`F1`（或 `Fn+F1`）进入 BIOS 设置，只有需要检查 UEFI/Secure Boot 或永久启动顺序时才使用。Lenovo 官方说明也是 `F12` 临时选择启动设备、`F1` 进入 UEFI/BIOS。[Lenovo 启动顺序说明](https://download.lenovo.com/pccbbs/pubs/t590_p53s/html_en/en/Change_the_startup_sequence_%28topic%29_T0000683080.html)

严格按以下顺序操作：

```text
1. 关机；只插 Ubuntu U 盘 A。
2. 开机连续按 F12/Fn+F12，选择 UEFI: Ubuntu U 盘。
3. 进入 Try Ubuntu，确认 UMIS 新盘后执行第 6 节分区命令。
4. 关机；拔出 U 盘 A，只插 Clonezilla U 盘 B。
5. 开机按 F12/Fn+F12，选择 UEFI: Clonezilla U 盘。
6. 执行第 7 节的分区复制，完成后选择关机，不要直接启动旧系统。
7. 拔出 U 盘 B，再插回 U 盘 A，按 F12 进入 Try Ubuntu。
8. 执行第 8 节的 UUID/fstab/GRUB 收尾，关机并拔出 U 盘 A。
9. 不插 U 盘开机，按 F12 选择 Ubuntu-NewDisk 或新盘型号。
```

保持启动模式为 UEFI，不要切换到 Legacy/CSM。若 Clonezilla U 盘在 Secure Boot 下无法启动，可临时在 BIOS 中关闭 Secure Boot，迁移完成后再恢复；Ubuntu 新系统的 Secure Boot 处理见第 8 节。

## 6. Live USB：建立新盘布局

从 Ubuntu 24.04 Live USB 选择 `Try Ubuntu`，再次确认型号和序列号。以下命令假设目标仍为 `/dev/nvme1n1`：

```bash
sudo sgdisk --zap-all /dev/nvme1n1
sudo parted -s /dev/nvme1n1 mklabel gpt
sudo parted -s /dev/nvme1n1 mkpart ESP fat32 1MiB 1025MiB
sudo parted -s /dev/nvme1n1 set 1 esp on
sudo parted -s /dev/nvme1n1 mkpart primary linux-swap 1025MiB 66561MiB
sudo parted -s /dev/nvme1n1 mkpart primary ext4 66561MiB 100%
sudo partprobe /dev/nvme1n1

sudo mkfs.vfat -F32 -n EFI_UBUNTU /dev/nvme1n1p1
sudo mkswap -L swap_ubuntu /dev/nvme1n1p2
sudo mkfs.ext4 -L ubuntu-root /dev/nvme1n1p3
```

布局：`p1` 1G EFI，`p2` 64G swap，`p3` 剩余空间 ext4 根分区。若 Live USB 下设备名变化，必须以型号/序列号为准替换命令中的设备名。

## 7. Clonezilla：只复制 Ubuntu 根分区

启动 Clonezilla Live，选择：

```text
Start Clonezilla
  -> device-device
  -> Beginner
  -> part_to_local_part
```

源：`/dev/nvme0n1p6`（旧 Ubuntu ext4 根分区）<br>
目标：`/dev/nvme1n1p3`（新 Ubuntu ext4 根分区）

绝对不要选择：

```text
disk_to_local_disk
/dev/nvme0n1 -> /dev/nvme1n1
```

也不要复制旧 EFI、Windows、WinRE、旧 swap。文件系统检查可选择“检查源/目标”；不要选择会把源盘修复写回的选项。完成后关机，回到 Ubuntu Live USB。

## 8. Live USB：生成新 UUID、扩容并修复 GRUB

```bash
sudo e2fsck -f /dev/nvme1n1p3
sudo tune2fs -U random /dev/nvme1n1p3
sudo resize2fs /dev/nvme1n1p3
sudo blkid /dev/nvme1n1p1 /dev/nvme1n1p2 /dev/nvme1n1p3
```

挂载：

```bash
sudo mkdir -p /mnt/new
sudo mount /dev/nvme1n1p3 /mnt/new
sudo mkdir -p /mnt/new/boot/efi
sudo mount /dev/nvme1n1p1 /mnt/new/boot/efi
```

编辑 `/mnt/new/etc/fstab`，写入刚才 `blkid` 得到的新 UUID：

```text
UUID=<新 root UUID> / ext4 defaults 0 1
UUID=<新 EFI UUID> /boot/efi vfat defaults 0 1
UUID=<新 swap UUID> none swap sw 0 0
```

不要继续使用旧 UUID：`3484-B896`、`6f0ad98e-177e-48d7-8c52-46fd7299b995`、`5d4f34d0-6fee-4493-8357-bc158ffb645b`。

进入新系统修复 UEFI 引导：

```bash
for d in dev dev/pts proc sys run; do sudo mount --rbind "/$d" "/mnt/new/$d"; sudo mount --make-rslave "/mnt/new/$d"; done
sudo chroot /mnt/new /bin/bash
grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Ubuntu-NewDisk --recheck
update-initramfs -u -k all
update-grub
exit
sudo umount -R /mnt/new
sudo reboot
```

若机器启用了 Secure Boot 且 `grub-install` 报签名/ shim 错误，在 chroot 中补做 `apt install --reinstall grub-efi-amd64-signed shim-signed` 后再执行上面的 GRUB 命令。

BIOS/UEFI 启动菜单选择 `Ubuntu-NewDisk` 或型号为 `UMIS RPJYJ1T24MLR1HWY` 的新盘。

## 9. 首次启动验收

只有下面的结果全部指向 `nvme1n1`，才算迁移成功：

```bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
findmnt /
findmnt /boot/efi
swapon --show
df -hT /
sudo efibootmgr -v
docker ps
systemctl --failed
```

预期：`/`、`/boot/efi`、swap 全部来自型号为 `UMIS RPJYJ1T24MLR1HWY` 的新盘；Windows 仍在型号为 `YMTC YMSS2CD08D25MC` 的旧盘 p3。不要仅凭 `nvme0n1`/`nvme1n1` 判断；如果 `/` 来自旧盘 p6，说明启动的还是旧 Ubuntu，不能清理旧盘。

## 10. 回滚与旧盘处理

新盘启动失败时，在 BIOS/UEFI 选择旧盘的 Ubuntu 或 Windows Boot Manager；旧盘分区未被本方案写入，仍可正常使用。必要时从 Live USB 重新检查新盘的 UUID、`fstab` 和 GRUB。

新系统连续稳定运行至少 3–7 天后再考虑释放旧 Linux 空间。释放前再次确认 `findmnt /` 和 `findmnt /boot/efi` 指向 UMIS 新盘，并保留 YMTC 旧盘 EFI/Windows/WinRE 分区。不要在确认前删除旧盘的 p5 或 p6。

## 11. 最终执行清单

```text
[ ] 服务器关键备份已完成并通过远端计数/容量检查
[ ] 迁移前 lsblk、fstab、EFI 启动项证据已保存
[ ] Live USB 中用型号/序列号确认目标是 UMIS 新盘
[ ] 只对 /dev/nvme1n1 执行分区和格式化
[ ] Clonezilla 使用 part_to_local_part：nvme0n1p6 -> nvme1n1p3
[ ] 新 p3 已 e2fsck、tune2fs -U random、resize2fs
[ ] 新 fstab 只使用新 UUID
[ ] GRUB 已安装到新 p1，启动项为 Ubuntu-NewDisk
[ ] 首次启动验收全部指向 nvme1n1
[ ] 稳定 3–7 天后才处理旧 Linux 分区
```

## 12. 迁移稳定后删除旧 Ubuntu（只提供步骤，不在本机执行）

当前设备名已经发生过交换，下面的旧盘布局以**型号/序列号**为准：

```text
旧盘：YMTC YMSS2CD08D25MC，serial=YMB51T0JA2546513J9，当前设备名通常为 /dev/nvme1n1
├─p1 260M  EFI SYSTEM       必须保留，Windows Boot Manager 仍使用它
├─p2 16M   Microsoft 保留    必须保留
├─p3 450G  Windows           必须保留
├─p4 2G    WinRE_DRV         必须保留
├─p5 61G   旧 Linux swap     可删除
└─p6 440.6G 旧 Ubuntu ext4    可删除
```

### 12.1 删除前的硬性条件

至少稳定运行 3–7 天，并且在当前系统执行以下检查：

```bash
lsblk -e7 -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
findmnt /
findmnt /boot/efi
swapon --show
findmnt -S /dev/nvme1n1p6 || true
```

必须同时满足：

```text
/                 来自 UMIS 新盘的 nvme0n1p3
/boot/efi         来自 UMIS 新盘的 nvme0n1p1
swap              来自 UMIS 新盘的 nvme0n1p2
/dev/nvme1n1p6    没有挂载
```

服务器关键备份和 SQLite 快照必须仍然可访问。删除 p5/p6 是不可逆操作，不能因为当前系统已经启动就跳过这些检查。

### 12.2 是否必须使用 Ubuntu Live USB？

不是绝对必须。当前系统的 `/` 位于 UMIS 新盘，旧盘的 p5/p6 没有挂载且旧 p5 没有启用为 swap，因此理论上可以从当前系统删除旧 p5/p6。但这是不可逆的分区表操作，Live USB 更容易避免自动挂载、文件管理器占用和设备选错；如果有任何一项检查不满足，必须改用 Live USB。

当前系统直接操作前，先执行以下只读检查：

```bash
lsblk -e7 -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
findmnt /
findmnt /boot/efi
swapon --show
findmnt -S /dev/nvme1n1p5 || true
findmnt -S /dev/nvme1n1p6 || true
grep -E '6f0ad98e-177e-48d7-8c52-46fd7299b995|5d4f34d0-6fee-4493-8357-bc158ffb645b' /etc/fstab || true
```

只有确认当前根分区和 EFI 都在 UMIS 新盘、`swapon` 中没有旧 p5、两个 `findmnt` 都无输出、`fstab` 没有旧 UUID 后，才可以执行下面的当前系统终端方式。先再次确认 YMTC 型号和序列号；设备名如果变化，必须替换 `/dev/nvme1n1`：

```bash
lsblk -d -o NAME,SIZE,MODEL,SERIAL
sudo parted /dev/nvme1n1 print free
```

确认 `print free` 显示的 p1/p2/p3/p4 与本节布局一致后，才执行删除。下面只删除 p6 和 p5，不会删除 Windows 相关的 p1–p4：

```bash
sudo parted --script /dev/nvme1n1 rm 6
sudo parted --script /dev/nvme1n1 rm 5
sudo partprobe /dev/nvme1n1
sudo udevadm settle
lsblk -e7 -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL /dev/nvme1n1
```

`parted rm` 只删除分区表项，删除前必须人工确认设备型号；Ubuntu 的 parted 手册将 `rm partition` 定义为删除分区。[Ubuntu parted 手册](https://manpages.ubuntu.com/manpages/resolute/man8/parted.8.html)

### 12.3 使用 Live USB/GParted 删除旧 p5/p6（推荐）

如果不想在当前系统执行分区表写入，重启后按 `F12`/`Fn+F12`，启动 Ubuntu Live USB，选择 `Try Ubuntu`。

先确认设备：

```bash
lsblk -e7 -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
```

确认包含 Windows 的是 `YMTC YMSS2CD08D25MC`，包含当前运行 Ubuntu 的是 `UMIS RPJYJ1T24MLR1HWY`。如果设备名不是下面示例中的 `nvme1n1`，必须按型号替换。

推荐使用 GParted：

```text
1. 打开 GParted，选择 YMTC 旧盘（不要选择 UMIS 新盘）。
2. 确认 p1 EFI、p2 Microsoft 保留、p3 Windows、p4 WinRE_DRV 的位置。
3. 对旧 p5 swap 执行 Swapoff（如果显示已挂载）。
4. 删除旧 p5 和旧 p6；绝对不要删除 p1/p2/p3/p4。
5. 查看 Pending Operations，确认只包含删除 p5、删除 p6。
6. 点击 Apply，确认操作对象仍是 YMTC 旧盘，并等待进度条完全结束；GParted 的删除操作只有在 Apply 后才真正写入磁盘。[GParted 官方手册](https://gparted.org/display-doc.php?name=help-manual)
7. 删除完成后选择下面的一个分支：
   A. 继续在 Live USB 创建数据分区：执行第 12.5 节的 GParted 创建步骤。
   B. 只删除、不创建：打开终端执行 `sudo poweroff`，拔出 U 盘再开机；注意关机不会自动创建数据分区，之后仍需回到第 12.5 节创建并挂载。
```

如果选择分支 A，删除操作完成后在 GParted 中选择菜单 `View -> Refresh Devices`（或重新打开 GParted），应看到 YMTC 旧盘末尾的 `unallocated` 空间；不要在 UMIS 新盘上操作。

终端只读确认命令如下；这些命令不会删除分区：

```bash
findmnt -S /dev/nvme1n1p5 || true
findmnt -S /dev/nvme1n1p6 || true
```

不要使用 `rm -rf` 代替分区删除，也不要对 Windows p3 或 WinRE p4 执行 `mkfs`。

### 12.4 重要限制：旧盘空间不能直接扩展当前根分区

当前根分区是新物理盘上的 `/dev/nvme0n1p3`，旧 Ubuntu 空间位于另一块物理盘。普通 ext4 分区不能把另一块磁盘的空闲空间直接并入 `/dev/nvme0n1p3`；因此不能执行下面这种危险操作：

```bash
# 禁止：这不能把 nvme1n1 的空间扩展到 nvme0n1p3
sudo resize2fs /dev/nvme0n1p3 <把另一块盘的空间加进来>
```

如果目标是增加当前系统可用空间，最稳妥的方案是把旧盘 p5/p6 删除后，在释放出的空间创建一个**独立 ext4 数据分区**，挂载到 `/data` 或 `/home/mac/old-disk-data`。这会增加可用数据空间，但不会改变 `/` 的容量。若一定要让 `/` 成为跨盘的大分区，需要重新设计为 LVM/RAID 或重新安装系统，不建议在当前已运行的 ext4 根分区上改造。

### 12.5 把释放的旧盘空间创建为数据分区并挂载

在 GParted 中用 p5/p6 释放出的连续空间新建一个 ext4 分区：

```text
1. 选择 YMTC 旧盘上标为 unallocated 的连续空间。
2. 右键选择 New。
3. File system 选择 ext4，Label 填写 old-disk-data。
4. 点击 Add，把操作加入 Pending Operations。
5. 再次确认设备选择的是 YMTC 旧盘，点击 Apply，等待完成。
```

创建操作完成后，在 Live USB 终端核对标签和设备，不要凭分区编号猜测：

```bash
sudo partprobe
lsblk -f
sudo blkid -L old-disk-data
```

`blkid -L old-disk-data` 应输出新数据分区，例如 `/dev/nvme1n1p5`。如果输出为空，说明创建或格式化没有完成，先不要修改 fstab。确认无误后可以关机：

```bash
sudo poweroff
```

拔出 Ubuntu Live U 盘，正常启动已经迁移的 Ubuntu；**不要在 Live USB 中修改已安装系统的 `/etc/fstab`**。回到已迁移系统后，再继续下面的 `blkid`、备份 fstab、写入挂载项和 `mount -a` 步骤。

完成后回到已迁移的 Ubuntu 系统，查 UUID：

```bash
lsblk -f
sudo blkid /dev/nvme1n1p5
```

删除旧 p5/p6 后，新的数据分区编号可能是 `p5`，也可能因工具重新编号而不同；必须以 `lsblk -f` 的实际结果为准。

推荐挂载到 `/data`，避免覆盖当前 `/home/mac` 中已有内容：

```bash
sudo mkdir -p /data
sudo chown root:root /data
sudo chmod 755 /data
```

先备份当前 fstab，再编辑并加入一行（把 UUID 和分区设备替换成实际值）：

```bash
sudo cp -a /etc/fstab "/etc/fstab.before-old-ubuntu-delete.$(date +%Y%m%d-%H%M%S)"
sudoedit /etc/fstab
```

```text
UUID=<旧盘新数据分区UUID> /data ext4 defaults,nofail,x-systemd.device-timeout=5s 0 2
```

测试并设置普通用户可写目录：

```bash
sudo mount -a
findmnt /data
df -hT /data
sudo mkdir -p /data/mac-data
sudo chown mac:mac /data/mac-data
chmod 755 /data/mac-data
```

如果确实想挂载到用户目录，必须先使用一个空目录，例如：

```bash
sudo mkdir -p /home/mac/old-disk-data
sudo chown mac:mac /home/mac/old-disk-data
```

然后把 `/etc/fstab` 的挂载点改为 `/home/mac/old-disk-data`。不要把分区直接挂载到已有且非空的 `/home/mac`、`/home` 或 `/`，否则原有内容会被挂载点内容遮蔽。

### 12.6 删除旧 Ubuntu 后的验收

```bash
lsblk -e7 -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL
findmnt /
findmnt /boot/efi
swapon --show
findmnt /data
df -hT / /data
sudo efibootmgr -v
```

最终应看到：

```text
UMIS 新盘：Ubuntu 根、EFI、swap，继续负责启动系统
YMTC 旧盘：EFI、Microsoft 保留、Windows、WinRE 保留
YMTC 旧盘释放空间：作为独立 /data（或 /home/mac/old-disk-data）使用
```

本节只提供删除和挂载方法；本次不会替你执行删除分区、格式化或修改 `/etc/fstab`。
