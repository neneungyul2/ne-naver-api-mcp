"""NAVER API HUB HTTP 클라이언트 (httpx 비동기)."""
from typing import Any

import httpx

from .config import Credentials
from .endpoints import AUTH_HEADER_NAMES, SEARCH_BASE, SHOPPING_BASE, TREND_URL
from .errors import format_api_error


class ApiError(Exception):
    """HUB 호출 실패. 메시지는 format_api_error 결과(키 값 없음)다."""


class NaverApiClient:
    def __init__(
        self,
        credentials: Credentials,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        id_name, secret_name = AUTH_HEADER_NAMES
        self._http = httpx.AsyncClient(
            headers={
                id_name: credentials.client_id,
                secret_name: credentials.client_secret,
                "Content-Type": "application/json",
            },
            transport=transport,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict:
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            # 응답이 아예 없는 실패(타임아웃, 연결 거부 등)는 원인 메시지가 유일한 단서다
            raise ApiError(format_api_error(url, None, str(e) or type(e).__name__)) from None
        if response.status_code >= 400:
            try:
                body: object = response.json()
            except ValueError:
                body = response.text
            raise ApiError(format_api_error(url, response.status_code, body)) from None
        try:
            return response.json()
        except ValueError:
            raise ApiError(
                format_api_error(url, response.status_code, response.text)
            ) from None

    async def _get(self, url: str, params: dict) -> dict:
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._request("GET", url, params=clean)

    async def _post(self, url: str, data: dict) -> dict:
        return await self._request("POST", url, json=data)

    async def search(self, type: str, params: dict) -> dict:  # noqa: A002
        return await self._get(f"{SEARCH_BASE}/{type}", params)

    async def search_trend(self, req: dict) -> dict:
        return await self._post(TREND_URL, req)

    async def shopping_category(self, req: dict) -> dict:
        return await self._post(f"{SHOPPING_BASE}/categories", req)

    async def shopping_by_device(self, req: dict) -> dict:
        return await self._post(f"{SHOPPING_BASE}/category/device", req)

    async def shopping_by_gender(self, req: dict) -> dict:
        return await self._post(f"{SHOPPING_BASE}/category/gender", req)

    async def shopping_by_age(self, req: dict) -> dict:
        return await self._post(f"{SHOPPING_BASE}/category/age", req)

    async def shopping_keywords(self, req: dict) -> dict:
        return await self._post(f"{SHOPPING_BASE}/category/keywords", req)

    async def shopping_keyword_by_device(self, req: dict) -> dict:
        return await self._post(f"{SHOPPING_BASE}/category/keyword/device", req)

    async def shopping_keyword_by_gender(self, req: dict) -> dict:
        return await self._post(f"{SHOPPING_BASE}/category/keyword/gender", req)

    async def shopping_keyword_by_age(self, req: dict) -> dict:
        return await self._post(f"{SHOPPING_BASE}/category/keyword/age", req)
