#!/bin/bash
# 평가 — Finder에서 더블클릭하면 터미널이 열리며 실행된다. (Ollama는 임베딩용으로 켜져 있어야 함)
# 순서: 단위 테스트 → Before/After 평가 10문항 (결과: eval/results/)
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
LOG="logs/eval_$(date +%Y%m%d_%H%M%S).log"
source .venv/bin/activate
export PYTHONUNBUFFERED=1
{
  echo "== [1/2] 단위 테스트"
  python -m pytest -q
  echo "== [2/2] Before/After 평가 (LLM_BACKEND=$(grep '^LLM_BACKEND=' .env | cut -d= -f2))"
  python eval/run_eval.py
  echo "== 끝"
} 2>&1 | tee "$LOG"
echo "로그: $LOG"
