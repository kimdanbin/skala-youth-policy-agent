"""에이전트 공용 메모장(State)과 LLM 출력 모양(Plan, Grade), 횟수 제한 상수.

노드끼리 주고받는 데이터의 '약속'을 여기 한 곳에 모아 둔다. 다른 파일은 전부 이 모양을 따른다.
"""
import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

# 무한 반복 방지: 재계획·재검색 횟수 제한 (+ graph.py의 recursion_limit 으로 3중 방어)
MAX_REPLAN = 1        # Supervisor 재계획 최대 횟수 (서브에이전트가 각자 재시도하므로 1번이면 충분)
MAX_DOC_RETRY = 2     # 문서검색 에이전트의 재검색 최대 횟수 (첫 검색 + 2번 = 최대 3번 검색)
MAX_DOC_RETRY_BOTH = 1  # 정책조회와 함께 돌 때(both)는 문서가 보조 자료라 1번까지만 (실측 근거: docs/PLAN.md)
POLICY_LIMIT = 5      # 답변에 넣을 정책 수
DOC_K = 4             # 한 번에 가져올 문서 조각 수

# ingest.py가 파일명(연도_사업명_발행기관)에서 만든 program 값과 정확히 같아야 한다 (벡터 DB에서 확인함)
DOC_PROGRAMS = ("청년정책집", "청년월세", "청년내일저축계좌")
Route = Literal["chat", "clarify", "policy", "doc", "both"]


class Plan(BaseModel):
    """Supervisor가 질문을 분석해 만드는 계획. LLM이 이 모양(JSON)으로 답하게 강제한다."""
    route: Route = Field(description=(
        "chat=인사·잡담·범위 밖 질문 / clarify=개인 자격을 묻는데 나이나 지역 정보가 없음 / "
        "policy=조건에 맞는 정책 목록이 필요 / doc=특정 제도의 세부 규정·서류·기준 설명이 필요 / "
        "both=정책 목록과 세부 설명이 둘 다 필요"))
    birth_year: int | None = Field(None, description="질문에 나온 출생 연도(예: 2002). 없으면 null")
    birth_month: int | None = Field(None, description="출생 월. 없으면 null")
    birth_day: int | None = Field(None, description="출생 일. 없으면 null")
    age: int | None = Field(None, description="질문에 '24살', '만 25세'처럼 나이가 직접 나오면 그 숫자. 없으면 null")
    region: str | None = Field(None, description="사는 지역. '전북 전주', '서울', '경기 수원'처럼 시도와 시군구. 없으면 null")
    keyword: str | None = Field(None, description="정책을 찾을 핵심 낱말 하나(예: 취업, 주거, 월세, 창업, 학자금). 없으면 null")
    category: str | None = Field(None, description="분야 목록 중 질문에 가장 가까운 분야 하나. 없으면 null")
    doc_query: str | None = Field(None, description="문서에서 찾을 검색 문장(예: '청년월세 자격요건 소득 재산 기준')")
    doc_program: str | None = Field(None, description="문서를 좁힐 사업명: 청년정책집, 청년월세, 청년내일저축계좌 중 하나 또는 null")
    reason: str = Field("", description="이렇게 계획한 이유 한 문장")


class Grade(BaseModel):
    """문서검색 에이전트가 찾은 조각을 LLM이 채점한 결과."""
    enough: bool = Field(description="조각들만으로 질문에 정확히 답할 수 있으면 true")
    reason: str = Field("", description="그렇게 판단한 이유 한 문장")
    better_query: str | None = Field(None, description="부족하면, 다시 찾을 더 구체적인 검색 문장")


class AgentState(TypedDict, total=False):
    question: str
    plan: dict                      # Plan.model_dump()
    plan_source: str                # "llm" | "fallback" (LLM이 모양을 못 지켜서 규칙으로 만든 계획)
    age: dict | None                # {"min": 23, "max": 24, "text": "만 23~24세"}
    region_info: dict | None        # resolve_region 결과
    policy_result: dict | None      # 정책조회 에이전트 결과
    doc_result: dict | None         # 문서검색 에이전트 결과
    replan_count: int
    next_agents: list[str]          # 검토 후 다시 실행할 서브에이전트 (재계획 결과)
    answer: str
    sources: list[str]
    # 아래 세 개는 정책조회·문서검색이 '동시에' 실행될 때 둘 다 값을 추가한다.
    # 덮어쓰기가 아니라 이어 붙이기(operator.add)로 해야 한쪽 기록이 사라지지 않는다.
    path: Annotated[list[str], operator.add]
    llm_calls: Annotated[int, operator.add]
    notes: Annotated[list[str], operator.add]
