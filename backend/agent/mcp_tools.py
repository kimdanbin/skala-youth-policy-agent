"""MCP 서버(mcp_server/server.py) 연결 도우미.

- 서버는 별도 프로그램으로 한 번만 띄우고 연결을 재사용한다(요청마다 띄우면 느리다).
- 환경변수(FAKE_TODAY 등)를 서버 프로세스에 명시적으로 넘긴다.
  (확인 결과: 넘기지 않으면 서버가 부모의 FAKE_TODAY를 못 봐서 날짜 고정이 안 됐다)
- 같은 연결을 동시에 쓰면 꼬일 수 있어 잠금(lock)을 건다.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from fastmcp.exceptions import ToolError

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "mcp_server" / "server.py"     # 절대 경로: 어느 폴더에서 실행해도 찾는다
LOG = ROOT / "logs" / "mcp_server.log"         # 서버 로그는 파일로 (터미널이 지저분해지지 않게)


class McpError(RuntimeError):
    """MCP 도구가 오류를 돌려줬을 때 (예: 모르는 지역)."""


class McpTools:
    def __init__(self, server: Path = SERVER):
        LOG.parent.mkdir(exist_ok=True)
        transport = PythonStdioTransport(server, env=dict(os.environ),
                                         python_cmd=sys.executable, log_file=LOG)
        self._client = Client(transport)
        self._lock = asyncio.Lock()
        self._catalog = None

    async def __aenter__(self):
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self._client.__aexit__(*exc)

    async def call_tool(self, name: str, args: dict):
        async with self._lock:
            try:
                result = await self._client.call_tool(name, args)
            except ToolError as e:
                raise McpError(str(e)) from e
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:          # get_today처럼 글자 하나를 돌려주는 도구
            return text

    async def read_catalog(self) -> dict:
        if self._catalog is None:             # 바뀌지 않는 자료라 한 번만 읽는다
            async with self._lock:
                contents = await self._client.read_resource("policy://catalog")
            self._catalog = json.loads(contents[0].text)
        return self._catalog

    async def get_answer_prompt(self, question: str, facts: str) -> str:
        async with self._lock:
            prompt = await self._client.get_prompt("policy_answer_prompt",
                                                   {"question": question, "facts": facts})
        return prompt.messages[0].content.text
