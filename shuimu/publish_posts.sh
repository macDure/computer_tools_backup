#!/bin/bash
# publish_posts.sh — 水木归档发布到 stock_research_mac (宿主机 git 仓, 远端 github)
# 用法: docker run --rm \
#         -v /home/mac/.hermes/shuimu_daily:/arch \
#         -v /home/mac/macperson/stock_research_mac:/s \
#         -v /home/mac/.ssh:/ssh:ro \
#         <镜像> bash /tmp/publish_posts.sh
# 行为: rsync 归档(2026/topics) → shuimu/帖子/ → git add/commit/push
# 注意: 不带 --delete, 目标里的 Icestone/(用户手工放的历史归档)不受影响;
#       归档中被删除的窗文件按 git 删除清单显式清理(防 re-crawl 后残留旧数据)。
set -u
cd /s
git config --global --add safe.directory /s 2>/dev/null || true
git config user.name 'macDure'
git config user.email 'machao-1990@163.com'
export TZ=Asia/Shanghai

# 镜像无 rsync, 用 cp -a 合并覆盖 (同名文件更新, 新文件加入, 不删目标独有文件)
mkdir -p /s/shuimu/帖子/2026 /s/shuimu/帖子/topics
cp -a /arch/2026/. /s/shuimu/帖子/2026/
cp -a /arch/topics/. /s/shuimu/帖子/topics/

# 归档里被 git 删除的文件 → 目标同步删
cd /arch
while read -r f; do
  [ -n "$f" ] || continue
  sub=${f%%/*}            # 2026 或 topics
  case "$sub" in
    2026|topics) rm -f "/s/shuimu/帖子/$f" 2>/dev/null ;;
  esac
done < <(git status --porcelain | awk '$1=="D"{print $2}')

cd /s
git add -A shuimu/
if git diff --cached --quiet; then
  echo "PUBLISH: 无新变更, 跳过 commit (最新: $(git log --oneline -1))"
  exit 0
fi
n=$(git diff --cached --numstat | wc -l)
git commit -q -m "shuimu: 帖子自动归档 $(date '+%Y-%m-%d %H:%M') ($n 文件变更)"
GIT_SSH_COMMAND='ssh -i /ssh/id_ed25519 -F /dev/null -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20' \
  git push origin main 2>&1 | tail -1
echo "PUBLISH: $(git log --oneline -1)"
