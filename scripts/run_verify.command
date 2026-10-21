#!/bin/bash
# Step 5 검증 스크립트 — Finder에서 더블클릭하면 터미널이 열리며 실행된다.
# 순서: 백엔드 서버 종료 → 패키지 설치 → 벡터 DB 재생성 → 검색 점검 → 테스트 → 에이전트 시나리오 6개
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
LOG="logs/verify_$(date +%Y%m%d_%H%M%S).log"
source .venv/bin/activate
export PYTHONUNBUFFERED=1        # 출력이 바로바로 보이게 (tee로 넘길 때 버퍼링 방지)
{
  echo "== [1/6] 백엔드 서버(uvicorn) 종료"
  pkill -f "uvicorn main:app" && echo "종료함" || echo "실행 중인 서버 없음"
  sleep 1
  echo "== [2/6] 패키지 설치"
  pip install -q -r requirements.txt && echo "설치 완료"
  echo "== [3/6] 벡터 DB 새로 만들기"
  python backend/rag/ingest.py
  echo "== [4/6] 검색 점검"
  python backend/rag/retriever.py
  echo "== [5/6] 단위 테스트"
  python -m pytest -q
  echo "== [6/6] 에이전트 시나리오 6개 (Ollama 사용, 몇 분 걸림)"
  python scripts/try_agent.py
  echo "== 끝"
} 2>&1 | tee "$LOG"
echo "로그: $LOG"
