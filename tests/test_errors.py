from ne_naver_api_mcp.errors import format_api_error

URL = "https://naverapihub.apigw.ntruss.com/search/v1/blog"


def test_message_carries_label_status_url_and_body():
    msg = format_api_error(URL, 500, {"error": {"message": "boom"}})
    assert "NAVER API HUB" in msg
    assert "HTTP 500" in msg
    assert "search/v1/blog" in msg
    assert "boom" in msg


def test_401_adds_key_hint():
    msg = format_api_error(URL, 401, "unauthorized")
    assert "NCP_APIGW_API_KEY_ID" in msg


def test_non_401_has_no_hint():
    msg = format_api_error(URL, 500, "x")
    assert "NCP_APIGW_API_KEY_ID" not in msg


def test_no_response_is_labelled():
    msg = format_api_error(URL, None, "timeout")
    assert "no response" in msg
    assert "timeout" in msg


def test_string_body_is_included_verbatim():
    assert "Bad Gateway" in format_api_error(URL, 502, "Bad Gateway")


def test_korean_body_is_not_escaped():
    assert "한글 본문" in format_api_error(URL, 400, {"errMsg": "한글 본문"})


def test_empty_body_adds_no_extra_line():
    assert format_api_error(URL, 500, None).count("\n") == 0


def test_error_message_never_contains_key_unless_passed_in():
    assert "SECRET-KEY-123" not in format_api_error(URL, 401, {"a": 1})


INACTIVE = {"error": {"errorCode": 401, "message": "요청한 API는 이 Application에서 활성화되어 있지 않습니다."}}


def test_inactive_api_401_points_to_the_application_not_the_key():
    msg = format_api_error(URL, 401, INACTIVE)
    assert "활성화되어 있지 않습니다" in msg
    assert "Application에 해당 API를 추가" in msg
    assert "올바른지 확인하세요" not in msg  # 키 안내로 오해하게 만들지 않는다


def test_other_401_still_gets_the_key_hint():
    assert "올바른지 확인하세요" in format_api_error(URL, 401, {"error": {"message": "Unauthorized"}})
