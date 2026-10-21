"""실제 NAVER API HUB 응답을 tests/fixtures/ 에 녹화한다 (호출 6회).

사용: uv run python scripts/record_fixtures.py   (작업 폴더의 .env 또는 환경변수의 키 사용)

공개 저장소에 올라가므로 제3자 콘텐츠(블로그/카페 글의 제목, 요약, 주소, 이름)는 합성 값으로 바꾸고,
저장 전에 키 값이 섞였는지 검사한다. 결과의 구조와 날짜 형식, 수치만 실제 응답이다.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from ne_naver_api_mcp.client import ApiError, NaverApiClient
from ne_naver_api_mcp.config import load_dotenv_if_present, resolve_credentials

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def scrub_item(item: dict, i: int) -> dict:
    out = {
        **item,
        "title": f"<b>그래머인사이드</b> 샘플 제목 {i + 1}",
        "description": f"샘플 요약입니다. <b>그래머인사이드</b> 문법 교재 예시 문장 {i + 1}.",
        "link": f"https://example.invalid/post/{i}",
    }
    if "bloggername" in item:
        out["bloggername"] = "example"
        out["bloggerlink"] = f"https://example.invalid/blog/{i}"
    if "cafename" in item:
        out["cafename"] = "example"
        out["cafeurl"] = f"https://example.invalid/cafe/{i}"
    return out


def save(name: str, value: object, secrets: list[str]) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2)
    for secret in secrets:
        if secret and secret in text:
            raise RuntimeError(f"{name}: 키 값이 섞였습니다. 저장하지 않습니다.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(text + "\n", encoding="utf-8")
    print("saved", name)


async def main() -> None:
    load_dotenv_if_present()
    credentials = resolve_credentials(os.environ)
    secrets = [credentials.client_id, credentials.client_secret]
    client = NaverApiClient(credentials)
    try:
        for kind in ("blog", "cafearticle", "webkr"):
            res = await client.search(kind, {"query": "그래머인사이드", "display": 3, "sort": "date"})
            save(f"search-{kind}", {**res, "items": [scrub_item(it, i) for i, it in enumerate(res["items"])]}, secrets)

        rng = {"startDate": "2025-01-01", "endDate": "2025-06-30", "timeUnit": "month"}
        trend = await client.search_trend(
            {**rng, "keywordGroups": [{"groupName": "그래머인사이드", "keywords": ["그래머인사이드", "그래머 인사이드"]}]}
        )
        save("search-trend", trend, secrets)

        shop = {"startDate": "2024-01-01", "endDate": "2026-09-30", "timeUnit": "month", "category": "50005951"}
        keyword = lambda n: {"name": n, "param": [n]}  # noqa: E731
        save(
            "shopping-keywords",
            await client.shopping_keywords({**shop, "keyword": [keyword("그래머인사이드"), keyword("천일문 중등 그래머")]}),
            secrets,
        )

        # 키워드 그룹당 param 2개 이상은 400 (실제로 확인된 제한)
        try:
            await client.shopping_keywords(
                {**shop, "keyword": [{"name": "그래머인사이드", "param": ["그래머인사이드", "그래머 인사이드"]}]}
            )
            raise RuntimeError("400이 예상됐지만 성공했습니다")
        except ApiError as e:
            lines = str(e).split("\n")[:2]
            body = lines[1].replace('"errId"', '"_errId"') if len(lines) > 1 else ""
            save("shopping-param-limit-error", {"status": 400, "message": "\n".join([lines[0], body])}, secrets)
    finally:
        await client.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:  # noqa: BLE001
        print(f"실패: {e}", file=sys.stderr)
        sys.exit(1)
