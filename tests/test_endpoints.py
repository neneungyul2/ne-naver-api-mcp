from ne_naver_api_mcp import endpoints as ep


def test_base_urls():
    assert ep.BASE_URL == "https://naverapihub.apigw.ntruss.com"
    assert ep.SEARCH_BASE == "https://naverapihub.apigw.ntruss.com/search/v1"
    assert ep.TREND_URL == "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
    assert ep.SHOPPING_BASE == "https://naverapihub.apigw.ntruss.com/shopping/v1"


def test_search_url_is_base_plus_type():
    assert f"{ep.SEARCH_BASE}/blog" == "https://naverapihub.apigw.ntruss.com/search/v1/blog"
    assert f"{ep.SEARCH_BASE}/cafearticle" == "https://naverapihub.apigw.ntruss.com/search/v1/cafearticle"


def test_shopping_suffixes():
    suffixes = [
        "/categories",
        "/category/device",
        "/category/gender",
        "/category/age",
        "/category/keywords",
        "/category/keyword/device",
        "/category/keyword/gender",
        "/category/keyword/age",
    ]
    for s in suffixes:
        assert f"{ep.SHOPPING_BASE}{s}" == f"https://naverapihub.apigw.ntruss.com/shopping/v1{s}"


def test_auth_header_names():
    assert ep.AUTH_HEADER_NAMES == ("X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY")


def test_unverified_set_is_a_frozenset():
    assert isinstance(ep.UNVERIFIED_OR_INVALID, frozenset)
