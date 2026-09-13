#!/bin/bash
# publish_all.sh — 一次性发布: 全年主题分类 + Icestone 文件夹 + tools 四件套
set -u
cd /s
git config --global --add safe.directory /s 2>/dev/null || true
git config user.name 'macDure'
git config user.email 'machao-1990@163.com'
export TZ=Asia/Shanghai

# 1. 全年主题分类 (2026/01~09)
rm -rf shuimu/帖子按主题分类/2026
mkdir -p shuimu/帖子按主题分类/2026
cp -a /stage_topic/2026/. shuimu/帖子按主题分类/2026/
echo "STAGE1: 主题分类月份: $(ls shuimu/帖子按主题分类/2026/)"

# 2. Icestone 按主题文件夹
rm -rf shuimu/Icestone
mkdir -p shuimu/Icestone
cp -a /stage_ice/Icestone/. shuimu/Icestone/
echo "STAGE2: Icestone 文件数: $(ls shuimu/Icestone | wc -l)"

# 3. tools 四件套 + README
mkdir -p shuimu/tools
cp -a /stage_tools/README.md /stage_tools/build_topic_archive.py /stage_tools/extract_author_posts.py /stage_tools/extract_author_topics.py /stage_tools/backfill_meta.py shuimu/tools/
echo "STAGE3: tools: $(ls shuimu/tools/ | tr '\n' ' ')"

# 只提交这三个目录 (不碰爬虫正在写的窗)
git add -A "shuimu/帖子按主题分类/" shuimu/Icestone shuimu/tools
n=$(git diff --cached --numstat | wc -l)
echo "ADDED: $n 文件"
git commit -q -m "shuimu: 2026全年(1-9月)帖子按主题分类 + Icestone按主题文件夹(833主题/1976帖) + tools后处理工具四件套(零依赖, --arch可换机) ($n 文件变更)"
GIT_SSH_COMMAND='ssh -i /ssh/id_ed25519 -F /dev/null -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20' \
  git push origin main 2>&1 | tail -2
echo "PUBLISH: $(git log --oneline -1)"
