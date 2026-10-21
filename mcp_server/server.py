import json

from fastmcp import FastMCP

import tools                                   # 4-B에서 만든 순수 함수들

mcp = FastMCP("youth-policy")


@mcp.tool()
def get_today() -> str:
    """오늘 날짜를 YYYY-MM-DD로 알려준다. 신청 기간이 지났는지 판단할 때 쓴다."""
    return tools.get_today().isoformat()


@mcp.tool()
def calc_age(birth_year: int, birth_month: int = 0, birth_day: int = 0) -> dict:
    """출생 연도(필수)와 월·일(모르면 0)로 오늘 기준 만 나이를 계산한다.
    월·일을 모르면 만 나이 최소·최대 범위를 돌려준다."""
    return tools.calc_age(birth_year, birth_month, birth_day)


@mcp.tool()
def find_policies(age: int | None = None, region: str | None = None,
                  keyword: str | None = None, only_open: bool = True,
                  limit: int = 5) -> list[dict]:
    """온통청년 청년정책 3,472개(2026-10-21 기준)에서 조건에 맞는 정책을 찾는다.
    age: 만 나이 / region: '서울', '전주'처럼 지역명 일부(전국 정책은 항상 포함)
    keyword: '취업', '주거', '월세' 같은 키워드 / only_open: True면 마감된 정책 제외"""
    return tools.find_policies(age, region, keyword, only_open, limit)


@mcp.resource("policy://catalog", mime_type="application/json")
def policy_catalog() -> str:
    """정책 데이터 안내: 기준일, 전체 정책 수, 분야 목록, 신청상태별 개수.
    find_policies의 keyword를 고를 때 분야 목록을 참고한다."""
    # dict를 그대로 돌려주면 한글이 \\uXXXX로 바뀌어 전송된다 → 직접 JSON 문자열로 만들어 한글 유지
    return json.dumps(tools.catalog(), ensure_ascii=False)


@mcp.prompt()
def policy_answer_prompt(question: str, facts: str) -> str:
    """수집한 사실로 청년정책 안내 답변을 쓸 때 쓰는 규칙 틀"""
    return f"""너는 청년정책 안내 도우미다. 아래 [수집한 사실]만 근거로 한국어로 답하라.

[답변 규칙]
1. 사실에 없는 정책·금액·조건은 지어내지 말고 "안내 자료에서 찾지 못했어요"라고 말한다.
2. 정책마다 이름, 대상, 지원 내용, 신청 방법을 짧게 정리한다.
3. 신청상태가 '마감'이면 반드시 "올해 모집은 끝났어요"라고 표시한다.
4. 자격은 단정하지 말고 "해당될 가능성이 높아요"처럼 말한다.
5. 소득·재산 조건은 기준만 알려주고, 해당 여부는 판단하지 않는다.
6. 끝에 참고한 출처(문서명 쪽수 또는 정책명)를 적고, 최종 확인은 복지로·고용24·온통청년에서 하라고 안내한다.

[질문]
{question}

[수집한 사실]
{facts}"""


if __name__ == "__main__":
    mcp.run()                                  # 표준 입출력(stdio)으로 서버 실행