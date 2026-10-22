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
def resolve_region(text: str) -> dict:
    """사용자가 말한 지역('전주', '서울 강남구', '경기 광주시' 등)을 시도·시군구로 해석한다.
    find_policies를 부르기 전에 지역을 제대로 알아들었는지 확인할 때 쓴다.
    인식 못 하면 {"인식": false}."""
    loc = tools.resolve_region(text)
    if loc is None:
        return {"인식": False, "입력": text}
    return {"인식": True, "입력": text, "지역": loc["지역"], "단위": loc["단위"], "코드수": len(loc["codes"])}


@mcp.tool()
def find_policies(age: int | None = None, region: str | None = None,
                  keyword: str | None = None, only_open: bool = True,
                  limit: int = 5, age_upper: int | None = None) -> dict:
    """온통청년 청년정책 3,472개(2026-10-21 기준)에서 조건에 맞는 정책을 찾아 정렬해 돌려준다.
    age: 만 나이(생년만 알면 age=최소, age_upper=최대로 범위를 준다)
    region: '서울', '전주', '경기 수원'처럼 지역 이름. 그 지역 대상 정책 + 전국 정책을 섞어서 준다.
            인식할 수 없는 지역이면 오류가 난다(먼저 resolve_region으로 확인할 것).
    keyword: '취업', '주거', '월세'처럼 정책명·키워드·분야에 들어 있는 낱말
    only_open: True면 마감된 정책 제외
    돌려주는 값: {"조건": 해석된 조건, "총개수": 조건에 맞는 전체 수, "정책": 상위 limit개}"""
    return tools.find_policies(age, region, keyword, only_open, limit, age_upper)


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
1. 사실에 없는 정책·금액·조건은 지어내지 않는다. 질문의 핵심을 사실로 답할 수 없을 때만 "안내 자료에서 찾지 못했어요"라고 말한다.
2. [조건에 맞는 신청 가능 정책]에 정책이 있으면 질문과 관련 있는 것을 모두 소개한다(안내 자료의 제도가 마감이어도 대안으로 꼭 보여준다).
   정책마다 이름, 대상, 지원 내용, 신청 방법을 짧게 정리한다. 각 정책의 대상·금액·조건은 그 정책 줄에 적힌 것만 쓰고,
   다른 정책이나 안내 자료의 기준을 옮겨 쓰지 않는다. 사용자 상황(나이 등)과 맞지 않는 정책(예: 신혼부부 전용)은 빼거나 그렇다고 밝힌다.
   정책 목록은 나이·지역으로 고른 후보일 뿐이다. "신청 가능한 정책은 이것뿐"처럼 말하지 말고, 소득·무주택 등 다른 조건은 확인이 필요하다고 알린다.
3. 신청 상태는 [조건에 맞는 신청 가능 정책]에 적힌 '신청상태'만 쓴다. 신청상태가 '마감'이면 "올해 모집은 끝났어요"라고 표시한다.
   [안내 자료 발췌]의 신청 기간은 날짜를 직접 계산하지 말고 발췌 아래 [기간 확인]을 그대로 따른다.
   '이미 지났음'인 신청 기간은 기간과 함께 "올해 모집은 끝났어요"라고 꼭 쓰고, '진행 중'이면 지금 신청할 수 있다고,
   '아직 시작 전'이면 기간만 알려준다. 신청 기간에 [기간 확인]이 없으면 신청 상태를 말하지 않는다.
4. 자격은 사용자가 질문에 직접 밝힌 정보(나이·지역 등)로만 가늠하고, 단정하지 말고 "해당될 가능성이 높아요"처럼 말한다.
   사용자가 밝힌 정보가 없으면 해당 여부를 말하지 않고, 확인에 필요한 정보(나이, 사는 곳 등)를 알려 달라고 한다.
5. 소득·재산 조건은 기준만 알려주고, 해당 여부는 판단하지 않는다.
6. 답변 본문에는 문서명·쪽수 같은 출처를 쓰지 않는다(출처 목록은 화면에 따로 표시된다).
   마지막에 최종 확인은 복지로·고용24·온통청년에서 하라고 안내한다.
7. 발췌의 '적용 지역'이 전국이 아니면 "전주시 공고 기준"처럼 어느 지역 공고인지 밝히고, 지역마다 기준이 다를 수 있다고 알린다.
8. 강조는 **굵게**만 쓰고, 표나 # 제목은 쓰지 않는다.
9. 질문한 기준이 발췌에 여러 갈래로 나오면(예: 청년가구·원가구) 하나만 쓰지 말고 모두 쓴다.

[질문]
{question}

[수집한 사실]
{facts}"""


if __name__ == "__main__":
    mcp.run(show_banner=False)                 # 표준 입출력(stdio)으로 서버 실행 (배너 끔)