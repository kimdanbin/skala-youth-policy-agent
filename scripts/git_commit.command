#!/bin/bash
# logs/commit_msg.txt 내용으로 커밋 — Finder에서 더블클릭
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
{
  git add -A && git commit -F logs/commit_msg.txt && git log --oneline -3 && git status -sb | head -3
} 2>&1 | tee logs/git_commit.log
