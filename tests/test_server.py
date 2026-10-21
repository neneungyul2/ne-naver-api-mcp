"""서버 시작/종료 동작. 실제 자식 프로세스로 확인한다."""
import os
import subprocess
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

CODE = "from ne_naver_api_mcp.server import main; main()"
KEY_VARS = ("NCP_APIGW_API_KEY_ID", "NCP_APIGW_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")


def clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in KEY_VARS and k != "NAVER_TOOLS_ALLOW"}
    env.update(extra)
    return env


def run_server(env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    """stdin을 닫고 실행한다. 시작에 성공하면 stdin EOF로 곧 종료한다."""
    return subprocess.run(
        [sys.executable, "-c", CODE],
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=60,
    )


def test_main_without_keys_exits_1_with_stderr_message_and_empty_stdout(tmp_path):
    p = run_server(clean_env(), tmp_path)
    assert p.returncode == 1
    assert p.stdout == b""
    assert "NCP_APIGW_API_KEY_ID" in p.stderr.decode("utf-8")


def test_stderr_is_utf8_even_when_the_console_locale_is_not(tmp_path):
    p = run_server(clean_env(PYTHONUTF8="0", PYTHONIOENCODING="cp949"), tmp_path)
    p2 = run_server({k: v for k, v in clean_env(PYTHONUTF8="0").items() if k != "PYTHONIOENCODING"}, tmp_path)
    for proc in (p, p2):
        assert "자격증명" in proc.stderr.decode("utf-8")


def test_main_with_legacy_keys_only_exits_1_and_explains(tmp_path):
    p = run_server(clean_env(NAVER_CLIENT_ID="a", NAVER_CLIENT_SECRET="b"), tmp_path)
    assert p.returncode == 1 and p.stdout == b""
    err = p.stderr.decode("utf-8")
    assert "개발자센터 키는 지원하지 않습니다" in err and "NCP_APIGW_API_KEY_ID" in err


def test_main_with_half_a_key_names_the_missing_variable(tmp_path):
    p = run_server(clean_env(NCP_APIGW_API_KEY_ID="x"), tmp_path)
    assert p.returncode == 1
    assert "NCP_APIGW_API_KEY: missing" in p.stderr.decode("utf-8")


def test_main_starts_with_dummy_keys_and_never_prints_the_secret(tmp_path):
    p = run_server(
        clean_env(NCP_APIGW_API_KEY_ID="dummyid-123", NCP_APIGW_API_KEY="dummysecretvalue"), tmp_path
    )
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    for stream in (p.stdout, p.stderr):
        assert b"dummysecretvalue" not in stream and b"dummyid-123" not in stream


async def test_server_lists_tools_over_stdio_with_dummy_keys(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", CODE],
        env=clean_env(NCP_APIGW_API_KEY_ID="dummyid-123", NCP_APIGW_API_KEY="dummysecretvalue"),
        cwd=str(tmp_path),
    )
    async with Client(params) as client:
        assert client.server_info.name == "ne-naver-api-mcp"
        # 도구가 하나도 등록되지 않은 서버(예: 오래된 빌드)가 통과하지 않도록 개수까지 확인한다
        assert len((await client.list_tools()).tools) == 20


def test_dotenv_in_cwd_is_used_when_the_environment_has_no_keys(tmp_path):
    (tmp_path / ".env").write_text(
        "NCP_APIGW_API_KEY_ID=fromfile-id\nNCP_APIGW_API_KEY=fromfile-secret\n", encoding="utf-8"
    )
    p = run_server(clean_env(), tmp_path)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")


def test_environment_wins_over_dotenv(tmp_path):
    (tmp_path / ".env").write_text("NCP_APIGW_API_KEY_ID=fromfile-id\n", encoding="utf-8")
    # 환경변수 쌍이 완전하면 .env의 값이 아니라 환경변수가 쓰인다 (둘 다 있어 성공)
    p = run_server(clean_env(NCP_APIGW_API_KEY_ID="env-id", NCP_APIGW_API_KEY="env-secret"), tmp_path)
    assert p.returncode == 0


def test_importing_the_server_and_building_it_does_not_load_kiwipiepy():
    code = (
        "import sys\n"
        "from ne_naver_api_mcp.server import create_server\n"
        "create_server(None)\n"
        "print('kiwipiepy' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", check=True,
        env=clean_env(),
    )
    assert out.stdout.strip() == "False"
