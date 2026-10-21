import io
from contextlib import redirect_stderr

from mcp import Client
from mcp.server.mcpserver import MCPServer

from ne_naver_api_mcp.tool_filter import ToolRegistrar, parse_tool_allow_list


def test_parse_allow_list_empty_means_everything():
    assert parse_tool_allow_list(None) is None
    assert parse_tool_allow_list("") is None
    assert parse_tool_allow_list("  , ") is None


def test_parse_allow_list_splits_on_commas_and_trims():
    assert parse_tool_allow_list(" search_blog , brand_mentions ") == {"search_blog", "brand_mentions"}


class FakeServer:
    def __init__(self):
        self.added: list[tuple[str, str]] = []

    def add_tool(self, fn, name=None, description=None, **kwargs):
        self.added.append((name, description))


def a():
    return "a"


def test_registrar_registers_only_allowed_tools():
    server = FakeServer()
    r = ToolRegistrar(server, {"a", "c"})
    for name in ("a", "b", "c"):
        r.register(name, a, f"{name} 설명")
    assert [n for n, _ in server.added] == ["a", "c"]
    assert server.added[0][1] == "a 설명"


def test_registrar_registers_everything_when_allow_is_none():
    server = FakeServer()
    r = ToolRegistrar(server, None)
    r.register("a", a, "x")
    r.register("b", a, "y")
    assert [n for n, _ in server.added] == ["a", "b"]


def test_warn_unknown_names_go_to_stderr():
    server = FakeServer()
    r = ToolRegistrar(server, {"search_blog", "serch_blog"})  # 오타
    r.register("search_blog", a, "x")
    buf = io.StringIO()
    with redirect_stderr(buf):
        r.warn_unknown()
    assert "serch_blog" in buf.getvalue()
    assert "search_blog" not in buf.getvalue().replace("serch_blog", "")


def test_warn_unknown_is_silent_when_everything_matches_or_no_filter():
    server = FakeServer()
    r = ToolRegistrar(server, {"a"})
    r.register("a", a, "x")
    buf = io.StringIO()
    with redirect_stderr(buf):
        r.warn_unknown()
        ToolRegistrar(server, None).warn_unknown()
    assert buf.getvalue() == ""


async def test_filtered_tools_are_really_hidden_from_an_mcp_client():
    server = MCPServer("t")
    r = ToolRegistrar(server, {"a"})

    def b() -> str:
        return "b"

    def a_tool() -> str:
        return "a"

    r.register("a", a_tool, "A 도구")
    r.register("b", b, "B 도구")
    async with Client(server) as client:
        names = [t.name for t in (await client.list_tools()).tools]
    assert names == ["a"]


async def test_surface_errors_turns_expected_failures_into_tool_errors_and_names_unexpected_ones_too():
    import inspect

    import pytest
    from mcp.server.mcpserver.exceptions import ToolError

    from ne_naver_api_mcp.analysis.budget import BudgetExceededError
    from ne_naver_api_mcp.analysis.rescale import AnchorError
    from ne_naver_api_mcp.client import ApiError
    from ne_naver_api_mcp.tool_filter import surface_errors

    async def sample(query: str, display: int = 3) -> str:
        raise exc

    wrapped = surface_errors(sample)
    assert list(inspect.signature(wrapped).parameters) == ["query", "display"]  # 스키마용 시그니처 유지
    for exc in (ApiError("HTTP 400 boom"), ValueError("bad"), BudgetExceededError(40, 30), AnchorError("anchor")):
        with pytest.raises(ToolError) as e:
            await wrapped("q")
        assert str(exc) in str(e.value)
    exc = RuntimeError("bug")  # 예상 밖 오류도 이유(타입과 메시지)가 클라이언트에 보여야 한다
    with pytest.raises(ToolError, match="RuntimeError.*bug"):
        await wrapped("q")
