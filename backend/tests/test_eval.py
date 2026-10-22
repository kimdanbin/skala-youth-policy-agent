"""평가 스크립트의 채점·요약 부분 (LLM 없이)"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("run_eval", Path(__file__).resolve().parents[2] / "eval" / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


def test_questions_file_is_consistent():
    for q in run_eval.QUESTIONS:
        assert {"id", "type", "question", "routes", "pages", "reference"} <= q.keys()
        assert all(isinstance(g, list) and g for g in q.get("must", []))


def test_rule_check():
    q = {"must": [["60%"], ["153.8", "1,538"]], "must_not": ["신생아"], "pages": ["문서 3쪽"]}
    r = run_eval.rule_check(q, "60% 이하, 1,538원", ["문서 3쪽"])
    assert r == {"must_rate": 1.0, "must_missing": [], "must_not_found": [], "page_hit": True}
    r = run_eval.rule_check(q, "60% 이하, 신생아 대출", ["문서 1쪽"])
    assert r["must_rate"] == 0.5 and r["must_missing"] == ["153.8"] and r["must_not_found"] == ["신생아"] and r["page_hit"] is False
    assert run_eval.rule_check({"pages": []}, "x", [])["page_hit"] is None


def test_summary_table():
    j = {"accuracy": 4, "grounded": 5, "helpful": 3, "reason": "ok"}
    side = {"must_rate": 0.5, "must_not_found": [], "page_hit": True, "judge": j, "elapsed_sec": 2.0, "llm_calls": 1,
            "route": "doc", "route_ok": True}
    rows = [{"id": "D1", "type": "doc", "question": "q", "before": side, "after": {**side, "must_rate": 1.0}},
            {"id": "C1", "type": "clarify", "question": "q2", "before": {**side, "must_rate": None, "page_hit": None},
             "after": {**side, "must_rate": None, "page_hit": None}}]
    md = run_eval.summary(rows, {"time": "t", "llm_backend": "openai", "judge": "gpt-4o"})
    assert "| 필수 사실 포함률 | 50% | 100% |" in md and "| 정답 쪽 검색 | 100% | 100% |" in md
    assert "After 경로 정확도: 100%" in md and md.count("| D1 |") == 1
