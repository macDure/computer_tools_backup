#!/bin/bash
# sync_backup.sh — 把生产脚本同步到 computer_tools_backup/shuimu/ 并 git commit (单文件级, 不碰仓里其他备份)
# 用法: sync_backup.sh <文件...>          例: sync_backup.sh queue_add_windows.py nf_crawler.py
# 环境变量 SYNC_MSG 可覆盖 commit message。文件内容与备份仓一致时自动跳过 (NO_CHANGE)。
set -euo pipefail
cd "$(dirname "$0")"
[ $# -gt 0 ] || { echo "用法: $0 <文件...>"; exit 1; }
for f in "$@"; do
  [ -f "$f" ] || { echo "文件不存在: $f"; exit 1; }
  case "$f" in */*) echo "只接受文件名, 不接受路径: $f"; exit 1;; esac
done
MSG="${SYNC_MSG:-shuimu: 同步生产脚本 $(date '+%Y-%m-%d %H:%M')}"
docker run --rm \
  -v /home/mac/.hermes/scripts/shuimu_daily:/src \
  -v /home/mac/macperson/computer_tools_backup:/r \
  ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie bash -c "
  git config --global --add safe.directory /r 2>/dev/null || true
  for f in $*; do cp /src/\"\$f\" /r/shuimu/\"\$f\"; done
  cd /r
  git config user.name 'macDure'; git config user.email 'machao-1990@163.com'
  git add $(printf 'shuimu/%s ' $*)
  if git diff --cached --quiet; then echo 'NO_CHANGE: 备份仓已是最新, 跳过 commit'; exit 0; fi
  git commit -q -m '$MSG'
  git log --oneline -1
" "$@"
