import pytest
from pydantic import ValidationError

from ne_naver_api_mcp.analysis.brand import (
    Brand,
    BrandInput,
    brand_keywords,
    matches_brand,
    validate_brands,
)


def test_brand_keywords_dedupes_exact_and_case_only_differences_but_keeps_spacing_variants():
    kws = brand_keywords(
        Brand("그래머인사이드", ("그래머 인사이드", "그래머인사이드", "Grammar Inside", "grammar inside"))
    )
    assert kws == ["그래머인사이드", "그래머 인사이드", "Grammar Inside"]


def test_brand_keywords_drops_blank_aliases():
    assert brand_keywords(Brand("천일문", ("", "  "))) == ["천일문"]


def test_brand_keywords_rejects_more_than_20():
    aliases = tuple(f"별칭{i}" for i in range(20))  # 이름 포함 21개
    with pytest.raises(ValueError, match="최대 20개"):
        brand_keywords(Brand("이름", aliases))


def test_brand_keywords_allows_exactly_20():
    aliases = tuple(f"별칭{i}" for i in range(19))
    assert len(brand_keywords(Brand("이름", aliases))) == 20


def test_matches_brand_ignores_spacing_and_case():
    assert matches_brand("천일문 중등 그래머 후기", Brand("천일문중등그래머"))
    assert matches_brand("GRAMMAR   inside 후기", Brand("x", ("Grammar Inside",)))
    assert not matches_brand("그래머 수업", Brand("그래머인사이드"))


def test_validate_brands_rejects_too_many_keywords_and_blank_names():
    aliases = tuple(f"별칭{i}" for i in range(20))
    with pytest.raises(ValueError, match="최대 20개"):
        validate_brands([Brand("이름", aliases)])
    with pytest.raises(ValueError, match="비어"):
        validate_brands([Brand(" ")])
    validate_brands([Brand("정상", ("별칭",))])


def test_brand_input_defaults_aliases_to_empty():
    assert BrandInput(name="천일문").to_brand() == Brand("천일문", ())


def test_brand_input_rejects_empty_name():
    with pytest.raises(ValidationError):
        BrandInput(name="")


def test_brand_input_converts_aliases_to_tuple():
    assert BrandInput(name="a", aliases=["b", "c"]).to_brand() == Brand("a", ("b", "c"))
