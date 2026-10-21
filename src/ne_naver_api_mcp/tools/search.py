"""검색 도구 8개 (웹문서, 뉴스, 블로그, 카페글, 이미지, 지식iN, 백과, 지역)."""
import json
from typing import Annotated, Literal

from pydantic import Field

from ..client import NaverApiClient
from ..endpoints import UNVERIFIED_OR_INVALID
from ..tool_filter import ToolRegistrar
from .descriptions import DESCRIPTIONS

SEARCH_TOOLS = {
    "search_webkr": "webkr",
    "search_news": "news",
    "search_blog": "blog",
    "search_cafearticle": "cafearticle",
    "search_image": "image",
    "search_kin": "kin",
    "search_encyc": "encyc",
    "search_local": "local",
}

Query = Annotated[str, Field(description="검색어")]
Display = Annotated[int | None, Field(description="한 번에 가져올 결과 수 (기본 10)")]
Start = Annotated[int | None, Field(description="검색 시작 위치 (기본 1)")]
Sort = Annotated[
    Literal["sim", "date"] | None, Field(description="정렬 방식 (sim: 유사도, date: 날짜순)")
]
LocalDisplay = Annotated[int | None, Field(description="한 번에 가져올 결과 수 (최대 5)")]
LocalStart = Annotated[int | None, Field(description="검색 시작 위치 (최대 1)")]
LocalSort = Annotated[
    Literal["random", "comment"] | None,
    Field(description="정렬 방식 (random: 정확도순, comment: 리뷰 많은순)"),
]


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _standard_handler(client: NaverApiClient, kind: str):
    async def handler(
        query: Query, display: Display = None, start: Start = None, sort: Sort = None
    ) -> str:
        return _dump(
            await client.search(kind, {"query": query, "display": display, "start": start, "sort": sort})
        )

    return handler


def _local_handler(client: NaverApiClient):
    async def handler(
        query: Query,
        display: LocalDisplay = None,
        start: LocalStart = None,
        sort: LocalSort = None,
    ) -> str:
        return _dump(
            await client.search("local", {"query": query, "display": display, "start": start, "sort": sort})
        )

    return handler


def register_search_tools(registrar: ToolRegistrar, client: NaverApiClient | None) -> None:
    for tool_name, kind in SEARCH_TOOLS.items():
        if kind in UNVERIFIED_OR_INVALID:
            continue  # 실제 확인에서 HUB에 없는 타입은 등록하지 않는다
        handler = _local_handler(client) if kind == "local" else _standard_handler(client, kind)
        handler.__name__ = tool_name
        registrar.register(tool_name, handler, DESCRIPTIONS[tool_name])
