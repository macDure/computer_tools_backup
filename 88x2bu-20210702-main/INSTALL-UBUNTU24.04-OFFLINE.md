# Ubuntu 24.04 离线安装 RTL8812BU/RTL8822BU 无线网卡驱动

本目录中的驱动模块名称是 `88x2bu`，适用于 RTL8812BU/RTL8822BU 芯片。当前这只网卡的 USB ID 是 `0bda:b812`。

> 重要：仅有源码还不够。编译驱动需要 GCC、Make、BC 和当前内核对应的 headers；完全无网时，必须提前把这些 `.deb` 包和源码一起准备好。

## 一、准备离线安装包

### 方法 A：另一台可联网的 Ubuntu 24.04 电脑

先在目标电脑记录内核版本和架构：

```bash
uname -r
dpkg --print-architecture
```

在另一台同为 Ubuntu 24.04、同为 `amd64` 的联网电脑上，使用目标机的内核版本替换下面的 `<目标内核版本>`：

```bash
mkdir -p ~/rtl88x2bu-debs
cd ~/rtl88x2bu-debs
sudo apt update
sudo apt-get --download-only -y -o Dir::Cache::archives="$PWD/" install \
  build-essential bc dkms \
  linux-headers-<目标内核版本> \
  iw rfkill usbutils
```

下载完成后，把下面两类内容复制到 U 盘：

1. `~/rtl88x2bu-debs/` 中的全部 `.deb` 文件；
2. 整个 `88x2bu-20210702-main` 源码目录。

如果联网电脑已经安装过某些依赖，APT 可能不会重新下载它们。最稳妥的做法是在一台干净的 Ubuntu 24.04 环境中执行上面的下载命令；目标机的内核 headers 必须与 `uname -r` 完全匹配。

### 方法 B：Ubuntu 安装 U 盘

如果安装介质中包含所需软件包，可以在目标机挂载安装介质后执行：

```bash
sudo apt-cdrom add
sudo apt install build-essential bc dkms linux-headers-$(uname -r)
```

如果提示找不到 `linux-headers-$(uname -r)`，需要用方法 A 准备对应版本的 headers。

## 二、在无网的新 Ubuntu 24.04 上安装依赖

假设 U 盘挂载在 `/media/$USER/USB`，先把依赖包复制到本地目录：

```bash
mkdir -p ~/rtl88x2bu-debs
cp /media/$USER/USB/rtl88x2bu-debs/*.deb ~/rtl88x2bu-debs/
```

安装本地 `.deb` 包：

```bash
sudo apt install --no-download ~/rtl88x2bu-debs/*.deb
```

如果因为包的安装顺序出现依赖提示，再执行：

```bash
sudo dpkg -i ~/rtl88x2bu-debs/*.deb
sudo apt-get -f install --no-download
```

确认编译环境和 headers 已存在：

```bash
command -v gcc make bc dkms
ls -ld /lib/modules/$(uname -r)/build
```

以上命令都能找到文件后，才进入驱动安装步骤。

## 三、安装前检查系统自带驱动

较新的 Ubuntu 内核可能已经自带 `rtw88_8822bu`。先插入网卡并查看当前绑定的驱动：

```bash
readlink -f /sys/class/net/wlx*/device/driver
```

如果输出包含 `/sys/bus/usb/drivers/rtw88_8822bu`，说明系统自带驱动已经在工作，不要再同时加载 `88x2bu`；直接使用系统自带驱动即可。如果没有无线接口，或输出为空，再继续下面的安装步骤。

## 四、安装本目录中的驱动

进入源码目录。目录名可以不同，但必须进入包含 `install-driver.sh` 的目录：

```bash
cd ~/macperson/88x2bu-20210702-main
```

使用 DKMS 安装，推荐执行：

```bash
sudo sh ./install-driver.sh NoPrompt
sudo depmod -a
sudo modprobe 88x2bu
```

`NoPrompt` 表示不打开编辑器、不自动重启，适合离线和无人值守安装。安装脚本会：

- 编译当前内核对应的 `88x2bu.ko`；
- 将驱动加入 DKMS，后续内核更新时自动重新编译；
- 安装 `/etc/modprobe.d/88x2bu.conf`；
- 安装完成后保留源码目录，方便以后维护。

不要同时为同一只网卡安装多个第三方驱动。当前源码已经包含针对 Ubuntu HWE 7.0 内核的兼容修补，必须使用本目录的完整源码。

## 五、验证驱动是否正常

插入网卡后执行：

```bash
lsusb -d 0bda:b812
lsmod | grep 88x2bu
ip -br link
nmcli device status
dkms status
```

正常时会看到一个新的无线接口，名称通常类似 `wlx...`，并且驱动路径应为 `rtl88x2bu`：

```bash
readlink -f /sys/class/net/wlx*/device/driver
```

输出包含下面内容即表示已绑定本驱动：

```text
/sys/bus/usb/drivers/rtl88x2bu
```

接口显示 `DORMANT` 或 `DISCONNECTED` 只表示还没有连接 Wi-Fi，不代表驱动安装失败。

## 六、连接 Wi-Fi

先查看接口名称和附近的 Wi-Fi：

```bash
nmcli device status
nmcli device wifi list ifname wlx接口名称
```

连接网络：

```bash
nmcli device wifi connect "WiFi名称" password "WiFi密码" ifname wlx接口名称
```

例如：

```bash
nmcli device wifi connect "HomeWiFi" password "your-password" ifname wlxe0e1a918d281
```

## 七、常见问题

### `Your kernel header files aren't properly installed`

当前运行内核没有对应 headers。先查看版本：

```bash
uname -r
```

然后准备完全同名的 `linux-headers-$(uname -r)` 离线安装包。不能用其他内核版本的 headers 代替。

### `bc: command not found`、`gcc: command not found` 或 `make: command not found`

说明依赖包没有安装完整，把联网电脑下载的全部 `.deb` 复制到目标机后重新执行第二节的安装命令。

### `modprobe: ERROR: could not insert '88x2bu'`

先查看内核日志：

```bash
sudo dmesg | tail -n 80
```

如果 Secure Boot 已启用，检查：

```bash
mokutil --sb-state
```

Secure Boot 开启时，需要按安装脚本提示导入并登记 DKMS 的 MOK 密钥；相关的 `mokutil`、`openssl` 等包也要提前准备好。

### 更新内核后网卡不能用

确保新内核的 headers 已安装，然后执行：

```bash
sudo dkms autoinstall -k $(uname -r)
sudo modprobe 88x2bu
```

查看 DKMS 状态：

```bash
dkms status
```
