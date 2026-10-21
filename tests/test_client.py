import json

import httpx
import pytest

from ne_naver_api_mcp.client import ApiError, NaverApiClient
from ne_naver_api_mcp.config import Credentials

CREDS = Credentials("test-id", "test-secret")
BASE = "https://naverapihub.apigw.ntruss.com"


def make_client(handler) -> NaverApiClient:
    return NaverApiClient(CREDS, transport=httpx.MockTransport(handler))


def recorder(response: httpx.Response | None = None):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response or httpx.Response(200, json={"ok": True})

    return seen, handler


async def test_headers_carry_hub_auth_names_only():
    seen, handler = recorder()
    await make_client(handler).search("blog", {"query": "a"})
    headers = seen[0].headers
    assert headers["x-ncp-apigw-api-key-id"] == "test-id"
    assert headers["x-ncp-apigw-api-key"] == "test-secret"
    assert headers["content-type"] == "application/json"
    assert "x-naver-client-id" not in headers


async def test_search_uses_get_with_params_and_path():
    seen, handler = recorder()
    out = await make_client(handler).search(
        "blog", {"query": "그래머인사이드", "display": 3, "start": None, "sort": "date"}
    )
    req = seen[0]
    assert out == {"ok": True}
    assert req.method == "GET"
    assert req.url.path == "/search/v1/blog"
    assert req.url.params["query"] == "그래머인사이드"
    assert req.url.params["display"] == "3"
    assert req.url.params["sort"] == "date"
    assert "start" not in req.url.params  # None 값은 보내지 않는다


@pytest.mark.parametrize(
    "method, path",
    [
        ("search_trend", "/search-trend/v1/search"),
        ("shopping_category", "/shopping/v1/categories"),
        ("shopping_by_device", "/shopping/v1/category/device"),
        ("shopping_by_gender", "/shopping/v1/category/gender"),
        ("shopping_by_age", "/shopping/v1/category/age"),
        ("shopping_keywords", "/shopping/v1/category/keywords"),
        ("shopping_keyword_by_device", "/shopping/v1/category/keyword/device"),
        ("shopping_keyword_by_gender", "/shopping/v1/category/keyword/gender"),
        ("shopping_keyword_by_age", "/shopping/v1/category/keyword/age"),
    ],
)
async def test_trend_and_each_shopping_endpoint_path_and_method(method, path):
    seen, handler = recorder()
    body = {"startDate": "2025-01-01", "keyword": [{"name": "그래머", "param": ["그래머"]}]}
    out = await getattr(make_client(handler), method)(body)
    req = seen[0]
    assert out == {"ok": True}
    assert req.method == "POST"
    assert str(req.url) == f"{BASE}{path}"
    assert json.loads(req.content.decode("utf-8")) == body


@pytest.mark.parametrize("kind", ["news", "encyc", "webkr", "image", "kin", "cafearticle", "local"])
async def test_every_search_type_maps_to_its_path(kind):
    seen, handler = recorder()
    await make_client(handler).search(kind, {"query": "q"})
    assert seen[0].url.path == f"/search/v1/{kind}"


async def test_http_error_becomes_api_error_with_status_and_url():
    _, handler = recorder(httpx.Response(400, json={"errMsg": "bad request"}))
    with pytest.raises(ApiError) as e:
        await make_client(handler).search("blog", {"query": "a"})
    msg = str(e.value)
    assert "HTTP 400" in msg and f"{BASE}/search/v1/blog" in msg and "bad request" in msg


async def test_network_error_message_is_preserved():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused for test")

    with pytest.raises(ApiError) as e:
        await make_client(handler).search("blog", {"query": "a"})
    msg = str(e.value)
    assert "NAVER API HUB" in msg and "no response" in msg and "connection refused for test" in msg


async def test_timeout_message_names_the_cause():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out for test")

    with pytest.raises(ApiError, match="read timed out for test"):
        await make_client(handler).search_trend({})


async def test_error_message_does_not_contain_credentials():
    _, handler = recorder(httpx.Response(401, json={"message": "unauthorized"}))
    with pytest.raises(ApiError) as e:
        await make_client(handler).search("blog", {"query": "a"})
    msg = str(e.value)
    assert "test-id" not in msg and "test-secret" not in msg
    assert "NCP_APIGW_API_KEY_ID" in msg  # 401 안내


async def test_non_json_success_body_is_an_api_error():
    _, handler = recorder(httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(ApiError, match="not json"):
        await make_client(handler).search("blog", {"query": "a"})


async def test_aclose_can_be_called_twice():
    client = make_client(lambda request: httpx.Response(200, json={}))
    await client.aclose()
    await client.aclose()
