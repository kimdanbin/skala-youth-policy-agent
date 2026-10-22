#!/bin/bash
# OpenAI(gpt-4o-mini) 확인 — Finder에서 더블클릭하면 터미널이 열리며 실행된다.
# 순서: 패키지 설치(langchain-openai) → 단위 테스트 → 에이전트 시나리오 6개 → 켜져 있는 서버 다시 읽기
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
LOG="logs/openai_check_$(date +%Y%m%d_%H%M%S).log"
source .venv/bin/activate
export PYTHONUNBUFFERED=1
{
  echo "== [1/4] 패키지 설치"
  pip install -q -r requirements.txt && echo "설치 완료"
  echo "== [2/4] 단위 테스트"
  python -m pytest -q
  echo "== [3/4] 에이전트 시나리오 6개 (LLM_BACKEND=$(grep '^LLM_BACKEND=' .env | cut -d= -f2))"
  python scripts/try_agent.py
  echo "== [4/4] 켜져 있는 백엔드 서버가 새 코드를 다시 읽게 함 (uvicorn --reload)"
  touch backend/main.py && echo "완료"
  echo "== 끝"
} 2>&1 | tee "$LOG"
echo "로그: $LOG"
