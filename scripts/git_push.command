#!/bin/bash
# GitHub에 올리기 — Finder에서 더블클릭
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
{ git push origin main && git status -sb | head -1; } 2>&1 | tee logs/git_push.log
