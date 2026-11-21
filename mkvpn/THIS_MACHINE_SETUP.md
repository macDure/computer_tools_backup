# 本机 TrustAccess 出差配置与验证记录

检查日期：2026-11-10。机器：`mac-ThinkPad-T14p-Gen-3`。

本机配置已部署，登录页面与 NPAPI 插件已实测启动。**尚未完成外部网络登录、隧道通信、换网恢复及长时间稳定性验收。** 当前同时接着公司网络，内网可达不能作为 VPN 验收证据。另一台电脑目前未直接登录核查；兼容性对照来源是本仓库的备份与排坑记录。

## 兼容性检查

| 项目 | 本机结果 | 结论 |
| --- | --- | --- |
| 系统 | Ubuntu 24.04.4 LTS，x86_64，内核 7.0.0-34-generic | 包架构匹配；内核隧道协商仍待真实登录验证 |
| TrustAccess | 1.0.1-1 已安装，`dpkg -V trustaccess` 无差异 | 复用现有安装，无需重装 |
| 后台 | `secvpnMonitord`、`secvpnServerd` 各一个，服务 active，有开机启动链接 | 基础后台正常 |
| 本地交接 | `secvpn.fox`、`secvpn.cli`、`scsProxy.ctl` 正在监听 | 浏览器交接入口存在 |
| 浏览器 | Pale Moon 34.3.2.1，本体及 libxul 的 SHA-256 与仓库一致 | 复用匹配版本 |
| 动态库 | 浏览器、GTK2、插件与 TrustAccess 的 32 个 ELF 文件依赖检查通过 | 未发现缺库；无需全局替换系统运行库 |
| 插件实载 | `plugin-container` 映射了 `/usr/lib/mozilla/plugins/libnpSecClientAssist.so` | 实际加载通过；不以单个进程隔离偏好值推断运行方式 |
| 网关 | 1443 可达，登录页最终 HTTP 200，标题“用户登录” | 登录入口可用，尚未提交认证 |
| Firefox 标识 | 桌面入口使用的旧 `user.js` 缺少 UA 覆写 | 已补齐；实时网关 JS 仍检查 Firefox/Linux 才插入插件 |
| iptables | `/sbin` → `usr/sbin`，`/sbin/iptables` 已通过 alternatives 指向 nft 实现 | 不执行旧文档的强制软链接，不切换 Docker 所用防火墙后端；客户端规则下发仍待认证后验证 |
| 内网域名 | hosts 中三个 mkzy 域名已指向 172.20.149.216 | 已存在，无需追加；现有重复行未改动 |
| 其他企业 VPN | 未发现 aTrust/EasyConnect 安装包或相关进程 | 不执行旧文档的卸载清理 |
| 当前隧道 | 无 `172.20.70.*`、无 pluto；到目标走公司有线网络 | 当前不能判定出差 VPN 可用 |

## 本次部署

实际运行目录：`/home/mac/Downloads/palemoon-trustaccess`。沿用现有浏览器及 profile，保留现有认证数据；只合并必要偏好项并替换启动工具。

- 补齐 Firefox UA、两种大小写的插件激活项，保留备份中的其余必要设置。
- 更新 `connect-trustaccess.sh`：增加启动互斥、后台完整性检查、换网后旧源地址识别，以及显式 `--reconnect`。重连只关闭当前用户使用此 VPN profile 的浏览器，随后通过系统认证停止 TrustAccess 后台及其 IPsec 进程；检测到其他实现的 pluto 时拒绝自动清理。没有调用会全局清空 XFRM 状态的旧 `secvpn setup stop`。
- 增加只读 `check-trustaccess.py`：检查网关 TCP 1443、VPN 地址、后台、本地 socket、内网目标 TCP 80、路由与公司直连干扰。除目标子网的直连路由外，也将物理网卡上的公司 `172.20.*` 地址（排除 VPN 的 `172.20.70.*`）标为可能的旁路，覆盖公司 Wi-Fi 经路由器访问目标的情况。支持定次采样，不自动登录或重置网络。
- 桌面和应用菜单入口均更新为 `TrustAccess-VPN.desktop`，添加“换网后重连”和“检查 VPN 连通性”操作。
- 旧入口 `start-palemoon.sh` 也转到同一连接脚本，避免继续走缺少恢复检查的旧路径。
- 没有修改系统路由、NetworkManager 连接、iptables alternatives、hosts 或自动生成的 `/etc/ipsec.conf`。

原脚本、user.js、桌面入口的备份位于：

```text
/home/mac/.local/state/mkvpn/backups/20261110-174444/
```

日志位于 `$HOME/.local/state/mkvpn/browser.log` 和 `launcher.log`，不写入 Git 中的浏览器备份。启动程序在用户可写的日志文件上采用私有权限。

验证结果：Shell/Python 语法检查、6 组连接状态判定检查、两个 desktop 文件校验通过；运行目录与仓库中的四个工具文件逐一 SHA-256 一致。4 次短时采样均为公司直连、网关可达、没有 VPN 地址，此结果不代表长时间稳定性。最终只读检查保存于 `$HOME/.local/state/mkvpn/preflight-20261110.jsonl`。新增重连的管理员操作尚未实际执行，留待外部网络验收时一并验证。

## 出差使用

1. 先连接酒店网络或手机热点，并完成可能存在的网页上网认证。
2. 双击桌面的 **TrustAccess VPN Login**，在专用 Pale Moon 中输入 VPN 账号密码。脚本不保存账号密码。
3. 换网络或睡眠唤醒后，使用图标右键菜单中的“换网后重连”；也可以运行：

   ```bash
   "$HOME/Downloads/palemoon-trustaccess/connect-trustaccess.sh" --reconnect
   ```

   此操作会关闭 VPN 登录窗口并请求本机管理员认证，随后需要重新输入 VPN 登录信息。普通双击遇到已有浏览器时会提示使用原窗口。

4. 页面显示在线但 SSH/内网页面失效时，先 `Ctrl+F5` 重新认证；旧电脑记录曾在约 3.5～4 小时出现服务端超时，这不是本机测得的固定时长。重新认证不恢复时，再执行上述重连。
5. 检查真实连接状态：

   ```bash
   "$HOME/Downloads/palemoon-trustaccess/connect-trustaccess.sh" --check
   ```

检查结果含义：

| 状态 | 含义 |
| --- | --- |
| `LAN_ACCESS_VPN_UNPROVEN` | 检测到公司目标网段的直连路由或物理网卡上的公司地址，无法据此证明 VPN 可用 |
| `VPN_NOT_CONNECTED` | 没有 VPN 地址，尚未连接 |
| `GATEWAY_UNREACHABLE` | 网关 TCP 不通，先检查普通网络 |
| `TUNNEL_PRESENT_INTERNAL_UNREACHABLE` | 地址仍在，但目标端口不通，可能失效或目标服务故障 |
| `VPN_CANDIDATE_NEEDS_EXTERNAL_ACCEPTANCE` | 有 VPN 地址、网关及内网端口可达；还需确认外部网络与实际加密通信 |

退出码 0 仅表示每次采样都符合最后一项的候选条件；其他情况返回 2，不能把退出码当作完整验收。该检查没有读取需要 root 的 XFRM 计数器，不证明加密流量实际经过隧道。

## 尚待完成的验收

必须在没有公司直连旁路的外部网络完成。当前公司有线和公司 Wi-Fi 同时在线，切网会影响已有连接；未取得切网确认前不自动断开。

1. 手动切至手机热点，确认 `ip route get 111.202.232.70` 选择该热点；到内网目标的路径没有公司直连旁路。
2. 登录后确认获得 `172.20.70.*`，并验证 GitLab/包服务和实际工作所用 SSH 目标。不能用 SSH 密码错误来判断 VPN 不通，也不能用网页登录成功替代隧道验证。
3. 由管理员读取 `ip -s xfrm state`，在访问内网前后观察匹配公司网关的策略/收发计数，或使用等价抓包证据确认流量路径。不要公开输出密钥。
4. 连续采样，并实际使用工作业务。以下约 5 小时采样便于发现旧记录中的超时问题，记录失败后重新认证及恢复时间：

   ```bash
   "$HOME/Downloads/palemoon-trustaccess/connect-trustaccess.sh" \
     --check --json --samples 300 --interval 60 \
     | tee "$HOME/.local/state/mkvpn/travel-check.jsonl"
   ```

5. 验证热点断开/恢复、睡眠唤醒和重启后重连。以上项目未实测前，只能确认配置与登录组件兼容，不能承诺出差稳定性。

专用旧浏览器只用于单位 VPN 登录。完整 profile 包含历史/认证状态，后续向其他机器迁移时应只复制必要配置，避免将运行中的缓存和认证文件再次提交到 Git。
