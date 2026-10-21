import asyncio
from pathlib import Path

from fastmcp import Client


async def main():
    async with Client(Path("mcp_server/server.py")) as client:     # 서버를 띄우고 연결
        tools = await client.list_tools()                     # ① 어떤 도구 있어?
        print("도구 목록:", [t.name for t in tools])

        result = await client.call_tool("calc_age", {"birth_year": 2002})   # ② 호출
        print("calc_age:", result.content[0].text)

        result = await client.call_tool("find_policies",
                                        {"age": 24, "region": "서울", "keyword": "취업", "limit": 2})
        print("find_policies:", result.content[0].text[:300])

        resources = await client.list_resources()                       # ③ 자료 목록
        print("자료 목록:", [str(r.uri) for r in resources])
        catalog = await client.read_resource("policy://catalog")        # ④ 자료 읽기
        print("catalog:", catalog[0].text[:300])

        prompts = await client.list_prompts()                           # ⑤ 프롬프트 목록
        print("프롬프트 목록:", [p.name for p in prompts])
        prompt = await client.get_prompt("policy_answer_prompt",        # ⑥ 틀 채우기
                                         {"question": "월세 지원 있어?", "facts": "(테스트)"})
        print("prompt:", prompt.messages[0].content.text[:200])


asyncio.run(main())