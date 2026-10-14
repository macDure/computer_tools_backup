# `/home/mac` 关键备份数据列表

备份时间：2026-09-16<br>
主机：`mac-ThinkPad-T14p-Gen-3`<br>
服务器：`lenovo@172.20.149.215`<br>
备份根目录：

```text
/data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/
```

## 1. 主备份目录

```text
/data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/home/mac/
```

主备份从 `/home/mac/` 同步，保留相对路径、普通文件、目录和符号链接。最终只读核对结果：

```text
约 126G（含附加快照和 Docker 清单）
普通文件：476,541
目录：75,808
符号链接：4,340
特殊文件：5
```

## 2. 纳入备份的数据

除“明确排除”部分外，`/home/mac` 下的以下内容均纳入：

- `macperson/`：代码、文档、研究资料、脚本、Apollo records/maps 等；
- `mkcode/`：源代码、Git 仓库、配置和非日志工作数据；
- `code_backup/` 及其他项目/源码目录；
- `Documents/`、`Downloads/` 和用户创建的普通文件；
- `.ssh/`、`.gnupg/`、`.codex/`、`.hermes/`、`.config/` 等用户配置和历史；
- Docker Compose、容器配置、卷定义相关文件（镜像层不单独导出）；
- 其他未命中排除规则的用户数据。

## 3. 明确排除的数据

以下路径没有进入主备份：

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

理由：这些是可重建缓存、构建产物、日志、依赖或回收站数据；Apollo 的 records/maps 保留，只有 `data/log` 排除。

## 4. 在线一致性补充

本次按确认的方案没有暂停 Docker/其他容器。正在写入的心跳、日志、SQLite WAL 文件可能在同步后继续变化；迁移前建议再运行一次增量 rsync，或只短暂停写入这些数据库的服务。

最后一次只读 rsync dry-run 看到 34 个在线变化项（SQLite WAL/SHM、日志、浏览器状态和心跳等）。主同步返回码为 0；这些差异反映服务继续写入的时间点，不代表传输失败。若需严格时间点一致，请停写相关服务后再做一次增量同步。

对 `.codex/`、`.hermes/` 下 18 个 SQLite 数据库使用 SQLite Online Backup API 生成一致快照，保存于：

```text
/data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/application-consistent/sqlite/
```

其中 `manifest.json` 记录源文件、快照文件和方法；`goals_1.sqlite`、`memories_1.sqlite` 使用 immutable 只读模式（无 WAL sidecar）。

两个由容器 root 创建、普通用户不可读的 Hermes 备份文件通过运行中的 `hermes-gateway` 容器只读导出后保存到主备份：

```text
home/mac/.hermes/.env.bak-feishu-202608261740
home/mac/.hermes/config.yaml.backup-20260826-160553-pre-migrate
```

## 5. Docker 恢复核对资料

不单独保存 Docker 镜像层（系统分区 Clonezilla 会复制 `/var/lib/docker`）。以下只读清单位于：

```text
/data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme/docker/
```

```text
containers.inspect.json   容器完整 inspect（含挂载、环境和启动参数，权限 0600）
images.list.jsonl          镜像/标签/ID 清单
volumes.list.jsonl         Docker 卷名称清单
volumes.inspect.json       Docker 卷 inspect
system.df.txt              Docker 空间占用报告
```

## 6. 权限与完整性边界

服务器使用普通用户 rsync；因为没有可用的无密码 sudo，备份不承诺 root 所有权、特殊 ACL/xattr 的逐字节复原，但文件内容、目录结构和符号链接已核对。备份目录和附加清单为远端用户私有权限（目录 `0700`，敏感清单文件 `0600`）。

迁移前可在服务器执行：

```bash
root=/data/machao_bak/mac-ThinkPad-T14p-Gen-3/20260916-critical-pre-nvme
du -sh "$root"
find "$root/home/mac" -type f | wc -l
find "$root/home/mac" -type l | wc -l
df -h /data
```
