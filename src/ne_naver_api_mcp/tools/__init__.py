"""도구 등록 모듈 모음. 각 모듈이 register_*_tools(registrar, ...)를 제공한다."""
from ..cache import FileCache
from ..client import NaverApiClient
from ..tool_filter import ToolRegistrar
from .analysis import register_analysis_tools
from .category import register_category_tools
from .datalab import register_datalab_tools
from .search import register_search_tools


def register_all_tools(
    registrar: ToolRegistrar, client: NaverApiClient | None, cache: FileCache | None = None
) -> None:
    """원본 18개(검색 8, 데이터랩 9, 카테고리 1) + 분석 2개를 등록한다.

    client가 None이면(테스트용) 등록만 하고, 호출 시점에 클라이언트가 필요하다.
    """
    register_search_tools(registrar, client)
    register_datalab_tools(registrar, client)
    register_category_tools(registrar)
    register_analysis_tools(registrar, client, cache)
