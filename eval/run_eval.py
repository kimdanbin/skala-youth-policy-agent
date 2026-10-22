"""Before(단순 RAG) vs After(멀티 에이전트) 평가.

같은 LLM(.env의 LLM_BACKEND)으로 같은 질문 10개를 두 방식에 넣고 비교한다.
  - 규칙 채점(코드): 필수 사실 포함률, 금지어(엉뚱한 대상 정책) 여부, 정답 쪽 검색 여부, 경로 정확도
  - LLM-as-a-Judge: gpt-4o(없으면 gpt-4o-mini)가 참고 답안(원본 PDF에서 확인한 사실)과 비교해 1~5점으로 채점
  - 시간, LLM 호출 수
실행 (프로젝트 최상위 폴더): python eval/run_eval.py
결과: eval/results/eval_시각.json (전체 기록), eval/results/summary_시각.md (표)
"""
import asyncio
import json
import os
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("LANGSMITH_PROJECT", "skala-youth-policy-agent-eval")   # 평가 기록은 따로 모음

from dotenv import load_dotenv   # noqa: E402

load_dotenv(ROOT / ".env")

from pydantic import BaseModel, Field   # noqa: E402

# 벡터 DB·LLM을 여는 모듈(rag.chain 등)은 main() 안에서 불러온다.
# 파일을 import만 해도 DB가 열리면, 테스트에서 채점 함수만 쓰려 해도 실제 DB를 건드리게 된다.

TODAY = os.getenv("FAKE_TODAY") or time.strftime("%Y-%m-%d")      # 채점자에게 오늘 날짜를 알려준다
QUESTIONS = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))

JUDGE_SYSTEM = """너는 청년정책 안내 챗봇의 답변을 채점하는 평가자다.
[참고 답안]은 원본 문서에서 사람이 확인한 사실이다. [답변]을 아래 세 기준으로 1~5점 채점하라.
오늘은 {today}이다. 문서와 정책은 2026년 자료이므로 '2026년'이라는 연도는 틀린 것이 아니다. 나이는 오늘 기준 만 나이로 계산하라.
표기만 다르고 값이 같으면 맞은 것이다(예: 1.22억원 = 1억 2,200만원 = 1억 2천2백만원).
[원문]이 주어지면 그것이 최종 근거다. 원문에 있는 내용은 참고 답안에 없더라도 맞은 것이고 근거 있는 것이다.
참고 답안과 원문 어디에도 없거나 그와 충돌하는 내용만 감점한다.
- accuracy(정확성): 답변의 금액·기준·기간·신청 상태가 참고 답안과 맞는가. 틀린 사실이 하나라도 있으면 3점 이하.
- grounded(근거성): 참고 답안이나 질문에 없는 내용을 지어내거나, 근거 없이 자격을 단정하지 않았는가.
- helpful(유용성): 질문에 직접 답하고, 지금 신청할 수 있는지·어떻게 신청하는지 등 사용자가 다음에 할 일을 알 수 있는가.
점수만 매기지 말고 reason에 감점 이유를 한두 문장으로 써라."""


class Judge(BaseModel):
    accuracy: int = Field(ge=1, le=5)
    grounded: int = Field(ge=1, le=5)
    helpful: int = Field(ge=1, le=5)
    reason: str


def source_text(pages: list[str]) -> str:
    """'2026_청년월세_전주시 3쪽' → 그 PDF 쪽의 글자 (채점자가 원문으로 확인하게)"""
    import unicodedata
    import pymupdf
    from rag.ingest import RAW_DIR, page_text
    files = {unicodedata.normalize("NFC", f.stem): f for f in RAW_DIR.glob("*.pdf")}
    out = []
    for ref in pages:
        name, page = ref.rsplit(" ", 1)
        if name in files:
            out.append(f"({ref})\n" + page_text(pymupdf.open(files[name])[int(page.rstrip("쪽")) - 1]))
    return "\n\n".join(out)


def rule_check(q: dict, answer: str, sources: list[str]) -> dict:
    """코드로 채점: 같은 답에는 언제나 같은 점수 (LLM 채점의 흔들림을 보완)"""
    must = q.get("must", [])
    hit = [any(alt in answer for alt in group) for group in must]
    return {
        "must_rate": round(sum(hit) / len(must), 2) if must else None,
        "must_missing": [g[0] for g, h in zip(must, hit) if not h],
        "must_not_found": [w for w in q.get("must_not", []) if w in answer],
        "page_hit": (any(p in sources for p in q["pages"]) if q["pages"] else None),
    }


async def judge(llms: list, q: dict, answer: str) -> dict:
    """llms = [(모델 이름, LLM), ...] 앞에서부터 시도. 답변을 만든 모델(gpt-4o-mini)보다 강한 모델로
    채점해야 '자기 답을 후하게 보는' 편향이 줄어든다. 쓸 수 없으면 다음 모델로."""
    msgs = [("system", JUDGE_SYSTEM.format(today=TODAY)),
            ("human", f"[질문]\n{q['question']}\n\n[참고 답안]\n{q['reference']}\n\n"
                      + (f"[원문]\n{q['_source']}\n\n" if q.get("_source") else "") + f"[답변]\n{answer}")]
    err = None
    for name, llm in llms:
        try:
            j = await llm.with_structured_output(Judge).ainvoke(msgs)
            return {**j.model_dump(), "model": name}
        except Exception as e:                   # 채점 실패는 기록만 하고 다음 모델 / 계속
            err = e
    return {"accuracy": None, "grounded": None, "helpful": None, "reason": f"채점 실패: {err}", "model": None}


async def main():
    from langchain_openai import ChatOpenAI
    from agent.deps import build_real_deps
    from agent.graph import build_graph, run
    from agent.mcp_tools import McpTools
    from rag.chain import answer as basic_answer

    judge_llm = [(m, ChatOpenAI(model=m, temperature=0, max_retries=4, timeout=60))
                 for m in dict.fromkeys([os.getenv("JUDGE_MODEL", "gpt-4o"), "gpt-4o-mini"])]
    rows = []
    async with McpTools() as mcp:
        graph = build_graph(build_real_deps(mcp))
        for q in QUESTIONS:
            q = {**q, "_source": source_text(q["pages"])}
            row = {"id": q["id"], "type": q["type"], "question": q["question"]}
            # Before: 단순 RAG (질문으로 바로 3개 검색 → 답변). 정책 목록·되묻기 기능은 없다.
            t = time.perf_counter()
            try:
                b = await asyncio.to_thread(basic_answer, q["question"])
                b_ans, b_src, b_err = b["reply"], b["sources"], None
            except Exception as e:
                b_ans, b_src, b_err = "", [], str(e)
            row["before"] = {"answer": b_ans, "sources": b_src, "error": b_err, "llm_calls": 1,
                             "elapsed_sec": round(time.perf_counter() - t, 2),
                             **rule_check(q, b_ans, b_src), "judge": await judge(judge_llm, q, b_ans)}
            # After: 멀티 에이전트
            a = await run(graph, q["question"])
            row["after"] = {"answer": a["answer"], "sources": a["sources"], "error": a["error"],
                            "llm_calls": a["llm_calls"], "elapsed_sec": a["elapsed_sec"], "path": a["path"],
                            "route": (a["plan"] or {}).get("route"),
                            "route_ok": (a["plan"] or {}).get("route") in q["routes"],
                            **rule_check(q, a["answer"], a["sources"]), "judge": await judge(judge_llm, q, a["answer"])}
            rows.append(row)
            print(f"[{q['id']}] before must={row['before']['must_rate']} judge={row['before']['judge']['accuracy']} | "
                  f"after must={row['after']['must_rate']} judge={row['after']['judge']['accuracy']} "
                  f"route={row['after']['route']} {row['after']['elapsed_sec']}초", flush=True)

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = ROOT / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    used = sorted({s["judge"]["model"] for r in rows for s in (r["before"], r["after"]) if s["judge"]["model"]})
    meta = {"llm_backend": os.getenv("LLM_BACKEND", "ollama"), "judge": ", ".join(used) or "-", "time": stamp}
    (out / f"eval_{stamp}.json").write_text(json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    md = summary(rows, meta)
    (out / f"summary_{stamp}.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"저장: eval/results/eval_{stamp}.json, summary_{stamp}.md")


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(st.mean(vals), 2) if vals else "-"


def _pct(vals):
    vals = [v for v in vals if v is not None]
    return f"{round(100 * sum(vals) / len(vals))}%" if vals else "-"


def _pct_avg(vals):
    """질문별 비율(0~1)의 평균을 %로"""
    vals = [v for v in vals if v is not None]
    return f"{round(100 * st.mean(vals))}%" if vals else "-"


def summary(rows: list[dict], meta: dict) -> str:
    def agg(side, subset):
        r = [x[side] for x in subset]
        return {
            "필수 사실 포함률": _pct_avg([x["must_rate"] for x in r]),
            "정답 쪽 검색": _pct([x["page_hit"] for x in r]),
            "엉뚱한 정책 언급": f"{sum(bool(x['must_not_found']) for x in r)}건",
            "Judge 정확성": _avg([x["judge"]["accuracy"] for x in r]),
            "Judge 근거성": _avg([x["judge"]["grounded"] for x in r]),
            "Judge 유용성": _avg([x["judge"]["helpful"] for x in r]),
            "평균 시간(초)": _avg([x["elapsed_sec"] for x in r]),
            "평균 LLM 호출": _avg([x["llm_calls"] for x in r]),
        }
    lines = [f"# 평가 결과 ({meta['time']}, LLM={meta['llm_backend']}, 채점={meta['judge']})", "",
             f"질문 {len(rows)}개 (문서 {sum(r['type'] == 'doc' for r in rows)} · 정책 {sum(r['type'] == 'policy' for r in rows)} · "
             f"되묻기 {sum(r['type'] == 'clarify' for r in rows)})", "",
             "| 지표 | Before (단순 RAG) | After (멀티 에이전트) |", "|---|---|---|"]
    b, a = agg("before", rows), agg("after", rows)
    for k in b:
        lines.append(f"| {k} | {b[k]} | {a[k]} |")
    lines += ["", f"After 경로 정확도: {_pct([r['after']['route_ok'] for r in rows])}", "",
              "| ID | 질문 | Before 필수/Judge | After 필수/Judge | After 경로 | 감점 이유(After) |", "|---|---|---|---|---|---|"]
    for r in rows:
        bb, aa = r["before"], r["after"]
        lines.append(f"| {r['id']} | {r['question']} | {bb['must_rate']}/{bb['judge']['accuracy']} | "
                     f"{aa['must_rate']}/{aa['judge']['accuracy']} | {aa['route']} | {aa['judge']['reason'][:80]} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(main())
