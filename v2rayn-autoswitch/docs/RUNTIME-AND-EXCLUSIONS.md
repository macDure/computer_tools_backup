# 运行时状态与备份边界

## 纳入 bundle 的内容

- `autoswitch.py`、`run.sh`、`config.conf` 模板、`DESIGN.md`（订阅 URL 已脱敏）；
- 正式 08:29 wrapper；
- 每 2 分钟时段守护及测试；
- GUI 温柔模式补丁、parse_ss 兼容补丁、cn-route 自愈、owner 识别；
- 订阅刷新/通知脚本；
- runner 建立脚本、部署脚本、验收脚本；
- 旧版诊断工具，单独放在 `legacy/`。

## 明确排除的内容

| 路径/类型 | 原因 | 恢复方式 |
|---|---|---|
| `guiConfigs/guiNDB.db` | 包含订阅节点和密码 | 目标机 GUI 重新添加/更新订阅 |
| `guiConfigs/guiNConfig.json` | 当前机器 GUI 状态 | 目标机 GUI 重新生成 |
| `guiConfigs/config.json` | fallback xray 当前节点配置，可能含密码 | 由脚本按目标节点重新生成 |
| `.env` | Feishu 应用密钥 | 目标机单独配置 |
| `autoswitch/tmp/` | 临时 probe、订阅原文、数据库副本 | 不需要恢复 |
| `autoswitch/logs/` | 当前机运行日志 | 目标机重新生成 |
| `autoswitch/state/`、`.hermes/state/` | 当前机状态去重信息 | 目标机首次运行自动生成 |
| `__pycache__/`、`.lock` | 运行时产物 | 自动生成 |

## 当前机器验证快照（仅作参考）

2026-09-16 北京时间约 09:16 的真实恢复验证：经 `c1s3` 更新订阅，写库 6 个节点；复检 `c1s1`、`c1s2` 均通过，约 742/820 ms，切回较低延迟的 `c1s1`，10808 返回 HTTP 204。

这不是目标机的预置状态，不能把其中的节点 IP、IndexId 或数据库复制过去。
