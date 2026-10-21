"""코드 검토에서 나온 견고성 항목: 오류 메시지 노출, 캐시/.env 장애, Kiwi 한 번만 로딩."""
import io
import subprocess
import sys
from contextlib import redirect_stderr

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ne_naver_api_mcp.analysis import tokenizer as tok
from ne_naver_api_mcp.analysis.brand import Brand
from ne_naver_api_mcp.analysis.compare_trend import CompareInput, compare_brand_trend
from ne_naver_api_mcp.cache import CallCounter, FileCache, cached_call
from ne_naver_api_mcp.config import load_dotenv_if_present
from ne_naver_api_mcp.tool_filter import surface_errors


async def test_os_errors_reach_the_user_with_their_reason():
    async def tool() -> str:
        raise PermissionError("cache folder is read-only")

    with pytest.raises(ToolError, match="read-only"):
        await surface_errors(tool)()


async def test_unexpected_errors_name_their_type_and_message_and_are_logged_to_stderr():
    async def tool() -> str:
        raise KeyError("results")

    buf = io.StringIO()
    with redirect_stderr(buf), pytest.raises(ToolError) as e:
        await surface_errors(tool)()
    assert "KeyError" in str(e.value) and "results" in str(e.value)
    assert "Traceback" in buf.getvalue()  # 서버 로그에는 스택이 남는다


def blocked_cache(tmp_path) -> FileCache:
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    return FileCache(blocker / "cache", ttl_ms=10**9)  # 파일 아래에는 폴더를 만들 수 없다


def test_cache_set_is_best_effort_and_warns_once(tmp_path):
    cache = blocked_cache(tmp_path)
    buf = io.StringIO()
    with redirect_stderr(buf):
        cache.set("k", {"a": 1})
        cache.set("k2", {"a": 2})
    assert cache.get("k") is None
    assert buf.getvalue().count("[경고]") == 1  # 같은 폴더의 경고는 한 번만


async def test_an_unwritable_cache_never_discards_a_paid_response(tmp_path):
    cache, counter = blocked_cache(tmp_path), CallCounter()

    async def fn():
        return {"ok": True}

    with redirect_stderr(io.StringIO()):
        assert await cached_call(cache, counter, "/e", {"q": 1}, fn) == {"ok": True}
    assert counter.used == 1


async def test_comparison_still_returns_results_with_an_unwritable_cache(tmp_path):
    class Api:
        async def search_trend(self, req):
            return {"results": [{"title": "A", "data": [{"period": "2025-01-01", "ratio": 100}]}]}

    with redirect_stderr(io.StringIO()):
        res = await compare_brand_trend(
            CompareInput(brands=[Brand("A")], source="search", start_date="2025-01-01",
                         end_date="2025-02-01", time_unit="month"),
            Api(), blocked_cache(tmp_path),
        )
    assert res.series[0].points[0].ratio == 100


def test_dotenv_in_the_local_codepage_is_read_instead_of_crashing(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_bytes("# 네이버 키\nNCP_APIGW_API_KEY_ID=abc123\n".encode("cp949"))
    monkeypatch.setattr("locale.getpreferredencoding", lambda *a, **k: "cp949")
    env: dict[str, str] = {}
    load_dotenv_if_present(f, env)
    assert env["NCP_APIGW_API_KEY_ID"] == "abc123"


def test_an_undecodable_dotenv_is_skipped_with_a_warning_that_names_only_the_file(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_bytes(b"\xff\xfe\x00bad\x80\x81 NCP_APIGW_API_KEY_ID=secretvalue\n")
    monkeypatch.setattr("locale.getpreferredencoding", lambda *a, **k: "ascii")
    env: dict[str, str] = {}
    buf = io.StringIO()
    with redirect_stderr(buf):
        load_dotenv_if_present(f, env)
    assert env == {}
    assert ".env" in buf.getvalue() and "secretvalue" not in buf.getvalue()


def test_server_starts_when_the_environment_has_keys_even_if_dotenv_is_cp949(tmp_path):
    (tmp_path / ".env").write_bytes("# 네이버 키\nOTHER=1\n".encode("cp949"))
    import os

    env = {k: v for k, v in os.environ.items()}
    env.update(NCP_APIGW_API_KEY_ID="dummyid", NCP_APIGW_API_KEY="dummysecret", PYTHONUTF8="0")
    p = subprocess.run([sys.executable, "-c", "from ne_naver_api_mcp.server import main; main()"],
                       env=env, cwd=tmp_path, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")


class FakeKiwi:
    loads = 0

    def __init__(self):
        FakeKiwi.loads += 1
        self.words: list[str] = []

    def add_user_word(self, word, tag):
        self.words.append(word)

    def tokenize(self, text):
        return []


def test_the_kiwi_model_is_built_once_across_tokenizers_and_calls(monkeypatch):
    FakeKiwi.loads = 0
    tok.reset_shared_kiwi()
    monkeypatch.setattr(tok, "_new_kiwi", FakeKiwi)
    a = tok.default_tokenizer([Brand("쎄듀워크북")])
    b = tok.default_tokenizer([Brand("다사영어")])
    a("텍스트")
    b("텍스트")
    a("또 텍스트")
    assert FakeKiwi.loads == 1
    tok.reset_shared_kiwi()


def test_new_brand_words_are_added_to_the_shared_model_without_reloading(monkeypatch):
    FakeKiwi.loads = 0
    tok.reset_shared_kiwi()
    monkeypatch.setattr(tok, "_new_kiwi", FakeKiwi)
    tok.KiwiTokenizer(["워크북"])("x")
    tok.KiwiTokenizer(["워크북", "다사영어"])("x")
    shared = tok._shared_kiwi([])
    assert FakeKiwi.loads == 1
    assert shared.words.count("워크북") == 1 and "다사영어" in shared.words
    tok.reset_shared_kiwi()
