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
