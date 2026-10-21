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


if __name__ == "__main__":
    mcp.run()                                  # 표준 입출력(stdio)으로 서버 실행