"""에이전트를 실제 부품(Ollama·벡터 DB·MCP 서버)으로 돌려보는 스크립트.

실행 (프로젝트 최상위 폴더에서, Ollama 켜진 상태):
    python scripts/try_agent.py                  # 시나리오 6개
    python scripts/try_agent.py "질문 하나"       # 원하는 질문
결과는 화면에 출력하고 logs/try_agent_시각.json 에도 저장한다 (보고서·평가 자료용).
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv   # noqa: E402

load_dotenv(ROOT / ".env")        # LLM_BACKEND, OPENAI_API_KEY, LANGSMITH_* (서버와 같은 설정으로 실행)

from agent.deps import build_real_deps   # noqa: E402
from agent.graph import build_graph, run   # noqa: E402
from agent.mcp_tools import McpTools   # noqa: E402

SCENARIOS = [
    "2002년생 서울 사는데 지금 신청할 수 있는 취업 지원 있어?",   # 정책조회
    "청년월세 받으려면 소득 기준이 어떻게 돼?",                   # 문서검색 (3-B 실패 질문)
    "2002년생 전주 사는데 월세 지원 받을 수 있어?",               # 둘 다 + 마감 안내
    "나 받을 수 있는 거 있어?",                                   # 되묻기
    "안녕, 넌 뭐 할 수 있어?",                                    # 바로 답변
    "국민내일배움카드로 뭘 배울 수 있어?",                         # 문서검색
]


async def main(questions):
    results = []
    async with McpTools() as mcp:                      # MCP 서버는 한 번만 띄워서 재사용
        graph = build_graph(build_real_deps(mcp))
        for i, q in enumerate(questions, 1):
            r = await run(graph, q)
            results.append(r)
            print(f"\n{'=' * 80}\n[{i}] {q}")
            print(f"경로: {' → '.join(r['path'])}")
            print(f"LLM 호출: {r['llm_calls']}회 | 시간: {r['elapsed_sec']}초 | 계획: {r['plan_source']}")
            if r["plan"]:
                p = r["plan"]
                print(f"계획: route={p['route']} 출생={p['birth_year']} 나이={p['age']} 지역={p['region']} "
                      f"키워드={p['keyword']} 분야={p['category']} 문서={p['doc_program']} 검색어={p['doc_query']}")
            print(f"나이: {(r['age'] or {}).get('text')} | 지역: {(r['region'] or {}).get('지역')} | "
                  f"정책 {r['policy_total']}개 | 문서 쪽 {r['doc_pages']} 충분={r['doc_enough']}")
            for n in r["notes"]:
                print(f"  · {n}")
            if r["error"]:
                print(f"!! 오류: {r['error']}")
            print(f"--- 답변 ---\n{r['answer']}\n--- 출처: {r['sources']}")
    out = ROOT / "logs" / f"try_agent_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {out}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or SCENARIOS))
