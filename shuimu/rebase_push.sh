#!/bin/bash
# rebase_push.sh — rebase 到远端最新后重推大 commit
set -u
cd /s
git config --global --add safe.directory /s 2>/dev/null || true
git config user.name 'macDure'
git config user.email 'machao-1990@163.com'
export GIT_SSH_COMMAND='ssh -i /ssh/id_ed25519 -F /dev/null -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20'
export TZ=Asia/Shanghai

echo "BEFORE: local=$(git rev-parse --short HEAD)"
git fetch origin 2>&1 | tail -2
echo "REMOTE: $(git rev-parse --short origin/main)"

# 只 rebase 我领先的那个 commit (主题分类+Icestone+tools)
if ! git rev-parse --verify origin/main >/dev/null 2>&1; then
  echo "origin/main 不存在"; exit 1
fi
git rebase origin/main 2>&1 | tail -8

echo "AFTER: local=$(git rev-parse --short HEAD)"
# 确认只领先 1 个 commit
n=$(git rev-list --count origin/main..HEAD)
echo "领先远端 commit 数: $n"

git push origin main 2>&1 | tail -3
echo "FINAL local=$(git rev-parse --short HEAD)"
