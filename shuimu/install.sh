#!/usr/bin/env bash
# install.sh — 水木股版爬虫工具包一键安装 (Ubuntu 22.04+/x86_64)
# 用法: ./install.sh   (在本目录内执行)
# 依赖安装策略: pypi 直连 -> 本目录 offline_wheels/ 离线包 -> 阿里云镜像
set -euo pipefail
cd "$(dirname "$0")"

echo "==> [1/4] 检查基础依赖 (python3-venv / git)"
need_pkgs=()
python3 -m venv --help >/dev/null 2>&1 || need_pkgs+=(python3-venv)
command -v git >/dev/null 2>&1 || need_pkgs+=(git)
if [ ${#need_pkgs[@]} -gt 0 ]; then
    echo "    缺少: ${need_pkgs[*]} -> apt install (需要 sudo)"
    sudo apt update -qq && sudo apt install -y -qq "${need_pkgs[@]}"
fi
PYVER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo "    python3 = $PYVER"

echo "==> [2/4] 创建虚拟环境 .venv 并安装依赖"
[ -d .venv ] || python3 -m venv .venv
if ! ./.venv/bin/pip install -q -r requirements.txt 2>/tmp/pip_err.log; then
    if [ -d offline_wheels ]; then
        echo "    pypi 直连失败, 使用本目录 offline_wheels/ 离线包..."
        ./.venv/bin/pip install -q --no-index --find-links offline_wheels -r requirements.txt
    else
        echo "    pypi 直连失败, 换阿里云镜像源重试..."
        ./.venv/bin/pip install -q -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
    fi
fi
./.venv/bin/python -c "from scrapling.fetchers import FetcherSession; print('    scrapling import OK (TLS 指纹核心)')"

echo "==> [3/4] 初始化归档仓 archive/"
mkdir -p archive logs
( cd archive && [ -d .git ] || git init -q . )
# 附件图默认进 git (每张几十 KB, 便于整体备份); 如不想进版本控制, 在 archive/.gitignore 加 "attachments/"
# archive 内建议 git user 未设时给默认 (仅本地仓)
( cd archive && git config user.name >/dev/null 2>&1 || git config user.name "shuimu-bot" )
( cd archive && git config user.email >/dev/null 2>&1 || git config user.email "shuimu@local" )
( cd archive && git config commit.gpgsign false )

echo "==> [4/4] 校验凭据文件 credentials"
if [ ! -f credentials ]; then
    cp credentials.template credentials
    chmod 600 credentials
    echo "    !! 已生成 credentials 模板 (从 credentials.template)"
    echo "    !! 下一步必做: 编辑 credentials 填入你的水木账号密码, 然后运行:"
    echo "       ./.venv/bin/python _img_selftest.py   (环境自检, 全绿即部署完成)"
    exit 0
fi
if ! grep -q '^username=.' credentials || ! grep -q '^password=.' credentials; then
    echo "    !! credentials 格式不对, 需要两行: username=xxx 和 password=xxx"
    exit 1
fi
chmod 600 credentials 2>/dev/null || true
echo "    credentials 格式 OK"

echo ""
echo "✅ 安装完成。自检:"
echo "   ./.venv/bin/python _img_selftest.py"
echo "   然后造队列开爬 (见 README 第四节):"
echo "   ./.venv/bin/python make_queue.py --start YYYY-MM-DD --end 'YYYY-MM-DD HH:MM'"
echo "   ./.venv/bin/python nf_crawler.py"
