"""Task 1: 서버를 실제 자식 프로세스(stdio)로 띄워 MCP 클라이언트로 연결한다."""
import os
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters


def server_params(env: dict[str, str] | None = None, cwd: str | None = None) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-c", "from ne_naver_api_mcp.server import main; main()"],
        # 서버는 작업 폴더의 .env를 읽는다: 개발자의 .env(검색광고 키 등)가 결과를 바꾸지 않게 빈 폴더에서 띄운다
        cwd=cwd,
        # 서버는 키가 없으면 시작하지 않으므로 더미 키를 넣는다 (실제 호출은 하지 않는다)
        env={
            **os.environ,
            "NCP_APIGW_API_KEY_ID": "dummyid",
            "NCP_APIGW_API_KEY": "dummysecret",
            **(env or {}),
        },
    )


async def test_stdio_server_initializes_and_lists_tools(tmp_path):
    async with Client(server_params(cwd=str(tmp_path))) as client:
        assert client.server_info.name == "ne-naver-api-mcp"
        result = await client.list_tools()
        assert len(result.tools) == 20
