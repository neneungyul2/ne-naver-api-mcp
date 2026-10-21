"""MCP 서버 조립과 실행 진입점."""
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from .cache import FileCache
from .client import NaverApiClient
from .config import (
    CredentialsError,
    load_dotenv_if_present,
    resolve_credentials,
    resolve_searchad_credentials,
)
from .searchad import SearchAdClient
from .tool_filter import ToolRegistrar, parse_tool_allow_list
from .tools import register_all_tools

SERVER_NAME = "ne-naver-api-mcp"


def create_server(
    client: NaverApiClient | None = None,
    *,
    allow: set[str] | None = None,
    cache: FileCache | None = None,
    searchad: SearchAdClient | None = None,
) -> MCPServer:
    """서버를 만들고 도구를 등록한다. 종료할 때 client(와 searchad)를 닫는다."""

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if client is not None:
                await client.aclose()
            if searchad is not None:
                await searchad.aclose()

    server = MCPServer(SERVER_NAME, lifespan=lifespan)
    registrar = ToolRegistrar(server, allow)
    register_all_tools(registrar, client, cache, searchad)
    registrar.warn_unknown()
    return server


def main() -> None:
    """stdio로 서버를 실행한다. stdout에는 MCP 프로토콜만 나가고 로그와 오류는 stderr로 간다."""
    # Windows 기본 인코딩(cp949 등)에서도 한글 오류 메시지가 깨지지 않게 stderr를 UTF-8로 고정한다
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv_if_present()
    try:
        credentials = resolve_credentials(os.environ)
    except CredentialsError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)
    try:
        searchad_credentials = resolve_searchad_credentials(os.environ)
    except CredentialsError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)
    allow = parse_tool_allow_list(os.environ.get("NAVER_TOOLS_ALLOW"))
    searchad = SearchAdClient(searchad_credentials) if searchad_credentials else None
    create_server(NaverApiClient(credentials), allow=allow, searchad=searchad).run()


if __name__ == "__main__":
    main()
