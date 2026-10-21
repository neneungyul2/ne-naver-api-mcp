import pytest

from ne_naver_api_mcp.config import (
    Credentials,
    CredentialsError,
    load_dotenv_if_present,
    resolve_credentials,
)

ID, KEY = "NCP_APIGW_API_KEY_ID", "NCP_APIGW_API_KEY"


def test_resolve_credentials_ok():
    assert resolve_credentials({ID: "hubid", KEY: "hubsecret"}) == Credentials("hubid", "hubsecret")


def test_missing_both_raises_with_setup_guide():
    with pytest.raises(CredentialsError) as e:
        resolve_credentials({})
    assert ID in str(e.value) and KEY in str(e.value)


def test_half_hub_key_names_missing_one():
    with pytest.raises(CredentialsError, match=r"NCP_APIGW_API_KEY\b.*missing|missing"):
        resolve_credentials({ID: "hubid"})
    with pytest.raises(CredentialsError) as e:
        resolve_credentials({ID: "hubid"})
    assert f"{KEY}: missing" in str(e.value)
    with pytest.raises(CredentialsError) as e2:
        resolve_credentials({KEY: "hubsecret"})
    assert f"{ID}: missing" in str(e2.value)


def test_legacy_only_raises_with_hub_guidance():
    with pytest.raises(CredentialsError) as e:
        resolve_credentials({"NAVER_CLIENT_ID": "a", "NAVER_CLIENT_SECRET": "b"})
    msg = str(e.value)
    assert ID in msg and KEY in msg
    assert "개발자센터 키는 지원하지 않습니다" in msg


def test_whitespace_only_values_count_as_missing():
    with pytest.raises(CredentialsError):
        resolve_credentials({ID: "   ", KEY: "\t"})


def test_whitespace_values_are_trimmed():
    assert resolve_credentials({ID: "  hubid ", KEY: " hubsecret\n"}) == Credentials("hubid", "hubsecret")


def test_none_values_are_missing():
    with pytest.raises(CredentialsError):
        resolve_credentials({ID: None, KEY: None})


def test_dotenv_does_not_override_existing_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"{ID}=from-file\n{KEY}=from-file-secret\n", encoding="utf-8")
    env = {ID: "already"}
    load_dotenv_if_present(f, env)
    assert env[ID] == "already"
    assert env[KEY] == "from-file-secret"


def test_dotenv_empty_value_is_not_set(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"{ID}=\n{KEY}=   \n", encoding="utf-8")
    env: dict[str, str] = {}
    load_dotenv_if_present(f, env)
    assert ID not in env and KEY not in env


def test_dotenv_missing_file_is_noop(tmp_path):
    env: dict[str, str] = {}
    load_dotenv_if_present(tmp_path / "nope.env", env)
    assert env == {}


def test_dotenv_reads_utf8_and_comments_and_quotes(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        "# 주석\n\nNAVER_EXPORT_DIR=\"D:\\내 문서\\exports\"\nexport NAVER_CACHE_DIR='C:/캐시'\nPLAIN = value \n",
        encoding="utf-8",
    )
    env: dict[str, str] = {}
    load_dotenv_if_present(f, env)
    assert env["NAVER_EXPORT_DIR"] == "D:\\내 문서\\exports"
    assert env["NAVER_CACHE_DIR"] == "C:/캐시"
    assert env["PLAIN"] == "value"


def test_dotenv_default_path_is_cwd(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"{ID}=cwdid\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    env: dict[str, str] = {}
    load_dotenv_if_present(None, env)
    assert env[ID] == "cwdid"
