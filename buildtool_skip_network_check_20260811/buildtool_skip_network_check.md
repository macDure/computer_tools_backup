# buildtool 跳过网络检查修改记录

## 背景

在容器 `apollo_neo_dev_10.0.0_pkg` 内执行：

```bash
ASKP=1 buildtool build --opt --gpu -p modules/planning/ -j12
```

原始报错为：

```text
ERROR Encounter ErrCode.NetworkIoError
ERROR hint: Network error: please checkout your network condition
```

原因是 buildtool 的 `ASKP=1` 只跳过“下载最新 package index”，但不会跳过 buildtool 自身的在线状态探测。构建前 `Procedure._check_network()` 会访问：

```text
http://pkg.mkzy.com/packages/api/login
```

如果该探测失败，`self.online` 会被置为 `False`。随后只要 buildtool 判断某个依赖包需要安装或重装，就会因为 `procedure.get_network_status()` 为 `False` 而直接抛出 `ErrCode.NetworkIoError`。

## 修改目标

让 `ASKP=1` 同时跳过 buildtool 的网络可用性检查，使其继续使用本地离线索引和本地已安装依赖进行构建。

该修改只影响带 `ASKP=1` 的构建命令；不带 `ASKP=1` 时仍保持原始联网检查逻辑。

## 修改文件

容器内文件：

```text
/opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py
```

备份文件：

```text
/opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py.bak_skip_network_20260811
```

## 修改内容

原逻辑：

```python
def _check_network(self):
    login_api = get_config("api", "login")
    cmd = ["curl", "--max-time", "5", login_api, ">/dev/null 2>&1"]
    if subprocess.call(" ".join(cmd), shell=True) != 0:
        logger.warning("Can't connect with the server, use offline mode")
        self.online = False
```

修改后：

```python
def _check_network(self):
    if os.environ.get("ASKP") == "1":
        logger.warning("ASKP=1 is set: skip buildtool network availability check")
        return
    login_api = get_config("api", "login")
    cmd = ["curl", "--max-time", "5", login_api, ">/dev/null 2>&1"]
    if subprocess.call(" ".join(cmd), shell=True) != 0:
        logger.warning("Can't connect with the server, use offline mode")
        self.online = False
```

核心变化是在 `_check_network()` 开头增加：

```python
if os.environ.get("ASKP") == "1":
    logger.warning("ASKP=1 is set: skip buildtool network availability check")
    return
```

## 实际执行的修改方法

在容器中执行了以下步骤：

```bash
f=/opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py
b=${f}.bak_skip_network_20260811
[ -f "$b" ] || cp "$f" "$b"

perl -0pi -e 's/    def _check_network\(self\):\n        login_api = get_config\("api", "login"\)/    def _check_network(self):\n        if os.environ.get("ASKP") == "1":\n            logger.warning("ASKP=1 is set: skip buildtool network availability check")\n            return\n        login_api = get_config("api", "login")/' "$f"

python3 -m py_compile "$f"
```

说明：

- 先将原文件备份为 `.bak_skip_network_20260811`。
- 使用 `perl -0pi` 在 `_check_network()` 开头插入 `ASKP=1` 判断。
- 用 `python3 -m py_compile` 做语法检查。

## 验证结果

再次执行：

```bash
ASKP=1 buildtool build --opt --gpu -p modules/planning/ -j12
```

日志出现：

```text
WARNING ASKP=1 is set: skip buildtool network availability check
INFO APOLLO_SKIP_UPDATE is set: skip downloading the latest package index...
```

随后构建越过原先的 `ErrCode.NetworkIoError`，进入 Bazel 编译阶段，并继续编译到 Apollo planning 相关源码和 CUDA 文件。

## 回滚方法

如果需要恢复原始 buildtool 行为：

```bash
cp /opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py.bak_skip_network_20260811 \
   /opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py

python3 -m py_compile /opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py
```

## 注意事项

- 该修改不会补齐缺失依赖，只是跳过网络可用性检查。
- 如果本地离线索引或依赖包确实不完整，构建后续仍可能在安装包、链接或编译阶段失败。
- 建议只在确认本地依赖完整、且当前问题仅为 `pkg.mkzy.com` DNS/代理/网络探测失败时使用。

## 使用备份文件快速替换容器内 buildtool 文件

本目录已经保存了修改后的 buildtool 文件：

```text
/home/mac/macperson/computer_tools_backup/buildtool_skip_network_check_20260811/__init__.py
```

容器内目标文件路径：

```text
/opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py
```

以后如果重新创建容器或 buildtool 文件被恢复，可以在宿主机执行以下命令，直接把备份文件复制进容器并替换：

```bash
backup_dir=/home/mac/macperson/computer_tools_backup/buildtool_skip_network_check_20260811
container=apollo_neo_dev_10.0.0_pkg
target=/opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py

# 1. 先备份容器内当前文件，避免覆盖后无法回退
docker exec "$container" bash -lc "cp '$target' '${target}.bak_before_skip_network_replace_$(date +%Y%m%d_%H%M%S)'"

# 2. 复制修改后的文件到容器临时目录
docker cp "$backup_dir/__init__.py" "$container:/tmp/buildtool_handler_init.py"

# 3. 替换目标文件，并做语法检查
docker exec "$container" bash -lc "cp /tmp/buildtool_handler_init.py '$target' && python3 -m py_compile '$target'"

# 4. 确认修改已生效
docker exec "$container" bash -lc "grep -n -A8 'def _check_network' '$target'"
```

替换完成后，执行构建：

```bash
docker exec --user mac -it apollo_neo_dev_10.0.0_pkg bash
cd /apollo_workspace
ASKP=1 buildtool build --opt --gpu -p modules/planning/ -j12
```

如果日志中出现以下内容，说明跳过网络检查逻辑已经生效：

```text
ASKP=1 is set: skip buildtool network availability check
APOLLO_SKIP_UPDATE is set: skip downloading the latest package index...
```

## 使用备份文件回退到替换前版本

如果你按上面的命令替换前做了自动备份，可以在容器里查找备份文件：

```bash
docker exec apollo_neo_dev_10.0.0_pkg bash -lc "ls -lt /opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py.bak_before_skip_network_replace_* | head"
```

选择其中一个备份文件后恢复，例如：

```bash
docker exec apollo_neo_dev_10.0.0_pkg bash -lc "cp /opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py.bak_before_skip_network_replace_YYYYMMDD_HHMMSS /opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py && python3 -m py_compile /opt/apollo/neo/packages/buildtool/10.0.0-rc1-r1/core/task/bazel/handler/__init__.py"
```
