"""도구 테스트용 가짜 API/서버 모음."""
from ne_naver_api_mcp.analysis.tokenizer import regex_tokenizer
from ne_naver_api_mcp.cache import FileCache
from ne_naver_api_mcp.tool_filter import ToolRegistrar

RESPONSE = {"ok": True, "한글": "값"}


class RecordingClient:
    """호출을 기록하고 고정 응답을 돌려주는 NaverApiClient 대역."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail: Exception | None = None

    def _record(self, *call):
        if self.fail:
            raise self.fail
        self.calls.append(call)
        return dict(RESPONSE)

    async def aclose(self) -> None:
        pass

    async def search(self, type, params):  # noqa: A002
        return self._record("search", type, params)

    async def search_trend(self, req):
        return self._record("search_trend", req)

    async def shopping_category(self, req):
        return self._record("shopping_category", req)

    async def shopping_by_device(self, req):
        return self._record("shopping_by_device", req)

    async def shopping_by_gender(self, req):
        return self._record("shopping_by_gender", req)

    async def shopping_by_age(self, req):
        return self._record("shopping_by_age", req)

    async def shopping_keywords(self, req):
        return self._record("shopping_keywords", req)

    async def shopping_keyword_by_device(self, req):
        return self._record("shopping_keyword_by_device", req)

    async def shopping_keyword_by_gender(self, req):
        return self._record("shopping_keyword_by_gender", req)

    async def shopping_keyword_by_age(self, req):
        return self._record("shopping_keyword_by_age", req)


class CaptureServer:
    """add_tool로 등록된 함수를 모아 직접 호출할 수 있게 한다."""

    def __init__(self) -> None:
        self.tools: dict = {}
        self.descriptions: dict = {}

    def add_tool(self, fn, name=None, description=None, **kwargs):
        self.tools[name] = fn
        self.descriptions[name] = description


def capture_registrar(allow=None) -> tuple[ToolRegistrar, CaptureServer]:
    server = CaptureServer()
    return ToolRegistrar(server, allow), server


def regex_factory(brands):
    """빠르고 결정적인 테스트를 위해 정규식 토크나이저를 쓰는 팩토리."""
    return regex_tokenizer


def make_cache(tmp_path) -> FileCache:
    return FileCache(tmp_path / "cache", ttl_ms=10**9)
