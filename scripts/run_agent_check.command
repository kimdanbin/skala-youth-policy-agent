#!/bin/bash
# 빠른 확인용: 단위 테스트 + 에이전트 시나리오 6개만 (벡터 DB·패키지는 run_verify.command로 이미 준비된 상태)
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
LOG="logs/agent_check_$(date +%Y%m%d_%H%M%S).log"
source .venv/bin/activate
export PYTHONUNBUFFERED=1
{
  echo "== [1/2] 단위 테스트"
  python -m pytest -q
  echo "== [2/2] 에이전트 시나리오 6개"
  python scripts/try_agent.py
  echo "== 끝"
} 2>&1 | tee "$LOG"
echo "로그: $LOG"
