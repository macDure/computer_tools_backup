#!/usr/bin/env bash
# ==============================================================================
# Terminator 中文输入法（Fcitx / 搜狗）一键修复与安装脚本
# 适用环境: Ubuntu / Debian / 及基于 GTK3 的 Linux 桌面系统
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
FCITX_CONFIG="${HOME}/.config/fcitx/config"

echo "=========================================================="
echo "    Terminator 中文输入法（Fcitx / 搜狗）一键修复工具"
echo "=========================================================="

# 1. 确保目录存在
mkdir -p "${BIN_DIR}" "${APP_DIR}"

# 2. 检查 fcitx-frontend-gtk3 依赖包（Ubuntu/Debian）
if command -v dpkg >/dev/null 2>&1; then
    if ! dpkg -s fcitx-frontend-gtk3 >/dev/null 2>&1; then
        echo "[!] 警告: 未检测到 fcitx-frontend-gtk3 模块。"
        echo "    建议先运行安装命令: sudo apt install -y fcitx-frontend-gtk3"
    else
        echo "[✓] 已检测到 fcitx-frontend-gtk3 前端模块"
    fi
fi

# 3. 部署修复版 Terminator 启动入口
echo "[*] 正在部署修复版 Terminator 到 ${BIN_DIR}/terminator ..."
if [ -f "/usr/bin/terminator" ]; then
    # 优先基于系统现有的 /usr/bin/terminator 进行动态补丁，保证版本完全兼容
    python3 -c "
import os
with open('/usr/bin/terminator', 'r') as f:
    code = f.read()

target = '''if os.environ.get('GTK_IM_MODULE') is not None:
    del os.environ['GTK_IM_MODULE']'''

replacement = '''# Preserved GTK_IM_MODULE for CJK / Fcitx support
os.environ['GTK_IM_MODULE'] = 'fcitx'
os.environ['QT_IM_MODULE'] = 'fcitx'
os.environ['XMODIFIERS'] = '@im=fcitx' '''

if target in code:
    code = code.replace(target, replacement)
    print('[✓] 成功移除 Terminator 源码中的 del os.environ[\"GTK_IM_MODULE\"] 硬编码 Bug')
else:
    print('[i] /usr/bin/terminator 未检测到特定代码块，使用预置补丁副本')

with open('${BIN_DIR}/terminator', 'w') as out:
    out.write(code)
" 2>/dev/null || cp -f "${SCRIPT_DIR}/terminator" "${BIN_DIR}/terminator"
else
    # 若系统尚未安装 terminator，则直接拷贝备份文件
    cp -f "${SCRIPT_DIR}/terminator" "${BIN_DIR}/terminator"
fi

chmod +x "${BIN_DIR}/terminator"
echo "[✓] 修复版可执行文件部署完成: ${BIN_DIR}/terminator"

# 4. 确保 ~/.local/bin 在 PATH 中
if ! echo "$PATH" | grep -q "${HOME}/.local/bin"; then
    echo "[*] 将 ~/.local/bin 添加至 ~/.bashrc PATH ..."
    echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> "${HOME}/.bashrc"
    echo "[✓] 已更新 ~/.bashrc"
fi

# 5. 部署/更新桌面启动项 terminator.desktop
echo "[*] 正在更新桌面启动项 ${APP_DIR}/terminator.desktop ..."
if [ -f "/usr/share/applications/terminator.desktop" ] && [ ! -f "${APP_DIR}/terminator.desktop" ]; then
    cp "/usr/share/applications/terminator.desktop" "${APP_DIR}/terminator.desktop"
fi

if [ -f "${APP_DIR}/terminator.desktop" ]; then
    # 替换可能存在的 env GTK_IM_MODULE=xim 或常规 terminator，统一指向 ~/.local/bin/terminator
    sed -i "s|Exec=.*terminator|Exec=${BIN_DIR}/terminator|g" "${APP_DIR}/terminator.desktop"
    sed -i "s|TryExec=.*|TryExec=${BIN_DIR}/terminator|g" "${APP_DIR}/terminator.desktop"
else
    # 拷贝随附的模板文件
    cp -f "${SCRIPT_DIR}/terminator.desktop" "${APP_DIR}/terminator.desktop"
    sed -i "s|Exec=.*terminator|Exec=${BIN_DIR}/terminator|g" "${APP_DIR}/terminator.desktop"
fi
echo "[✓] 桌面启动项更新完成"

# 6. 检查并修复 Fcitx 核心快捷键
if [ -f "${FCITX_CONFIG}" ]; then
    echo "[*] 检查 Fcitx 快捷键配置 (${FCITX_CONFIG}) ..."
    
    # 检查 TriggerKey
    if grep -q "^TriggerKey=$" "${FCITX_CONFIG}" || ! grep -q "^TriggerKey=" "${FCITX_CONFIG}"; then
        sed -i 's/^TriggerKey=.*/TriggerKey=CTRL_SPACE/' "${FCITX_CONFIG}" 2>/dev/null || echo "TriggerKey=CTRL_SPACE" >> "${FCITX_CONFIG}"
        echo "[✓] 恢复 Fcitx 激活快捷键为: Ctrl+Space"
    fi

    # 检查 SwitchKey (Shift 切换中英文)
    if grep -q "^SwitchKey=Disabled" "${FCITX_CONFIG}" || ! grep -q "^SwitchKey=" "${FCITX_CONFIG}"; then
        sed -i 's/^SwitchKey=.*/SwitchKey=SHIFT Both/' "${FCITX_CONFIG}" 2>/dev/null || echo "SwitchKey=SHIFT Both" >> "${FCITX_CONFIG}"
        echo "[✓] 恢复 Fcitx Shift 键切换中英文: SHIFT Both"
    fi

    # 检查 IMSwitchKey
    if grep -q "^IMSwitchKey=False" "${FCITX_CONFIG}" || ! grep -q "^IMSwitchKey=" "${FCITX_CONFIG}"; then
        sed -i 's/^IMSwitchKey=.*/IMSwitchKey=True/' "${FCITX_CONFIG}" 2>/dev/null || echo "IMSwitchKey=True" >> "${FCITX_CONFIG}"
        sed -i 's/^IMSwitchHotkey=.*/IMSwitchHotkey=CTRL_SHIFT/' "${FCITX_CONFIG}" 2>/dev/null || echo "IMSwitchHotkey=CTRL_SHIFT" >> "${FCITX_CONFIG}"
        echo "[✓] 恢复 Fcitx 列表循环快捷键: Ctrl+Shift"
    fi

    # 热重载 Fcitx 配置
    if command -v fcitx-remote >/dev/null 2>&1; then
        fcitx-remote -r >/dev/null 2>&1 || true
        echo "[✓] Fcitx 配置已热重载生效"
    fi
fi

# 7. 解决 IBus 与 Terminator 的 Ctrl+Shift+E 垂直分屏快捷键冲突
if command -v gsettings >/dev/null 2>&1; then
    current_emoji_hotkey=$(gsettings get org.freedesktop.ibus.panel.emoji hotkey 2>/dev/null || true)
    if [ "$current_emoji_hotkey" != "@as []" ] && [ -n "$current_emoji_hotkey" ]; then
        echo "[*] 清除 IBus 默认占用的 Ctrl+Shift+E 表情快捷键（避免与 Terminator 垂直分屏冲突）..."
        gsettings set org.freedesktop.ibus.panel.emoji hotkey "[]" 2>/dev/null || true
        echo "[✓] 已禁用 IBus Emoji 快捷键"
    fi
fi

echo "=========================================================="
echo "    [成功] 修复全部完成！"
echo "    请彻底关闭现有的 Terminator 窗口后重新打开测试。"
echo "    快捷键提示:"
echo "      - 按 Shift 键: 切换搜狗/中文与英文"
echo "      - 按 Ctrl+Space: 激活/关闭输入法"
echo "      - 按 Ctrl+Shift+E: 垂直分屏（已不受 IBus 干扰）"
echo "=========================================================="
