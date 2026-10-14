# v2rayN AutoSwitch 部署文档

## 1. 适用环境

本 bundle 按当前生产拓扑整理，目标机需要保持以下布局，或在安装前按实际路径调整脚本中的常量：

| 项目 | 当前约定 |
|---|---|
| 宿主用户 | `mac`，UID 1000 |
| v2rayN 目录 | `/home/mac/v2rayN-linux-64` |
| Hermes home | `/home/mac/.hermes` |
| Hermes 容器脚本目录 | `/opt/data/scripts` |
| runner 内宿主映射 | `/home/mac` → 宿主 `/home/mac` |
| v2rayN 数据库 | `/home/mac/v2rayN-linux-64/guiConfigs/guiNDB.db` |
| xray 可执行文件 | `/home/mac/v2rayN-linux-64/bin/xray/xray` |
| 代理端口 | `127.0.0.1:10808` |
| runner 镜像 | `hermes-agent:local` |

`v2rayn_autoswitch.sh` 和 wrapper 依赖 `/opt/data/scripts`，因此应在与当前相同的 Hermes 工具容器/路径环境中执行。若目标机的 Hermes 脚本目录不同，先做路径适配，不要直接启用 cron。

## 2. 前置条件

在目标机准备：

- Ubuntu/Linux，用户 UID 1000 与 v2rayN 文件属主匹配；
- v2rayN 已安装并能启动，xray 位于 `bin/xray/xray`；
- `guiConfigs/guiNDB.db` 已由 v2rayN 创建，并至少有一个启用订阅；
- `curl`、`python3`、`flock`、`timeout`、Docker；
- Docker 镜像 `hermes-agent:local`；
- `geosite.dat`、`geoip.dat` 位于 v2rayN 的 `bin/` 目录；
- 如需飞书告警，Hermes `.env` 有 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`，并授予机器人发消息权限。

不要把当前机器的 `guiNDB.db` 直接复制到目标机；它包含订阅节点凭据。目标机应在 v2rayN GUI 中重新添加订阅并更新一次。

## 3. 安装源码

把本目录复制到目标机后执行：

```bash
cd /home/mac/macperson/computer_tools_backup/v2rayn-autoswitch
sudo bash deployment/deploy.sh
```

安装脚本会：

- 将 `current/autoswitch/` 安装到 v2rayN 的 `autoswitch/`；
- 不覆盖已有 `autoswitch/config.conf`；没有配置时从模板生成；
- 将当前脚本安装到 `/home/mac/.hermes/scripts/`，并在 `/opt/data/scripts/` 存在时同步一份；
- 安装 `deliver_feishu.py` 到 `scripts/shuimu_daily/`；
- 创建日志和状态目录；
- 不复制数据库、`.env`、运行日志、订阅原文或当前节点配置。

如果目标机不是当前路径布局，使用环境变量调整：

```bash
V2RAYN_DIR=/实际/v2rayN-linux-64 \
HERMES_HOME=/实际/.hermes \
TARGET_UID=1000 TARGET_GID=1000 \
sudo -E bash deployment/deploy.sh
```

安装器按 UID/GID 设置文件属主，不要求 runner 容器内存在宿主用户名 `mac`。

注意：当前源码内部仍使用 `/home/mac`、`/opt/data/scripts` 等生产路径。环境变量适合调整安装目标；跨布局使用前，应同步检查 wrapper 中的绝对路径。
## 4. 建立 runner

```bash
sudo bash deployment/bootstrap_runner.sh
sudo docker ps --filter name=v2rayn-switch-runner
```

runner 必须使用以下安全边界：

```bash
docker run -d --name v2rayn-switch-runner --restart unless-stopped \
  --pid=host --network=host --user 1000:1000 \
  --security-opt apparmor=unconfined --security-opt seccomp=unconfined \
  -v /home/mac:/home/mac \
  --entrypoint /usr/bin/tail hermes-agent:local -f /dev/null
```

实际切换命令使用 `docker exec -u 0`，因为需要给宿主 fallback xray/v2rayN 发送信号；不要使用 `--privileged`。

## 5. v2rayN 初始配置

1. 以宿主 UID 1000 用户启动 v2rayN GUI；
2. 在 GUI 中重新添加订阅，执行一次订阅更新；
3. 确认节点备注能解析出 `c1s1`、`c1s2`、`c1s3` 等名称；
4. 检查 `autoswitch/config.conf`，默认关键值为：

```ini
main_port = 10808
prefer_after_update = c1s1,c1s2
restart_v2rayn = true
backup_keep = 5
```

5. 确认系统代理仍指向 `127.0.0.1:10808`；
6. 若需要告警，把目标机 Feishu 应用凭据放入 `.env`，并修改 `current/scripts/shuimu_daily/deliver_feishu.py` 中的 `CHAT_ID` 为目标会话。不要把凭据写入脚本或本 bundle。

## 6. 安装后验收

先做无副作用检查：

```bash
sudo docker exec -u 0 v2rayn-switch-runner \
  python3 /home/mac/.hermes/scripts/v2rayn_mode_guard.py --dry-run

sudo docker exec -u 0 v2rayn-switch-runner \
  bash -c 'cd /home/mac/v2rayN-linux-64/autoswitch && ./run.sh --dry-run'
```

再执行 bundle 自带验收：

```bash
sudo bash deployment/verify_install.sh
```

代理已经由 GUI 或 fallback xray 接管时，验证 HTTP 204：

```bash
docker exec v2rayn-switch-runner \
  curl -x socks5h://127.0.0.1:10808 -o /dev/null -s \
  -w 'http=%{http_code} total=%{time_total}\\n' \
  --max-time 10 https://www.google.com/generate_204
```

预期：HTTP `204`。同时确认：

```bash
docker exec -u 0 v2rayn-switch-runner \
  python3 /home/mac/.hermes/scripts/v2rayn_owner.py 10808
```

## 7. 部署调度

优先使用 Hermes cron，按照 `CRON-JOBS.md` 新建两个任务：

- 每天北京时间 08:29 的正式更新任务；
- 每 2 分钟的时段代理守护。

job ID 是本机调度器生成的，不能从备份硬编码复用。新建后必须检查脚本路径、`no_agent=true`、时区和下一次运行时间。

如果改用系统 cron，必须先暂停/删除对应 Hermes cron，不能双重运行。系统 cron 示例见 `docs/CRON-JOBS.md`。

## 8. 日常排障

```bash
# 看守护状态
cat /home/mac/.hermes/state/v2rayn_mode_guard.json

# 看时段守护日志
tail -80 /home/mac/v2rayN-linux-64/autoswitch/logs/mode-guard.log

# 看正式任务日志
tail -80 /home/mac/v2rayN-linux-64/autoswitch/logs/auto-$(date +%Y%m%d).log

# 看 fallback xray 错误
 tail -80 /home/mac/.hermes/logs/v2rayn_fallback_xray.log
```

遇到 10808 问题，先查持有者再动作。不要使用 `pkill -f`，避免匹配到当前 shell 或误杀 GUI 核心；只允许精确识别 root fallback xray 后再处理。
