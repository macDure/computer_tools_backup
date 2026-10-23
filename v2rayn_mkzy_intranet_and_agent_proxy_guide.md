# v2rayN 科学上网、内网 mkzy 直连与大模型 Agent 代理保障指南

本文档完整记录在 Ubuntu/Linux 环境下配置 **v2rayN 科学上网代理**、**公司内网 `mkzy.com` 全局直连（终端与网页）**、**本地私有 DNS 域名解析** 以及 **Apollo Sim Scope 仿真认证弹窗** 的全套方案。

**目的**：换新电脑或系统重装后，依照本文档能一站式完成所有网络与代理配置，快速恢复工作环境。

---

> [!CAUTION]
> ## 🚨 最高禁令：严禁关闭或杀死 v2rayN / xray 代理内核！
>
> 1. **核心原因**：本机的外部网络、所有大模型开发工具（Codex、Antigravity CLI / agy、VSCode AI 扩展等）均强依赖本地 `127.0.0.1:10808` 代理进行网络通信。
> 2. **严重后果**：一旦通过 `kill` 或直接关闭代理内核，所有大模型 Agent 将瞬间断网失联死锁，无法自愈，必须依赖其他电脑人工介入才能排查恢复。
> 3. **铁律规范**：
>    - **任何维护、网络排查、脚本自动化均绝对禁止强杀或停止 v2rayN / xray 进程**；
>    - 如需调整配置或切换节点，必须通过 v2rayN 图形界面保存，或使用受控的热重载/API 机制，绝不能随意终止内核。

---

## 一、 整体网络拓扑与背景说明

| 目标分类 | 地址范围 / 域名 | 访问要求 | 负责服务 |
| :--- | :--- | :--- | :--- |
| **外网 / 大模型** | Google, GitHub, LLM API 等 | **必须走代理**（127.0.0.1:10808） | v2rayN + Xray 境外 VPS 节点 |
| **公司内网服务** | `*.mkzy.com`、`172.20.0.0/16`、`192.168.0.0/16` | **必须直连，严禁走代理** | 本机直连 / 内网物理网卡 |
| **内网私有 DNS** | `172.20.149.216` | 解析 `*.mkzy.com` 内网域名 | 私有 DNS 服务 |
| **Apollo 仿真回放** | `http://172.20.149.215:30410/` | 内网直接访问 | tiny-http + Rerun SDK (Wasm) |
| **统一身份认证 (SSO)** | `http://sso.mkzy.com/welcome` | 内网直接访问 + 弹窗扫码 | 飞书扫码认证网关（位于 172.20.149.216） |

---

## 二、 新电脑一键部署与配置全流程

在新电脑上克隆或恢复本备份目录（`/home/mac/macperson/computer_tools_backup`）后，按顺序执行以下 5 个步骤：

### 步骤 1：配置内网域名解析（`/etc/hosts`）

**背景根因**：
路由器公网 DNS（如 `192.168.3.1`）无法解析公司内部域名 `mkzy.com`。仿真服务在加载时会请求 `/api/platform/config` 获得认证服务地址 `http://sso.mkzy.com` 和平台地址 `http://platform.mkzy.com`。如果缺少解析，浏览器会直接报 `ERR_NAME_NOT_RESOLVED` 导致页面打不开。

在新电脑终端中执行以下命令，向 `/etc/hosts` 补齐内网域名：

```bash
sudo tee -a /etc/hosts << 'EOF'

# mkzy.com 内网服务解析（指向内部私有服务 172.20.149.216）
172.20.149.216 gitlab.mkzy.com
172.20.149.216 pkg.mkzy.com
172.20.149.216 minio-api.mkzy.com
172.20.149.216 apt.mkzy.com
172.20.149.216 sso.mkzy.com
172.20.149.216 platform.mkzy.com
EOF
```

---

### 步骤 2：配置 v2rayN 系统代理例外（关键避坑）

> [!WARNING]
> **致命陷阱**：在 Linux 下，v2rayN 会调用 `gsettings set org.gnome.system.proxy ignore-hosts` 写入桌面代理例外。
> 如果在输入框中**逗号后面留了空格**（例如 `localhost, *.mkzy.com`），GLib/Chrome 会按带空格的字面量 `' *.mkzy.com'` 进行匹配，导致整个例外规则**彻底失效**！内网请求会被全部送进代理内核，而境外 VPS 无法连接内网，导致内网服务完全挂死。

#### 配置步骤：
1. 打开 v2rayN 主界面；
2. 菜单栏点击：**设置** $\rightarrow$ **参数设置**；
3. 切换到 **系统代理设置** 标签页；
4. 找到 **系统代理例外** 输入框，复制填入以下完整规则（**注意：逗号后面严禁加任何空格！**）：
   ```text
   localhost,127.0.0.0/8,::1,*.mkzy.com,mkzy.com,.mkzy.com,172.20.0.0/16,172.20.149.0/24,172.20.149.215,172.20.149.216,192.168.0.0/16
   ```
5. 点击 **确定** 保存。

#### 路由规则兜底（可选但推荐）：
在 v2rayN 路由设置中（或编辑 `guiConfigs/config.json`）：
- 在 `outboundTag: "direct"` 的规则中加入 `"domain:mkzy.com"` 与 `"172.20.0.0/16"`；
- 确保即使某个软件强行将流量打到 10808 端口，xray 内核也会将其判定为直连（Freedom），绝不送往境外代理。

---

### 步骤 3：验证与修复 GNOME 桌面 / Chrome 浏览器直连

如果在命令行或无需打开 v2rayN GUI 时，可直接通过 `gsettings` 设置并验证桌面代理例外：

```bash
# 1. 写入无空格的正确格式
gsettings set org.gnome.system.proxy ignore-hosts "['localhost', '127.0.0.0/8', '::1', '*.mkzy.com', '172.20.*', '172.20.149.215', '172.20.149.216']"

# 2. Python 验证系统底层网络分流
python3 -c "
import gi; gi.require_version('Gio', '2.0'); from gi.repository import Gio
resolver = Gio.ProxyResolver.get_default()
print('sso.mkzy.com      ->', resolver.lookup('http://sso.mkzy.com/'))
print('172.20.149.215    ->', resolver.lookup('http://172.20.149.215:30410/'))
print('google.com        ->', resolver.lookup('http://google.com/'))
"
```
**期望输出**：
- `sso.mkzy.com` 和 `172.20.149.215` 输出 `['direct://']`（直连成功）；
- `google.com` 输出 `['http://127.0.0.1:10808']`（代理正常生效）。

---

### 步骤 4：配置本地终端代理脚本（`proxy_env.sh`）

终端环境（Bash/Zsh）通过环境变量 `http_proxy`、`https_proxy` 和 `no_proxy` 控制网络分流。

1. 确认已在 `~/.bashrc` 和 `~/.zshrc` 中引入了备份仓库的工具脚本：
   ```bash
   # 添加到 ~/.zshrc 或 ~/.bashrc
   if [ -r "$HOME/macperson/computer_tools_backup/v2raya-tproxy-kit/scripts/proxy_env.sh" ]; then
       . "$HOME/macperson/computer_tools_backup/v2raya-tproxy-kit/scripts/proxy_env.sh"
   fi
   ```
2. 确认 `proxy_env.sh` 中的 `proxy_env_v2rayn` 和 `proxy_env_auto` 包含内网绕过：
   ```bash
   export no_proxy='localhost,127.0.0.0/8,::1,mkzy.com,.mkzy.com,172.20.0.0/16,192.168.0.0/16'
   export NO_PROXY="$no_proxy"
   ```
3. 终端快捷命令速查：
   - `proxy-v2rayn`：一键开启终端代理（自动注入内网直连白名单）；
   - `proxy-off`：清除终端代理变量；
   - `proxy-show`：查看当前终端的代理状态。

---

### 步骤 5：Apollo Sim Scope 仿真回放与飞书 SSO 弹窗设置

访问仿真地址示例：
```text
http://172.20.149.215:30410/?record=%2Fapollo_workspace%2Fdata%2Fsimulation%2Fregression%2Ffr-max-pa-afternoon-20261023%2Fjobs%2Fcef3744dd0c84193%2Frun-1%2Fsimulation.record&layout=planning
```

#### 登录流程与弹窗解决：
1. 页面加载完成后，WebAssembly 会异步触发 `apolloSceneAccount.openProfile("http://sso.mkzy.com")`，通过 `window.open` 弹出飞书登录窗口；
2. **处理 Chrome 弹窗拦截**：
   由于弹窗是 Wasm 异步代码发起的，现代浏览器（Chrome/Edge）会默认作为“未经用户手势的弹出窗口”进行静默拦截。
   - 检查 Chrome 地址栏最右侧，会看到一个带红色小叉的窗口图标；
   - 点击该图标，选择 **“始终允许来自 http://172.20.149.215:30410 的弹出式窗口和重定向”**；
   - 点击 **完成** 并刷新页面；
3. 此时会自动弹出独立的飞书扫码认证窗口（`http://sso.mkzy.com/welcome`）；
4. 用手机飞书扫码并点击确认登录，认证成功后窗口自动关闭，仿真回放画面即刻正常呈现。

---

## 三、 快速排错手册（Troubleshooting）

| 异常现象 | 根因排查 | 解决方案 |
| :--- | :--- | :--- |
| **所有大模型 Agent (codex/agy) 突然全挂、报连接超时** | **最严重**：v2rayN 代理内核被杀死，或 10808 端口未监听 | 严禁杀进程！立即检查 v2rayN 界面，确认内核正在运行（或在终端运行 `./v2rayN` 启动），确认 `127.0.0.1:10808` 正常监听。 |
| **仿真页面打不开 / 报 `ERR_NAME_NOT_RESOLVED`** | `/etc/hosts` 缺少 `sso.mkzy.com` 解析 | 检查 `/etc/hosts`，补充 `172.20.149.216 sso.mkzy.com`。 |
| **仿真页面加载极慢后报 502 / 超时** | 页面请求误走了代理，送往了境外 VPS | 检查 v2rayN 参数设置中的“系统代理例外”，去除所有空格，必须包含 `172.20.*` 和 `*.mkzy.com`。 |
| **页面正常显示，但没有任何登录弹窗** | Chrome 拦截了弹出窗口 | 查看 Chrome 地址栏右侧是否有拦截图标，勾选“始终允许弹窗”并刷新。 |
| **终端中 `curl` 内网服务连不上** | 终端环境的 `no_proxy` 未生效 | 执行 `proxy-v2rayn` 刷新环境变量，或 `echo $no_proxy` 检查是否包含 `mkzy.com`。 |
