# v2rayA tproxy 排坑包

这个目录集中保存 v2rayA tproxy 方案的排坑文档和配套脚本。

## 文件清单

```text
v2raya_install_guide.md
scripts/v2raya_set_tproxy.sh
scripts/v2raya_import_subscription.sh
systemd-user/v2raya-tproxy-setup.service
credentials/v2raya-web-credentials.txt
```

## 各文件作用

- `v2raya_install_guide.md`: 主排坑文档，包含安装、TUN 失败原因、tproxy 正确设置、重启后修复、订阅导入、账号密码坑点。
- `scripts/v2raya_set_tproxy.sh`: 核心恢复脚本。会从 v2rayN 当前配置同步 Shadowsocks 节点到 v2rayA，然后设置并启动 tproxy。
- `scripts/v2raya_import_subscription.sh`: 订阅导入脚本。用于绕过 v2rayA UI 输入问题，直接调用 `/api/import`。
- `systemd-user/v2raya-tproxy-setup.service`: 用户级 systemd 服务。登录后自动运行 `scripts/v2raya_set_tproxy.sh`。
- `credentials/v2raya-web-credentials.txt`: v2rayA Web API 登录凭据，权限应保持 `600`。

## 当前实际使用路径

```text
/home/mac/v2raya-tproxy-kit/v2raya_install_guide.md
/home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
/home/mac/v2raya-tproxy-kit/scripts/v2raya_import_subscription.sh
/home/mac/v2raya-tproxy-kit/credentials/v2raya-web-credentials.txt
/home/mac/.config/systemd/user/v2raya-tproxy-setup.service
```

## 常用命令

恢复 v2rayA tproxy：

```bash
bash /home/mac/v2raya-tproxy-kit/scripts/v2raya_set_tproxy.sh
```

导入订阅：

```bash
cat /tmp/v2raya-sub.txt | /home/mac/v2raya-tproxy-kit/scripts/v2raya_import_subscription.sh
```

查看自启动服务：

```bash
systemctl --user status v2raya-tproxy-setup.service --no-pager
```

## 安装包归档

```text
installers/installer_debian_x64_2.4.6.deb
installers/tinytun-v0.0.3-alpha.2-x86_64-unknown-linux-gnu.zip
installers/v2rayN-linux-64.tar.gz
```

这些文件只是安装/恢复用的归档，不参与当前运行。
