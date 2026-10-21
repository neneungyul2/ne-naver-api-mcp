from pathlib import Path

from ne_naver_api_mcp.cache import (
    CallCounter,
    FileCache,
    cache_key,
    cached_call,
    default_cache,
)


def test_cache_key_is_order_independent_and_endpoint_sensitive():
    assert cache_key("/a", {"x": 1, "y": 2}) == cache_key("/a", {"y": 2, "x": 1})
    assert cache_key("/a", {"x": 1}) != cache_key("/b", {"x": 1})
    assert cache_key("/a", {"x": [1, 2]}) != cache_key("/a", {"x": [2, 1]})


def test_cache_key_handles_korean_and_nested_params():
    key = cache_key("search", {"query": "그래머인사이드", "groups": [{"name": "천일문", "kw": ["a"]}]})
    assert len(key) == 64


def test_file_cache_returns_saved_value_and_expires_after_ttl(tmp_path):
    t = [1000.0]
    cache = FileCache(tmp_path, ttl_ms=500, now=lambda: t[0])
    cache.set("k", {"a": 1})
    assert cache.get("k") == {"a": 1}
    t[0] += 501
    assert cache.get("k") is None


def test_file_cache_treats_broken_files_as_miss(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "nodate.json").write_text('{"value": 1}', encoding="utf-8")
    cache = FileCache(tmp_path, ttl_ms=1000)
    assert cache.get("bad") is None
    assert cache.get("nodate") is None
    assert cache.get("missing") is None


def test_cache_stores_korean_values_as_utf8(tmp_path):
    cache = FileCache(tmp_path, ttl_ms=10_000)
    cache.set("k", {"title": "그래머인사이드 후기"})
    raw = (tmp_path / "k.json").read_bytes().decode("utf-8")
    assert "그래머인사이드 후기" in raw  # 이스케이프하지 않고 UTF-8로 저장
    assert cache.get("k") == {"title": "그래머인사이드 후기"}


def test_none_value_is_not_stored_so_it_cannot_look_like_a_miss(tmp_path):
    cache = FileCache(tmp_path, ttl_ms=10_000)
    cache.set("k", None)
    assert not (tmp_path / "k.json").exists()


def test_cache_creates_missing_directories(tmp_path):
    cache = FileCache(tmp_path / "a" / "b", ttl_ms=10_000)
    cache.set("k", [1])
    assert cache.get("k") == [1]


async def test_cached_call_runs_fn_once_for_the_same_arguments(tmp_path):
    cache, counter, calls = FileCache(tmp_path, 10_000), CallCounter(), []

    async def fn():
        calls.append(1)
        return {"ok": True}

    await cached_call(cache, counter, "/e", {"q": 1}, fn)
    await cached_call(cache, counter, "/e", {"q": 1}, fn)
    assert len(calls) == 1
    assert counter.used == 1 and counter.hit == 1


async def test_cached_call_distinguishes_different_params(tmp_path):
    cache, counter = FileCache(tmp_path, 10_000), CallCounter()

    async def fn():
        return {"ok": True}

    await cached_call(cache, counter, "/e", {"q": 1}, fn)
    await cached_call(cache, counter, "/e", {"q": 2}, fn)
    assert counter.used == 2 and counter.hit == 0


async def test_cache_file_never_contains_params_or_secret(tmp_path):
    cache = FileCache(tmp_path, 10_000)

    async def fn():
        return {"ok": 1}

    await cached_call(cache, CallCounter(), "/e", {"token": "SECRET-KEY-123"}, fn)
    for f in Path(tmp_path).iterdir():
        assert "SECRET-KEY-123" not in f.read_text(encoding="utf-8")


def test_default_cache_reads_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("NAVER_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("NAVER_CACHE_TTL_HOURS", "2")
    cache = default_cache()
    assert cache.directory == tmp_path / "c"
    assert cache.ttl_ms == 2 * 3600 * 1000


def test_default_cache_falls_back_to_home_and_24_hours(monkeypatch):
    monkeypatch.delenv("NAVER_CACHE_DIR", raising=False)
    monkeypatch.delenv("NAVER_CACHE_TTL_HOURS", raising=False)
    cache = default_cache()
    assert cache.directory == Path.home() / ".naver-search-mcp" / "cache"
    assert cache.ttl_ms == 24 * 3600 * 1000


def test_default_cache_ignores_a_bad_ttl(monkeypatch):
    monkeypatch.setenv("NAVER_CACHE_TTL_HOURS", "abc")
    assert default_cache().ttl_ms == 24 * 3600 * 1000
