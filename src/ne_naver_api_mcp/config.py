"""자격증명(NAVER API HUB 키)과 .env 로딩."""
import locale
import os
import sys
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path

HUB_ID = "NCP_APIGW_API_KEY_ID"
HUB_SECRET = "NCP_APIGW_API_KEY"
LEGACY_NAMES = ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")

SETUP_GUIDE = f"""
NAVER API HUB 키를 환경변수로 설정하세요: {HUB_ID}, {HUB_SECRET}
  발급: NAVER Cloud Platform 콘솔 > NAVER API HUB
(네이버 개발자센터 키는 지원하지 않습니다.)"""


class CredentialsError(Exception):
    pass


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def resolve_credentials(env: Mapping[str, str | None]) -> Credentials:
    hub_id = _clean(env.get(HUB_ID))
    hub_secret = _clean(env.get(HUB_SECRET))
    if hub_id and hub_secret:
        return Credentials(hub_id, hub_secret)
    if hub_id or hub_secret:
        raise CredentialsError(
            "NAVER API HUB 자격증명이 불완전합니다.\n"
            f"  {HUB_ID}: {'provided' if hub_id else 'missing'}\n"
            f"  {HUB_SECRET}: {'provided' if hub_secret else 'missing'}\n"
            "두 값을 함께 설정해야 합니다."
        )
    if any(_clean(env.get(name)) for name in LEGACY_NAMES):
        raise CredentialsError(
            "네이버 개발자센터 키(NAVER_CLIENT_ID/NAVER_CLIENT_SECRET)만 설정되어 있습니다. "
            "개발자센터 키는 지원하지 않습니다.\n"
            f"NAVER API HUB 키를 {HUB_ID}, {HUB_SECRET} 에 설정하세요."
        )
    raise CredentialsError(f"자격증명이 설정되지 않았습니다.{SETUP_GUIDE}")


SEARCHAD_CUSTOMER_ID = "NAVER_SEARCHAD_CUSTOMER_ID"
SEARCHAD_ACCESS_LICENSE = "NAVER_SEARCHAD_ACCESS_LICENSE"
SEARCHAD_SECRET_KEY = "NAVER_SEARCHAD_SECRET_KEY"
SEARCHAD_NAMES = (SEARCHAD_CUSTOMER_ID, SEARCHAD_ACCESS_LICENSE, SEARCHAD_SECRET_KEY)


@dataclass(frozen=True)
class SearchAdCredentials:
    customer_id: str
    access_license: str
    secret_key: str


def resolve_searchad_credentials(env: Mapping[str, str | None]) -> SearchAdCredentials | None:
    """검색광고 API 키. 하나도 없으면 None(기능 비활성), 일부만 있으면 오류.

    검색광고 도구는 선택 기능이라 키가 없다고 서버를 막지 않는다.
    """
    values = {name: _clean(env.get(name)) for name in SEARCHAD_NAMES}
    if not any(values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise CredentialsError(
            "네이버 검색광고 API 자격증명이 불완전합니다.\n"
            + "\n".join(f"  {n}: {'missing' if n in missing else 'provided'}" for n in SEARCHAD_NAMES)
            + "\n세 값을 함께 설정하거나, 쓰지 않으면 모두 비워 두세요."
        )
    return SearchAdCredentials(
        values[SEARCHAD_CUSTOMER_ID],  # type: ignore[arg-type]
        values[SEARCHAD_ACCESS_LICENSE],  # type: ignore[arg-type]
        values[SEARCHAD_SECRET_KEY],  # type: ignore[arg-type]
    )


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _read_env_text(file: Path) -> str | None:
    """UTF-8(BOM 허용)로 읽고, 안 되면 이 PC의 기본 인코딩(예: 옛 메모장의 cp949)으로 다시 읽는다.
    읽을 수 없으면 파일 이름만 stderr에 알리고 건너뛴다 (내용은 출력하지 않는다)."""
    try:
        raw = file.read_bytes()
    except OSError:
        return None
    for encoding in ("utf-8-sig", locale.getpreferredencoding(False)):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    print(f"[경고] {file} 을(를) 읽을 수 없어 건너뜁니다 (UTF-8로 저장했는지 확인하세요).", file=sys.stderr)
    return None


def load_dotenv_if_present(
    path: Path | None = None, env: MutableMapping[str, str] | None = None
) -> None:
    """작업 폴더(또는 path)의 .env를 읽어 env에 채운다. 이미 값이 있는 변수는 덮어쓰지 않는다."""
    target = env if env is not None else os.environ
    file = path if path is not None else Path.cwd() / ".env"
    text = _read_env_text(file)
    if text is None:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), _unquote(value.strip())
        if not sep or not key or not value:
            continue
        if _clean(target.get(key)) is None:
            target[key] = value
