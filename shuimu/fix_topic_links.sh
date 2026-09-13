#!/bin/bash
# fix_topic_links.sh — 重生成后的主题归档(修复附件路径+图片markdown化)写入宿主仓并发布
# 用法: docker run --rm \
#         -v /home/mac/.hermes/tmp/topic_archive:/stage \
#         -v /home/mac/macperson/stock_research_mac:/s \
#         -v /home/mac/.ssh:/ssh:ro <镜像> bash /tmp/fix_topic_links.sh
set -u
cd /s
git config --global --add safe.directory /s 2>/dev/null || true
git config user.name 'macDure'
git config user.email 'machao-1990@163.com'
export TZ=Asia/Shanghai

DEST="shuimu/帖子按主题分类/2026/01"
# 全量重建当月目录(生成器幂等, 先清后拷防残留)
rm -rf "$DEST"
mkdir -p "$DEST"
cp -a /stage/2026/01/. "$DEST"/

n_md=$(ls "$DEST" | grep -c '\.md$')
echo "STAGE: $DEST 重建完成, $n_md 个主题 md + meta.json"

# 只提交主题分类目录, 不动爬虫工作区的其他未提交变更
git add -A "shuimu/帖子按主题分类/"
if git diff --cached --quiet; then
  echo "PUBLISH: 无变更(不应发生)"
  exit 0
fi
cnt=$(git diff --cached --numstat | wc -l)
git commit -q -m "shuimu: 修复帖子按主题分类附件相对路径(补年份层级) + 图片改markdown语法可直接渲染 ($cnt 文件变更)"
GIT_SSH_COMMAND='ssh -i /ssh/id_ed25519 -F /dev/null -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20' \
  git push origin main 2>&1 | tail -2
echo "PUBLISH: $(git log --oneline -1)"
