# tmux/终端自动检查并接入代理

## 本次修改

修改文件：

```text
/home/mac/v2raya-tproxy-kit/scripts/proxy_env.sh
```

该文件本来就由 `~/.bashrc` 加载，因此普通 Terminator 终端和 tmux 新建的 shell 会使用同一套逻辑，不需要在 `.tmux.conf` 中重复启动代理。

修改前备份：

```text
proxy_env.sh.before-auto-system-proxy
```

修改后快照：

```text
proxy_env.sh.after-auto-system-proxy
```

## 自动策略

每次启动交互式 bash 时，`proxy_env_auto` 按以下顺序检查：

1. 如果 `127.0.0.1:10808` 正在监听：
   - 设置当前 shell 的 HTTP/HTTPS 代理为 `http://127.0.0.1:10808`。
   - 设置当前 shell 的 SOCKS 代理为 `socks5h://127.0.0.1:10808`。
   - 确保 GNOME 系统代理为手动模式，HTTP/HTTPS/SOCKS 都指向 `127.0.0.1:10808`。
2. 如果 10808 不可用：
   - 只关闭本逻辑之前管理的、且恰好指向 `127.0.0.1:10808` 的 GNOME 系统代理。
   - 不修改其他手动代理配置。
   - 如果 v2rayA 的 20170/20171 端口可用，保持终端代理变量和 GNOME 手动代理不变，因为 v2rayA tproxy 不需要它们。
3. 本逻辑只检查端口和设置当前用户环境，不启动、停止或杀掉 v2rayN、xray、v2rayA。

## 验证

查看当前端口：

```bash
ss -lntup | rg ':(10808|20170|20171)\b'
```

查看当前终端变量：

```bash
proxy-show
```

手动重新执行自动检查：

```bash
proxy-auto
```

查看 GNOME 系统代理：

```bash
gsettings get org.gnome.system.proxy mode
gsettings get org.gnome.system.proxy.http host
gsettings get org.gnome.system.proxy.http port
```

修改后已有 shell 不会自动重新执行 `.bashrc`。在已有 shell 中执行：

```bash
source ~/.bashrc
```

新建 tmux window 或 pane 时会自动加载该逻辑：

```text
Ctrl-b c        新建 window
Ctrl-b %        新建左右 pane
Ctrl-b "        新建上下 pane
```

## 回滚

恢复修改前的 helper：

```bash
cp -a /home/mac/macperson/computer_tools_backup/tmux_setup/proxy_env.sh.before-auto-system-proxy \
  /home/mac/v2raya-tproxy-kit/scripts/proxy_env.sh
source ~/.bashrc
```

回滚只恢复 shell helper，不会自动恢复已经改变的 GNOME 系统代理状态；如需手动关闭系统代理：

```bash
gsettings set org.gnome.system.proxy mode 'none'
```

## 注意

如果 tmux server 是很久以前从 SSH 会话启动的，里面保存的 `DBUS_SESSION_BUS_ADDRESS` 可能已经过期。此时 shell 代理变量仍可设置，但 GNOME 系统代理可能无法更新；从当前图形终端重启 tmux server 后再试即可。
