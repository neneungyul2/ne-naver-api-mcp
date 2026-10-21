"""find_category: 자연어로 쇼핑 분야 코드 찾기 (정확/시작/포함/유사 일치, 단계별 가중치)."""
import json
import math
import sys
from functools import lru_cache
from importlib import resources

LEVELS = (
    ("level1", "대분류", 50),
    ("level2", "중분류", 30),
    ("level3", "소분류", 20),
    ("level4", "세분류", 10),
)
SUGGESTIONS = ["패션", "화장품", "가구", "스마트폰", "가전제품", "스포츠", "도서", "자동차", "식품", "뷰티"]
SIMILARITY_THRESHOLD = 0.6


@lru_cache(maxsize=1)
def load_categories() -> list[dict]:
    """패키지에 포함된 categories.json을 읽는다 (작업 폴더와 무관). 실패하면 빈 목록."""
    try:
        text = (resources.files("ne_naver_api_mcp") / "data" / "categories.json").read_text(
            encoding="utf-8"
        )
        return json.loads(text)
    except (OSError, ValueError) as e:
        print(f"카테고리 데이터 로딩 실패: {e}", file=sys.stderr)
        return []


def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(a) + 1))
    for j, cb in enumerate(b, start=1):
        current = [j]
        for i, ca in enumerate(a, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(current[i - 1] + 1, previous[i] + 1, previous[i - 1] + cost))
        previous = current
    return previous[len(a)]


def similarity(a: str, b: str) -> float:
    longer, shorter = (a, b) if len(a) > len(b) else (b, a)
    if len(longer) == 0:
        return 1.0
    return (len(longer) - levenshtein(longer, shorter)) / len(longer)


def _score(category: dict, query: str) -> tuple[int, str]:
    best_score, best_type = 0, ""
    for key, name, bonus in LEVELS:
        text = (category.get(key) or "").lower()
        if not text:
            continue
        if text == query:
            score, match_type = 100 + bonus, f"정확일치({name})"
        elif text.startswith(query):
            score, match_type = 80 + bonus, f"시작일치({name})"
        elif query in text:
            score, match_type = 60 + bonus, f"포함일치({name})"
        else:
            sim = similarity(query, text)
            if sim > SIMILARITY_THRESHOLD:
                score, match_type = math.floor(sim * 40) + bonus, f"유사일치({name})"
            else:
                score, match_type = 0, ""
        if score > best_score:
            best_score, best_type = score, match_type
    return best_score, best_type


def find_category(
    query: str, max_results: int = 10, *, categories: list[dict] | None = None
) -> dict:
    data = categories if categories is not None else load_categories()
    q = query.lower().strip()
    scored = []
    for category in data:
        score, match_type = _score(category, q)
        if score > 0:
            scored.append((score, match_type, category))
    scored.sort(key=lambda t: (-t[0], t[2].get("code", "")))
    top = scored[:max_results]

    if not top:
        return {
            "message": f'"{query}"와 관련된 카테고리를 찾을 수 없습니다. 다른 검색어를 시도해보세요.',
            "suggestions": SUGGESTIONS,
        }
    return {
        "message": f'"{query}" 검색 결과 ({len(top)}개, 관련도순 정렬)',
        "total_found": len(top),
        "categories": [
            {
                "code": c["code"],
                "category": " > ".join(c[k] for k, _, _ in LEVELS if c.get(k)),
                "match_type": match_type,
                "score": score,
                "levels": {name: c.get(key) or "" for key, name, _ in LEVELS},
            }
            for score, match_type, c in top
        ],
        "next_steps": {
            "trend_analysis": "이제 datalab_shopping_category 도구로 각 카테고리의 트렌드 분석이 가능합니다",
            "age_analysis": "datalab_shopping_by_age 도구로 연령별 쇼핑 패턴을 분석할 수 있습니다",
            "gender_analysis": "datalab_shopping_by_gender 도구로 성별 쇼핑 패턴을 분석할 수 있습니다",
            "device_analysis": "datalab_shopping_by_device 도구로 디바이스별 쇼핑 패턴을 분석할 수 있습니다",
        },
    }
