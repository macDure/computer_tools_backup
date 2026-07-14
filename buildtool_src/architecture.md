# Apollo Buildtool 代码架构与功能说明

`buildtool` 是 Apollo 系统中用于构建、管理依赖、管理系统包的核心工具。它的设计围绕包管理、环境检查、以及底层构建系统的封装（Bazel/CMake）展开。

以下是对 `buildtool` 代码架构及各核心模块的功能梳理。

## 1. 目录结构概览

`buildtool` 的主要代码分为以下几个关键目录：

```text
buildtool_src/
├── bin/          # 程序的统一入口点
├── core/         # 核心代码逻辑库（最核心目录）
│   ├── action/   # 子命令的具体实现（如 build, install, clean等）
│   ├── task/     # 底层构建工具链交互（如 bazel, cmake 等）
│   ├── version_decide/ # 版本依赖解析、网络元数据同步与 cyberfile 解析
│   └── package_identification/ # 包识别与描述封装
├── scripts/      # 辅助脚本
├── cmake/        # CMake 相关的模板与工具链配置
└── bazel/        # Bazel 相关的模板与工具链配置
```

## 2. 核心架构与请求流转

`buildtool` 采用了经典的**命令行解析 -> 前置检查 -> 动作派发 -> 依赖解析 -> 任务执行**的设计模式。

### 2.1 统一入口与前置检查 (`bin/mainboard.py`)
`mainboard.py` 是整个工具的骨架：
- **命令行解析**：利用 `argparse` 接管所有的子命令参数。
- **环境前置检查**：
  - `check_in_docker_env()`: 确保只能在 Apollo 容器内运行。
  - `check_gpu_existence() / check_esdcan_use()`: 自动侦测硬件资源（NVIDIA GPU / ESD CAN 卡）。
  - `check_architecture_support() / check_platfrom_support()`: 限制 Linux/x86_64 或 aarch64 环境。
  - `check_minimal_memory_requirement()`: 检查至少 2GB 内存以防 OOM。
- **配置写入**：`generate_env_config()` 将必需的 `setup.sh` 写入到当前容器用户的 `~/.bashrc` 中。
- **分发执行**：通过 `EntryPoints` 将具体的命令（如 `build`、`clean`）路由给 `core/action/` 下对应的 Python 脚本。

### 2.2 子命令实现逻辑 (`core/action/`)
这里存放了终端中你输入 `buildtool xxx` 时对应的工作流逻辑：
- `build.py` / `test.py`: 核心编译与测试指令，会触发 Bazel 构建过程。
- `install.py` / `reinstall.py` / `upgrade.py`: 包管理相关指令，通过拉取远端 `apollo.baidu.com` 的数据来进行软件包更新或重新安装。
- `create.py` / `init.py`: 用于初始化新的 Apollo 包结构（生成 `cyberfile.xml` 与 `BUILD` 模板等）。

### 2.3 依赖与版本解析 (`core/version_decide/` & `core/topological_order.py`)
- **`cyberfile` 解析**：`version_decide/cyberfile/__init__.py` 负责从服务器（通过 HTTP 请求）下载包的元数据（依赖网络！），并解析本地包内的 `cyberfile.xml` 以检查缺少的依赖。
- **拓扑排序**：`topological_order.py` 负责构建组件依赖关系图（DAG），确保底层库被优先编译。

### 2.4 底层构建工具适配 (`core/task/`)
该目录主要作为**适配层**，负责将上层的动作转换为下层工具的指令：
- **`bazel` 目录**：
  - `handler/`: 包含了非常多底层的处理逻辑。比如 `preprocess.py` 会在编译前处理依赖检查（如果在这一步检测到网络断开，会报 NetworkIoError）。
  - 会动态修改 `WORKSPACE` 文件，生成动态的 bazel targets 并通过 subprocess 调用 `bazel build`。

## 3. 功能执行链路示例（以 `buildtool build` 为例）

1. **发起命令**：你在终端执行 `buildtool build -p ./modules/canbus/`
2. **环境校验**：`mainboard.py` 启动，检测到是在 Docker 内，检测到系统内存与 GPU 状态。
3. **元数据更新**：进入 `cyberfile/__init__.py`，向远程请求最新的软件包版本信息（这也就是为什么断网或者不配置代理会卡住的原因，可通过我们加入的 `APOLLO_SKIP_UPDATE=1` 旁路掉）。
4. **解析依赖**：读取 `./modules/canbus/cyberfile.xml`，通过 `topological_order.py` 生成依赖树，如果有缺少的第三方库则触发 `apt` 或自行下载。
5. **动态生成**：`core/task/bazel/handler/` 根据当前分析结果，在后台修改 Bazel 的依赖路径、`WORKSPACE` 和临时构建文件。
6. **最终编译**：组装完整的 `bazel build //modules/canbus/...` 命令交由系统后台执行，输出编译进度条。

## 4. 总结
`buildtool` 不是一个纯粹的编译工具（如 CMake/Make），而是一个**基于 Bazel，并整合了环境检查、云端包管理与代码生成的 Apollo 容器内中控系统**。
