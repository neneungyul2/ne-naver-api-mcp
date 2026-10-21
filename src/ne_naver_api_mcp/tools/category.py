"""find_category 도구."""
import json
from typing import Annotated

from pydantic import Field

from ..categories import find_category
from ..tool_filter import ToolRegistrar
from .descriptions import DESCRIPTIONS


def register_category_tools(registrar: ToolRegistrar) -> None:
    async def find_category_tool(
        query: Annotated[
            str,
            Field(
                description="Korean category search query (한국어 카테고리 검색어, 예: '패션', '화장품', "
                "'가구', '스마트폰'). Supports exact match and fuzzy search with level-based priority"
            ),
        ],
        max_results: Annotated[
            int, Field(description="Maximum number of results to return (반환할 최대 결과 수, 기본값: 10)")
        ] = 10,
    ) -> str:
        return json.dumps(find_category(query, max_results), ensure_ascii=False, indent=2)

    find_category_tool.__name__ = "find_category"
    registrar.register("find_category", find_category_tool, DESCRIPTIONS["find_category"])
