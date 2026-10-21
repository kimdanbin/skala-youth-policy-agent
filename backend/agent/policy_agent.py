"""② 정책조회 서브에이전트 — MCP Tool(calc_age, find_policies)로 조건에 맞는 정책을 찾는다.

계획(Plan)은 LLM이 세우고, 여기서는 코드가 그 계획대로 도구를 정확히 부른다.
결과가 0개면 스스로 조건을 넓혀 다시 찾는다: 키워드 → 분야 → (키워드 없이).
지역은 넓히지 않는다: 다른 지역 정책은 사용자가 받을 수 없어서 넓혀 봐야 의미가 없다.
"""
from .mcp_tools import McpError
from .state import POLICY_LIMIT, AgentState


async def resolve_age(deps, plan: dict) -> dict | None:
    if plan.get("age") is not None:
        a = plan["age"]
        return {"min": a, "max": a, "text": f"만 {a}세"}
    if plan.get("birth_year") is None:
        return None
    r = await deps.mcp.call_tool("calc_age", {"birth_year": plan["birth_year"],
                                              "birth_month": plan.get("birth_month") or 0,
                                              "birth_day": plan.get("birth_day") or 0})
    if "만나이" in r:
        return {"min": r["만나이"], "max": r["만나이"], "text": f"만 {r['만나이']}세"}
    return {"min": r["만나이_최소"], "max": r["만나이_최대"],
            "text": f"만 {r['만나이_최소']}~{r['만나이_최대']}세(생일 전이면 {r['만나이_최소']}세)"}


async def policy_node(state: AgentState, deps) -> dict:
    plan = state["plan"]
    age = await resolve_age(deps, plan)
    region = plan.get("region")
    base = {"region": region, "only_open": True, "limit": POLICY_LIMIT}
    if age:
        base.update(age=age["min"], age_upper=age["max"])

    tries = []
    for kw in (plan.get("keyword"), plan.get("category")):
        if kw and kw not in tries:
            tries.append(kw)
    tries.append(None)          # 키워드 없이 찾는 건 마지막 수단
    attempts, result = [], None
    for kw in tries:
        try:
            result = await deps.mcp.call_tool("find_policies", {**base, "keyword": kw})
        except McpError as e:      # 예: 지역을 못 알아들음 → 지역 없이 한 번 더
            attempts.append({"키워드": kw, "오류": str(e)})
            base["region"] = None
            result = await deps.mcp.call_tool("find_policies", {**base, "keyword": kw})
        attempts.append({"키워드": kw, "총개수": result["총개수"]})
        if result["총개수"] > 0:
            break

    # 이름에 키워드가 들어간 '마감된' 정책도 따로 알려준다 ("올해 모집은 끝났어요" 안내용).
    # 예: 전주 청년월세는 5월에 마감 → 신청 가능 목록에는 없지만, 사용자가 찾는 바로 그 정책이다.
    closed = []
    if tries[0] is not None:
        c = await deps.mcp.call_tool("find_policies", {**base, "keyword": tries[0],
                                                       "only_open": False, "limit": 20})
        closed = [x for x in c["정책"] if x["신청상태"] == "마감" and tries[0] in x["정책명"]][:3]

    notes = []
    if len(attempts) > 1:
        notes.append("정책 조회 조건 넓힘: " + " → ".join(str(a.get("키워드")) for a in attempts))
    return {"age": age,
            "policy_result": {**result, "마감된_관련정책": closed, "시도": attempts},
            "path": ["policy_agent"], "llm_calls": 0, "notes": notes}
