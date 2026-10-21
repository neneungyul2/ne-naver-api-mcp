"""NAVER API HUB 오류 메시지 형식."""
import json

LABEL = "NAVER API HUB"
KEY_HINT = (
    "인증에 실패했습니다. NAVER API HUB 키(NCP_APIGW_API_KEY_ID / NCP_APIGW_API_KEY)가 "
    "올바른지 확인하세요."
)


INACTIVE_MARKER = "활성화되어 있지 않습니다"
INACTIVE_HINT = (
    "이 API는 사용 중인 Application에서 활성화되어 있지 않습니다. "
    "NCP 콘솔 > NAVER API HUB에서 Application에 해당 API를 추가하세요."
)


def _stringify(body: object) -> str:
    if body is None:
        return ""
    if isinstance(body, str):
        return body
    try:
        return json.dumps(body, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(body)


def format_api_error(url: str, status: int | None, body: object) -> str:
    """상태 코드, URL, 응답 본문을 담은 오류 메시지. 키 값은 절대 넣지 않는다."""
    status_text = "no response" if status is None else f"HTTP {status}"
    lines = [f"[{LABEL}] {status_text} — {url}"]
    text = _stringify(body)
    if text:
        lines.append(text)
    if status == 401:
        # 키가 틀린 것과 "이 Application에 API가 없는 것"을 구분해 안내한다
        lines.append(INACTIVE_HINT if INACTIVE_MARKER in text else KEY_HINT)
    return "\n".join(lines)
