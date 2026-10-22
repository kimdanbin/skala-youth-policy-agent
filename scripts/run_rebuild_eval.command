#!/bin/bash
# 벡터 DB 다시 만들기(표 추출 적용) + 평가 — Finder에서 더블클릭. (Ollama 켜져 있어야 함: bge-m3 임베딩)
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
LOG="logs/rebuild_eval_$(date +%Y%m%d_%H%M%S).log"
source .venv/bin/activate
export PYTHONUNBUFFERED=1
{
  echo "== [1/6] 표 추출 테스트 (이 맥의 PyMuPDF로: 숫자가 하나도 안 사라지는지)"
  python -m pytest -q backend/tests/test_ingest.py || { echo "!! 표 추출 테스트 실패 → 중단 (DB 그대로 둠)"; exit 1; }
  echo "== [2/6] 벡터 DB 새로 만들기"
  python backend/rag/ingest.py
  echo "== [3/6] 검색 점검"
  python backend/rag/retriever.py
  echo "== [4/6] 켜져 있는 백엔드 서버가 새 DB를 다시 열게 함 (uvicorn --reload)"
  touch backend/main.py && echo "완료"
  echo "== [5/6] 전체 단위 테스트"
  python -m pytest -q
  echo "== [6/6] Before/After 평가 (LLM_BACKEND=$(grep '^LLM_BACKEND=' .env | cut -d= -f2))"
  python eval/run_eval.py
  echo "== 끝"
} 2>&1 | tee "$LOG"
echo "로그: $LOG"
