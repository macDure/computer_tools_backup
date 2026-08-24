# Codex 临时使用本地 Qwen 模型

## 目标

保持 Codex 原来的默认配置不变：直接运行 `codex` 时继续使用内置 `openai` provider 和默认 GPT 模型；只有显式添加参数时，才临时使用本地 Qwen 服务。

## 已部署的本地模型

- Base URL：`http://172.20.149.215:8000/v1`
- Model ID：`qwen3.8-27b-fp8`
- 本地 provider：`local_qwen`
- 服务端同时支持 `/v1/chat/completions` 和 `/v1/responses`

Codex 当前自定义 provider 使用 Responses API，因此配置中的协议应写成 `wire_api = "responses"`。参考[官方自定义 provider 配置说明](https://developers.openai.com/codex/config-advanced/#custom-model-providers)。

## 当前配置结构

用户级配置文件：`~/.codex/config.toml`，其中默认配置保持为：

```toml
model = "gpt-5.6-luna"
# 不设置 model_provider，使用内置 openai provider
```

同时保留本地 provider：

```toml
[model_providers.local_qwen]
name = "Local Qwen 3.8 27B FP8"
base_url = "http://172.20.149.215:8000/v1"
wire_api = "responses"
experimental_bearer_token = "<本地服务 API Key>"
```

API key 当前保存在 `~/.codex/config.toml` 中；该文件应保持权限 `600`，不要提交到 Git 或公开分享。

## 临时使用本地 Qwen

启动一个使用 Qwen 的 Codex 会话：

```bash
codex -c model_provider=local_qwen -m qwen3.8-27b-fp8
```

非交互模式也使用同样的参数：

```bash
codex exec -c model_provider=local_qwen -m qwen3.8-27b-fp8 "你的任务"
```

这些参数只对当前新会话生效，不会改变默认配置。

## 使用 GPT 模型

直接运行 Codex：

```bash
codex
```

也可以临时指定 GPT 模型：

```bash
codex -c model_provider=openai -m gpt-5.6-sol
codex -c model_provider=openai -m gpt-5.6-terra
codex -c model_provider=openai -m gpt-5.6-luna
```

如果使用新的默认配置，修改 `~/.codex/config.toml` 顶部的 `model`；不要把 `model_provider = "local_qwen"` 写成全局默认，除非确实想让 Qwen 替代默认 GPT。

## 验证配置

检查默认 provider：

```bash
codex doctor --summary
```

预期默认值为：

```text
model: gpt-5.6-luna
model provider: openai
```

检查临时 Qwen 调用：

```bash
codex exec --ephemeral --skip-git-repo-check \
  -c model_provider=local_qwen \
  -m qwen3.8-27b-fp8 \
  "Reply exactly QWEN_OK and nothing else."
```

## 常见错误

### 把 Qwen 设成了默认模型

如果 `codex doctor` 显示 `model provider: local_qwen`，恢复 `~/.codex/config.toml` 顶部为：

```toml
model = "gpt-5.6-luna"
```

并删除全局的：

```toml
model_provider = "local_qwen"
model_context_window = 262144
```

保留 `[model_providers.local_qwen]` 整个配置块，这样仍可通过命令临时使用 Qwen。

### Qwen 服务不可访问

```bash
curl --noproxy '*' \
  -H 'Authorization: Bearer <本地服务 API Key>' \
  http://172.20.149.215:8000/v1/models
```

### 修改默认配置后没有生效

退出当前 Codex 并重新启动；配置文件通常在新会话启动时加载。
