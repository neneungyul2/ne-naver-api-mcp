from ne_naver_api_mcp.categories import find_category, load_categories

CATS = [
    {"code": "2", "level1": "패션의류", "level2": "여성의류", "level3": "원피스", "level4": ""},
    {"code": "1", "level1": "패션잡화", "level2": "", "level3": "", "level4": ""},
    {"code": "3", "level1": "가구", "level2": "침대", "level3": "패션침대", "level4": ""},
]


def by_code(result: dict) -> dict:
    return {c["code"]: c for c in result["categories"]}


def test_exact_match_scores_100_plus_level_bonus():
    res = find_category("패션의류", categories=CATS)
    top = res["categories"][0]
    assert top["code"] == "2"
    assert top["match_type"] == "정확일치(대분류)"
    assert top["score"] == 150
    assert top["levels"]["대분류"] == "패션의류"


def test_starts_with_and_contains_scores():
    starts = by_code(find_category("패션", categories=CATS))
    assert starts["2"]["score"] == 130 and starts["2"]["match_type"] == "시작일치(대분류)"
    assert starts["3"]["score"] == 100 and starts["3"]["match_type"] == "시작일치(소분류)"
    contains = by_code(find_category("의류", categories=CATS))
    assert contains["2"]["score"] == 110 and contains["2"]["match_type"] == "포함일치(대분류)"


def test_fuzzy_match_requires_similarity_over_0_6():
    fuzzy = by_code(find_category("패션의루", categories=CATS))
    assert fuzzy["2"]["match_type"] == "유사일치(대분류)"
    assert fuzzy["2"]["score"] == 80  # floor(0.75 * 40) + 50
    assert find_category("가나다라", categories=CATS)["message"].endswith("시도해보세요.")


def test_sorted_by_score_then_code():
    codes = [c["code"] for c in find_category("패션", categories=CATS)["categories"]]
    assert codes == ["1", "2", "3"]  # 130, 130(코드 오름차순), 100


def test_max_results_limit_and_total_found():
    res = find_category("패션", max_results=2, categories=CATS)
    assert len(res["categories"]) == 2
    assert res["total_found"] == 2


def test_no_result_returns_message_and_suggestions():
    res = find_category("존재하지않는분류명xyz", categories=CATS)
    assert "찾을 수 없습니다" in res["message"]
    assert "패션" in res["suggestions"]
    assert "categories" not in res


def test_result_structure_and_next_steps():
    res = find_category("패션의류", categories=CATS)
    cat = res["categories"][0]
    assert cat["category"] == "패션의류 > 여성의류 > 원피스"
    assert set(cat["levels"]) == {"대분류", "중분류", "소분류", "세분류"}
    assert set(res["next_steps"]) == {
        "trend_analysis", "age_analysis", "gender_analysis", "device_analysis",
    }
    assert "datalab_shopping_category" in res["next_steps"]["trend_analysis"]


def test_query_is_case_and_space_insensitive():
    cats = [{"code": "9", "level1": "Grammar", "level2": "", "level3": "", "level4": ""}]
    assert find_category("  GRAMMAR ", categories=cats)["categories"][0]["score"] == 150


def test_data_loaded_from_package_resources(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # 작업 폴더와 무관해야 한다
    data = load_categories()
    assert len(data) > 1000
    assert any(c["code"] == "50005951" for c in data)


def test_load_categories_is_cached():
    assert load_categories() is load_categories()


def test_book_grammar_category_is_found():
    res = find_category("영어", max_results=50)
    assert any(c["code"] == "50005951" for c in res["categories"])
