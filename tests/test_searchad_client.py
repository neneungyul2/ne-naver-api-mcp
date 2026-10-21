import base64
import hashlib
import hmac

import httpx
import pytest

from ne_naver_api_mcp.client import ApiError
from ne_naver_api_mcp.config import (
    CredentialsError,
    SearchAdCredentials,
    resolve_searchad_credentials,
)
from ne_naver_api_mcp.searchad import SearchAdClient, normalize_hint, sign

CUSTOMER, LICENSE, SECRET = "1234567", "LICENSE-abc", "SECRET-xyz"
CREDS = SearchAdCredentials(CUSTOMER, LICENSE, SECRET)
NAMES = ("NAVER_SEARCHAD_CUSTOMER_ID", "NAVER_SEARCHAD_ACCESS_LICENSE", "NAVER_SEARCHAD_SECRET_KEY")


def make(handler, **kw):
    return SearchAdClient(
        CREDS, transport=httpx.MockTransport(handler), clock=lambda: 1_700_000_000.123, retry_delays=(0, 0), **kw
    )


def test_sign_is_base64_hmac_sha256_of_timestamp_method_uri():
    expected = base64.b64encode(
        hmac.new(b"secret", b"1700000000123.GET./keywordstool", hashlib.sha256).digest()
    ).decode()
    assert sign("1700000000123", "GET", "/keywordstool", "secret") == expected


def test_normalize_hint_removes_all_spaces():
    assert normalize_hint(" 그래머 인사이드 ") == "그래머인사이드"


async def test_request_headers_and_signature_exclude_query():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"keywordList": []})

    client = make(handler)
    await client.keyword_tool(["그래머 인사이드", "ABC"])
    h = seen["headers"]
    assert h["x-api-key"] == LICENSE and h["x-customer"] == CUSTOMER
    assert h["x-timestamp"] == "1700000000123"
    # 서명 대상은 쿼리스트링을 뺀 경로다
    assert h["x-signature"] == sign("1700000000123", "GET", "/keywordstool", SECRET)
    assert "hintKeywords=%EA%B7%B8%EB%9E%98%EB%A8%B8%EC%9D%B8%EC%82%AC%EC%9D%B4%EB%93%9C%2CABC" in seen["url"]
    assert "showDetail=1" in seen["url"]
    assert SECRET not in seen["url"]
    await client.aclose()


async def test_retries_on_429_then_succeeds_with_fresh_signature():
    sigs = []

    def handler(request):
        sigs.append(request.headers["x-signature"])
        if len(sigs) < 3:
            return httpx.Response(429, json={"code": 429})
        return httpx.Response(200, json={"keywordList": [{"relKeyword": "x"}]})

    client = make(handler)
    out = await client.keyword_tool(["x"])
    assert out["keywordList"][0]["relKeyword"] == "x" and len(sigs) == 3
    await client.aclose()


async def test_429_after_retries_raises_with_hint():
    client = make(lambda r: httpx.Response(429, json={"code": 429}))
    with pytest.raises(ApiError, match="호출 제한"):
        await client.keyword_tool(["x"])
    await client.aclose()


async def test_auth_error_has_hint_and_never_leaks_secrets():
    client = make(lambda r: httpx.Response(401, json={"code": 10001, "title": "Invalid signature"}))
    with pytest.raises(ApiError) as e:
        await client.keyword_tool(["x"])
    message = str(e.value)
    assert "NAVER_SEARCHAD_SECRET_KEY" in message and "Invalid signature" in message
    assert SECRET not in message and LICENSE not in message
    await client.aclose()


async def test_non_json_and_network_errors():
    c1 = make(lambda r: httpx.Response(200, text="<html>"))
    with pytest.raises(ApiError):
        await c1.keyword_tool(["x"])

    def boom(request):
        raise httpx.ConnectTimeout("timed out")

    c2 = make(boom)
    with pytest.raises(ApiError, match="no response"):
        await c2.keyword_tool(["x"])
    await c1.aclose()
    await c2.aclose()


async def test_hint_validation():
    client = make(lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        await client.keyword_tool([])
    with pytest.raises(ValueError):
        await client.keyword_tool(["  "])
    with pytest.raises(ValueError):
        await client.keyword_tool(["a", "b", "c", "d", "e", "f"])
    await client.aclose()


def test_credentials_resolution():
    assert resolve_searchad_credentials({}) is None
    assert resolve_searchad_credentials({n: "  " for n in NAMES}) is None
    full = dict(zip(NAMES, ("1", "2", "3")))
    assert resolve_searchad_credentials(full) == SearchAdCredentials("1", "2", "3")
    with pytest.raises(CredentialsError, match="missing"):
        resolve_searchad_credentials({NAMES[0]: "1"})
