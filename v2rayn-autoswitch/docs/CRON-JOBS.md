# 调度定义与恢复方法

## 当前生产调度

以下是当前机器已验证的两条核心任务。Hermes cron 的 job ID 在每台机器上不同，恢复时按名称/脚本重新创建，不复制 ID。

| 任务 | 北京时间 | Hermes schedule（UTC） | 脚本 | no_agent |
|---|---:|---:|---|---|
| v2rayN-autoswitch-每日08:29 | 每日 08:29 | `29 0 * * *` | `v2rayn_autoswitch.sh` | `true` |
| v2rayN-时段代理守护 | 每 2 分钟 | `*/2 * * * *` | `v2rayn_mode_guard.sh` | `true` |

当前实测的生产 job：

- 正式任务：`7fb119005b5b`，脚本 `v2rayn_autoswitch.sh`；
- 守护任务：`bf5966089aa9`，脚本 `v2rayn_mode_guard.sh`。

这些 ID 只用于核对当前机器，不要在其他机器手动指定。

## Hermes cron 创建内容

使用 Hermes 的 cron UI、`/cron` 命令或 cron 工具创建：

### 1. 正式更新

- 名称：`v2rayN-autoswitch-每日08:29`
- schedule：`29 0 * * *`
- script：`v2rayn_autoswitch.sh`
- no_agent：`true`
- deliver：按目标机通知会话设置
- 成功静默，异常由 wrapper 输出告警

### 2. 时段守护

- 名称：`v2rayN-时段代理守护(每2分钟/08:29保护)`
- schedule：`*/2 * * * *`
- script：`v2rayn_mode_guard.sh`
- no_agent：`true`
- deliver：按目标机通知会话设置
- 成功静默，异常由 wrapper 输出告警

守护代码自身在北京时间 08:28—08:33 保护窗口内跳过，让 08:29 正式任务独占 `autoswitch.lock`。

## 可选任务

`v2rayn_sub_refresh_cron.sh` 是独立的每 30 分钟订阅刷新入口，当前生产核心调度不依赖它。若启用，必须确认它与正式任务、时段守护共享锁，并观察日志后再长期运行。

`v2rayn_proxy_guard.sh` 是较早的 GUI/端口状态机脚本。当前核心守护已由 `v2rayn_mode_guard.sh` 统一承担，不能把两者同时作为独立 cron 启用。

`v2rayn_c1s2_guard.sh` 已属于 legacy，当前不应启用。

## 系统 cron 替代方案

只有在 Hermes cron 不可用时才使用；启用前先停掉对应 Hermes 任务。以下示例要求脚本运行环境能看到 `/opt/data/scripts`：

```cron
CRON_TZ=Asia/Shanghai
29 8 * * * /opt/data/scripts/v2rayn_autoswitch.sh
*/2 * * * * /opt/data/scripts/v2rayn_mode_guard.sh
```

不要额外添加 04:00 的 c1s3 任务。04:00 行为由每 2 分钟时段守护中的夜间规则处理。
