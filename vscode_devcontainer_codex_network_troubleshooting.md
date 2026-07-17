# VS Code Dev Container 与 Codex 排查记录

日期：2026-07-17

## 1. 初始问题

VS Code 通过 Dev Containers 连接容器 `/apollo_neo_dev_10.0.0_pkg` 失败，日志核心错误为：

```text
/usr/share/code/code: bad option: --ms-enable-electron-run-as-node
Exit code 9
```

环境信息：

- VS Code：1.98.2
- Dev Containers：0.288.1
- Docker Server API：1.55
- 容器：`/apollo_neo_dev_10.0.0_pkg`

Docker 本身正常，失败发生在 Dev Containers CLI 启动之前，不是容器认证或 Docker 网络问题。

## 2. Dev Containers 修复

原因是旧版 Dev Containers 扩展向 VS Code 1.98.2 的 Electron 进程传入了当前启动器不接受的参数。

对本机扩展文件进行了兼容性修补：

```text
/home/mac/.vscode/extensions/ms-vscode-remote.remote-containers-0.288.1/dist/extension/extension.js
```

修补内容：

- 删除 `--ms-enable-electron-run-as-node` 参数；
- 使用 `ELECTRON_RUN_AS_NODE=1` 启动 CLI。

原文件备份为：

```text
/home/mac/.vscode/extensions/ms-vscode-remote.remote-containers-0.288.1/dist/extension/extension.js.before-electron-node-fix
```

修补后，Dev Containers CLI 的直接测试可以正常返回版本 `0.35.0`。

如果将来重新安装或更新 Dev Containers 扩展，此修补可能被覆盖。

## 3. 容器网络与代理

宿主机当前代理为 Xray：

```text
HTTP_PROXY=http://127.0.0.1:10808
HTTPS_PROXY=http://127.0.0.1:10808
ALL_PROXY=socks://127.0.0.1:10808/
```

宿主机监听：

```text
127.0.0.1:10808/tcp  xray
127.0.0.1:10808/udp  xray
```

容器使用 `network_mode: host`，因此容器内的 `127.0.0.1` 就是宿主机，不需要使用 `host.docker.internal`。

容器内通过代理测试结果：

- `chatgpt.com`：可以建立代理连接；
- `api.openai.com`：可以建立代理连接，访问未认证接口时返回 `401`；
- 代理出口国家查询结果：`US`。

VS Code Server 的启动参数包含：

```text
--use-host-proxy
```

Codex 进程也继承了代理环境变量，因此代理变量已经传递到 Codex 进程。

建议的代理变量格式：

```bash
HTTP_PROXY=http://127.0.0.1:10808
HTTPS_PROXY=http://127.0.0.1:10808
ALL_PROXY=socks5h://127.0.0.1:10808
NO_PROXY=localhost,127.0.0.0/8,::1
```

## 4. 容器用户与 Codex 配置目录

宿主机用户是 `mac`，但当前容器内 VS Code Server 和 Codex 以 `root` 用户运行。

因此正确的 Codex 配置目录是：

```text
/root/.codex
```

不是容器内的 `/home/mac/.codex`，也不是宿主机的 `/home/mac/.codex`。

Codex 扩展启动日志最初报错：

```text
CODEX_HOME points to "/root/.codex", but that path does not exist
```

已经在容器内创建并设置权限：

```text
/root/.codex
权限：700
所有者：root:root
```

Codex 自带二进制可以正常运行，版本为：

```text
codex-cli 0.144.5
```

## 5. Codex 扩展信息

容器内安装的扩展：

```text
/root/.vscode-server/extensions/openai.chatgpt-26.707.91948
```

扩展声明的 VS Code 引擎版本为：

```text
^1.96.2
```

当前 VS Code 1.98.2 理论上满足该版本范围。

日志中还出现：

```text
registerChatSessionItemProvider is not a function
```

这表示当前 VS Code API 较旧，Codex 的部分聊天会话集成功能不可用，但最初导致 Codex 进程退出的直接原因是 `/root/.codex` 缺失。

## 6. 当前登录错误

创建 `/root/.codex` 后，Codex 登录出现：

```text
Token exchange failed: token endpoint returned status 403 Forbidden:
Country, region, or territory not supported

Error code: token_exchange_failed
```

这说明请求已经到达 OpenAI 登录服务，但 token 交换阶段被地区/出口策略拒绝，不是普通的 DNS、HTTP 代理或容器权限错误。

虽然代理出口检测为美国，但 OpenAI 仍可能根据以下因素拒绝：

- 代理 IP 属于数据中心或共享 VPN 出口；
- 出口 IP 的信誉或地区识别不符合要求；
- 浏览器登录地区、账号地区和容器出口不一致；
- 账号或工作区本身不在支持范围内。

OpenAI 官方说明：不支持地区访问 ChatGPT 或 API 可能导致账号受到限制。

- https://help.openai.com/en/articles/5347006
- https://help.openai.com/en/articles/9131992-chatgpt-and-api-services-in-unsupported-countries-and-territories

## 7. VS Code 容器内打开其他根目录

在已连接容器的 VS Code 窗口中，可以使用：

```text
Ctrl+K Ctrl+O
```

然后输入容器内路径，例如：

```text
/
/apollo
/apollo_workspace
/opt
/root
```

当前项目代码通常位于：

```text
/apollo_workspace
```

注意：这里必须使用容器内路径，不是宿主机的 `/home/mac/...` 路径。

## 8. 当前结论与建议

目前已经解决或确认：

- Docker 正常；
- Dev Containers 启动参数问题已修补；
- 容器已成功登录；
- 容器网络可用；
- 宿主机代理已传递给 VS Code Server 和 Codex 进程；
- `/root/.codex` 缺失问题已修复。

当前剩余问题是 OpenAI token exchange 的地区策略拒绝。建议使用符合 OpenAI 支持范围且未被识别为受限/共享 VPN 的网络出口重新登录；如果确认账号和网络地区均受支持，应携带 `token_exchange_failed` 错误码联系 OpenAI 支持。
