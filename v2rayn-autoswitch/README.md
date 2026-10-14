# v2rayN AutoSwitch 可移植备份

这是当前机器上 **v2rayN 自动切节点、订阅更新、日间故障恢复、10808 兜底守护** 的源码与部署资料备份。

## 目标

在另一台与当前相同的 Linux + Docker + Hermes + v2rayN 环境中，按 `DEPLOYMENT.md` 完成部署后，恢复以下能力：

- 北京时间 08:29 自动探测节点、更新订阅并选择节点；
- 04:00—08:28 夜间保持 `c1s3`；
- 08:29—次日 04:00 优先 `c1s1/c1s2`；
- 日间故障先尝试 `c1s1/c1s2`，两者都超时才切 `c1s3`；
- 切到日间 `c1s3` 后立即更新订阅并复检 `c1s1/c1s2`，最多 3 轮；恢复后切回延迟较小者；
- runner、fallback xray、10808 端口持有者识别、GUI 温柔模式和国内/内网直连路由自愈。

## 快速入口

1. 先读 `DEPLOYMENT.md`，确认目标机路径和前置条件。
2. 执行 `deployment/deploy.sh` 安装源码。
3. 执行 `deployment/bootstrap_runner.sh` 建立或启动 Docker runner。
4. 按文档在 v2rayN GUI 中配置订阅，再执行 dry-run 和验收命令。
5. 只启用一套调度方式：Hermes cron 或系统 cron，不能两套同时启用。

## 目录

- `current/autoswitch/`：主工具 `autoswitch.py`、`run.sh`、配置模板和设计文档；
- `current/scripts/`：当前生产使用的 wrapper、时段守护、订阅刷新、补丁和测试脚本；
- `current/scripts/shuimu_daily/`：告警用 `deliver_feishu.py`；
- `legacy/`：旧版 c1s2 守护、手工切换和单节点诊断工具，仅供排障参考，不要与当前守护并行启用；
- `deployment/`：部署 runner、安装文件和验收脚本；
- `docs/`：调度、路径、敏感配置和运行状态说明；
- `checksums.sha256`：本 bundle 文件校验清单。

## 敏感信息边界

本备份**不包含**以下当前机器状态：

- `guiConfigs/guiNDB.db`；
- `guiConfigs/guiNConfig.json`、`guiConfigs/config.json`；
- `.env`、订阅 URL、订阅原文、节点密码；
- 日志、运行状态、临时 probe 文件和 `__pycache__`。

这些内容绑定具体电脑或包含凭据，必须在目标机重新配置。订阅应在目标机 v2rayN GUI 中重新添加；Feishu 告警需要在目标机 `.env` 中提供应用凭据，并按 `DEPLOYMENT.md` 修改接收会话 ID。
