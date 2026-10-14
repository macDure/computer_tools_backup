# Antigravity CLI (`agy`) 自动确认与权限管理指南

在日常开发与自动化运维中，Antigravity CLI (`agy`) 默认会在调用敏感工具（如执行 Shell 命令、修改文件等）时弹出权限确认提示。

若希望自动化运行任务或减少频繁的手动回车确认，可以使用 **`--dangerously-skip-permissions`** 参数全局跳过工具交互权限提示。

---

## 一、交互模式下自动确认

直接启动交互会话或附带初始任务：

```bash
# 直接进入交互界面并全局跳过权限确认
agy --dangerously-skip-permissions

# 附带初始任务并进入交互会话
agy -i "你的任务内容" --dangerously-skip-permissions
```

---

## 二、非交互式命令行执行（单次运行）

使用 `-p` 或 `--print` 执行单次任务并自动批准所有操作，适合脚本调用或后台自动化：

```bash
agy -p "请重构当前目录下的 CMakeLists.txt 并运行测试" --dangerously-skip-permissions
```

---

## 三、配置 Shell 别名（避免每次输入长参数）

可将该参数绑定为别名写入 Shell 配置文件（如 `~/.bashrc`）：

```bash
echo 'alias agy-auto="agy --dangerously-skip-permissions"' >> ~/.bashrc
source ~/.bashrc
```

后续直接执行即可默认处于免确认状态：

```bash
# 交互模式
agy-auto

# 命令行单次执行
agy-auto -p "任务内容"
```

---

## 四、核心参数补充说明

| 参数 | 说明 | 适用场景 |
| :--- | :--- | :--- |
| **`--dangerously-skip-permissions`** | 完全放行所有工具权限（包含直接执行终端 Shell 命令、读写与删除文件等）。 | 任务明确、全自动化执行场景。 |
| **`--mode accept-edits`** | 仅在代码编辑时自动接受文件修改，其余工具调用仍保留确认。 | 代码重构、大范围改写代码。 |
| **`--sandbox`** | 开启终端沙箱限制，禁止可能导致宿主机受损的高危破坏性命令。 | 需要自动执行但希望保护宿主机系统的场景。 |

### 推荐组合用法：

1. **自动代码编辑 + 交互确认命令**：
   ```bash
   agy --mode accept-edits
   ```

2. **全自动无感运行（自动修改代码并免确认执行命令）**：
   ```bash
   agy --mode accept-edits --dangerously-skip-permissions
   ```

3. **安全沙箱 + 免权限确认**：
   ```bash
   agy --sandbox --dangerously-skip-permissions
   ```
