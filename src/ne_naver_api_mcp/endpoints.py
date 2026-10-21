"""NAVER API HUB 호출 주소와 인증 헤더 이름."""

BASE_URL = "https://naverapihub.apigw.ntruss.com"
SEARCH_BASE = f"{BASE_URL}/search/v1"
TREND_URL = f"{BASE_URL}/search-trend/v1/search"
SHOPPING_BASE = f"{BASE_URL}/shopping/v1"

AUTH_HEADER_NAMES = ("X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY")

# 실제 키로 확인했을 때 HUB에 없는 검색 타입 (Task 4에서 채운다). 이 타입의 도구는 등록하지 않는다.
UNVERIFIED_OR_INVALID: frozenset[str] = frozenset()
