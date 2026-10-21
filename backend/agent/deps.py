"""의존성 묶음(Deps). 노드들은 LLM·MCP·검색기를 직접 만들지 않고 여기서 받아 쓴다.

진짜 부품(build_real_deps)과 가짜 부품(테스트)을 갈아 끼울 수 있어서,
Ollama·벡터 DB 없이도 그래프 흐름을 1초 만에 테스트할 수 있다.
진짜 부품은 함수 안에서 import 한다(lazy import): 테스트가 벡터 DB를 찾지 않게 하려는 것.
"""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Deps:
    llm: Any                 # .with_structured_output(모양).ainvoke(...) / .ainvoke(...) 를 지원하는 LLM
    mcp: Any                 # McpTools: call_tool / read_catalog / get_answer_prompt
    search: Callable         # search(query, k, program) -> [(Document, distance), ...]  (동기 함수)


def build_real_deps(mcp) -> Deps:
    from llm import get_llm                 # backend/llm.py
    from rag.retriever import search        # 여기서 처음 벡터 DB를 연다 (없으면 바로 오류로 알려줌)
    return Deps(llm=get_llm(), mcp=mcp, search=search)
