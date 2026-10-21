"""브랜드(제품/시리즈) 모델: 이름 + 별칭, 검색 키워드, 본문 매칭."""
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

MAX_KEYWORDS_PER_BRAND = 20


@dataclass(frozen=True)
class Brand:
    name: str
    aliases: tuple[str, ...] = ()


class BrandInput(BaseModel):
    """도구 입력용 브랜드 (이름 + 표기가 다른 별칭)."""

    name: str = Field(min_length=1, description="브랜드(제품/시리즈) 이름")
    aliases: list[str] = Field(default_factory=list, description="띄어쓰기/영문 표기 등 별칭")

    def to_brand(self) -> Brand:
        return Brand(self.name, tuple(self.aliases))


def brand_keywords(brand: Brand) -> list[str]:
    """이름 + 별칭에서 빈 값과 (대소문자 무시) 중복을 뺀 검색 키워드. 공백만 다른 항목은 유지한다."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in (brand.name, *brand.aliases):
        keyword = raw.strip()
        if not keyword or keyword.lower() in seen:
            continue
        seen.add(keyword.lower())
        out.append(keyword)
    if len(out) > MAX_KEYWORDS_PER_BRAND:
        raise ValueError(
            f'브랜드 "{brand.name}"의 키워드는 최대 {MAX_KEYWORDS_PER_BRAND}개까지 지정할 수 있습니다 '
            f"(현재 {len(out)}개)."
        )
    return out


def validate_brands(brands: Sequence[Brand]) -> None:
    """호출 전에 브랜드 입력을 검증한다 (키워드 20개 초과, 이름이 빈 브랜드)."""
    for brand in brands:
        if not brand_keywords(brand):
            raise ValueError("브랜드 이름이 비어 있습니다. name은 공백이 아닌 문자열이어야 합니다.")


def _squash(text: str) -> str:
    return "".join(text.split()).lower()


def matches_brand(text: str, brand: Brand) -> bool:
    """텍스트에 브랜드 키워드가 하나라도 있으면 True. 공백/대소문자 차이는 무시한다."""
    haystack = _squash(text)
    return any(_squash(kw) in haystack for kw in brand_keywords(brand))
