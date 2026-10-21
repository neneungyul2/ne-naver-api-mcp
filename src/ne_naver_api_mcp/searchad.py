"""네이버 검색광고 API 클라이언트 (HMAC-SHA256 서명 인증, httpx 비동기).

서명 문자열은 `{timestamp}.{method}.{uri}`이고 uri는 쿼리스트링을 뺀 경로다.
키워드도구(/keywordstool)만 쓴다: 키워드별 최근 한 달 PC/모바일 검색수.
"""
import asyncio
import base64
import hashlib
import hmac
import time
from collections.abc import Callable

import httpx

from .client import ApiError
from .config import SearchAdCredentials
from .endpoints import SEARCHAD_BASE, SEARCHAD_KEYWORDSTOOL
from .errors import format_searchad_error

MAX_HINTS_PER_CALL = 5  # keywordstool은 한 번에 힌트 키워드 5개까지 받는다
RETRY_DELAYS = (1.0, 3.0)  # 429(호출 제한)일 때 기다렸다 다시 시도하는 간격(초)


def sign(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}".encode()
    digest = hmac.new(secret_key.encode(), message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def normalize_hint(keyword: str) -> str:
    """keywordstool 힌트는 공백이 없어야 하고, 응답의 relKeyword도 공백이 없다."""
    return "".join(keyword.split())


class SearchAdClient:
    def __init__(
        self,
        credentials: SearchAdCredentials,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._credentials = credentials
        self._http = httpx.AsyncClient(transport=transport, timeout=timeout)
        self._retry_delays = retry_delays
        self._clock = clock

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self, method: str, uri: str) -> dict[str, str]:
        timestamp = str(round(self._clock() * 1000))
        return {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": timestamp,
            "X-API-KEY": self._credentials.access_license,
            "X-Customer": self._credentials.customer_id,
            "X-Signature": sign(timestamp, method, uri, self._credentials.secret_key),
        }

    async def _get(self, uri: str, params: dict) -> dict:
        url = f"{SEARCHAD_BASE}{uri}"
        attempts = len(self._retry_delays) + 1
        for attempt in range(attempts):
            try:
                # 서명에는 시각이 들어가므로 재시도마다 새로 만든다
                response = await self._http.get(url, params=params, headers=self._headers("GET", uri))
            except httpx.HTTPError as e:
                raise ApiError(format_searchad_error(url, None, str(e) or type(e).__name__)) from None
            if response.status_code == 429 and attempt < attempts - 1:
                await asyncio.sleep(self._retry_delays[attempt])
                continue
            if response.status_code >= 400:
                try:
                    body: object = response.json()
                except ValueError:
                    body = response.text
                raise ApiError(format_searchad_error(url, response.status_code, body)) from None
            try:
                return response.json()
            except ValueError:
                raise ApiError(format_searchad_error(url, response.status_code, response.text)) from None
        raise AssertionError("unreachable")  # pragma: no cover

    async def keyword_tool(self, hint_keywords: list[str]) -> dict:
        """힌트 키워드(최대 5개)의 연관 키워드 통계. 응답은 {"keywordList": [...]}."""
        hints = [normalize_hint(k) for k in hint_keywords]
        if not hints or any(not h for h in hints):
            raise ValueError("힌트 키워드가 비어 있습니다.")
        if len(hints) > MAX_HINTS_PER_CALL:
            raise ValueError(f"한 번에 키워드 {MAX_HINTS_PER_CALL}개까지 조회할 수 있습니다.")
        return await self._get(
            SEARCHAD_KEYWORDSTOOL, {"hintKeywords": ",".join(hints), "showDetail": "1"}
        )
