# ne-naver-api-mcp 파이썬 재작성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** NAVER API HUB용 MCP 서버(도구 20개: 원본 18개 + 분석 2개)를 파이썬으로 새로 만들고 `uvx`로 실행할 수 있게 한다.

**Architecture:** `src/ne_naver_api_mcp/` 아래에 클라이언트(httpx 비동기), 분석(순수 함수 + API 주입), 캐시, 내보내기, 도구 등록 모듈을 나눈다. 도구 입출력 JSON은 Node 버전과 같은 camelCase 키를 쓰고 내부 객체는 snake_case 데이터클래스다. 동작 기준은 Node 구현(태그 `node-v1`)과 Node 설계서이며, 테스트는 Node 테스트를 파일 단위로 옮긴다.

**Tech Stack:** Python ≥3.11, uv, hatchling, `mcp` 2.x(`MCPServer`), httpx, openpyxl, kiwipiepy, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-10-21-python-rewrite-design.md` (동작 기준: `docs/superpowers/specs/2026-10-16-book-brand-analysis-design.md` §1~§11)

## Global Constraints

- 작업 폴더는 worktree `<worktree>`, 브랜치 `python-rewrite`. **푸시와 `main` 변경은 하지 않는다.** 커밋 작성자는 `neneungyul2 <neneungyul2@gmail.com>`(저장소 설정됨). 커밋 메시지 끝에 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- 파이썬 3.11 이상. 확인된 대상: 3.12, 3.14.6. `requires-python = ">=3.11"`.
- `mcp` 2.x: `from mcp.server.mcpserver import MCPServer` (`mcp.server.fastmcp`는 없다).
- NAVER API HUB 키만 지원. 환경변수 `NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY`. Base URL `https://naverapihub.apigw.ntruss.com`, 헤더 `X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY`.
- 그 밖의 환경변수(이름은 Node와 같다): `NAVER_EXPORT_DIR`(기본 `<cwd>/exports`), `NAVER_CACHE_DIR`(기본 `<홈>/.naver-search-mcp/cache`), `NAVER_CACHE_TTL_HOURS`(기본 24), `NAVER_TOOLS_ALLOW`(쉼표 구분, 비면 전체; 목록에 없는 이름이 섞이면 stderr 경고).
- 기본값: `maxCalls` 30, `maxPostsPerBrand` 100(최대 1000), `queriesPerBrand` 1(최대 3), `topCandidates` 30, `baselinePosts` 100(10~300), `genericRate` 0.15, 낮은 정밀도 임계값 1, 쇼핑 별칭 시도 2회, 쇼핑 키워드 그룹당 1개, 쇼핑 그룹 5개, 검색어 트렌드 그룹 5개·그룹당 키워드 20개, 검색 `display` 100·`start` ≤ 1000.
- **stdout에는 MCP 프로토콜만** 나간다. 로그와 경고는 stderr. 모든 파일 입출력은 `encoding="utf-8"`를 명시한다 (Windows 기본 인코딩에 기대지 않는다).
- 도구 이름과 인자 이름은 Node 버전과 같다(camelCase 인자 포함, 예: `startDate`, `timeUnit`, `exportAs`; `find_category`만 `max_results`). 결과 JSON 키도 Node와 같은 camelCase다(`callsUsed`, `estimatedCallsMax`, `lowPrecision`, `comparableFrom` 등).
- Node 소스는 태그 `node-v1`에서 읽는다: `git show node-v1:<경로>` (Task 1에서 작업 폴더의 Node 파일을 지운 뒤에도 읽을 수 있다).
- 테스트 실행: `uv run pytest`. 라이브 테스트는 `@pytest.mark.live`이며 `NAVER_LIVE_TEST=1`일 때만 실행, 기본은 건너뜀. 의존성 설치/실행은 `uv run`(별도 가상환경 직접 만들지 않는다).
- 이식 규칙: Node 테스트 파일 하나 → 파이썬 테스트 파일 하나, **해당되는 모든 케이스 포함**. 이식하지 않는 케이스는 `docs/superpowers/parity.md`에 파일별로 "이식함/대체함/해당 없음(이유)"로 적는다 (각 Task가 자기 몫을 추가).
- 공개 저장소가 될 코드이므로 샘플과 문서에 개인 정보, 제3자 글, API 키를 넣지 않는다. `.env`는 gitignore.

## Review Focus

- 환경변수 없이 서버를 띄우면 stdout에는 아무것도 쓰지 않고 stderr 오류와 비정상 종료 코드로 끝나야 한다. (Task 11)
- Windows 기본 인코딩(cp949)에서도 한글 브랜드명이 캐시, CSV, xlsx, 도구 결과 JSON에서 깨지지 않아야 한다. (Task 6, 10)
- kiwipiepy 모델 로딩이 서버 시작과 `import`를 늦추지 않아야 한다 (처음 형태소 분석이 필요할 때 한 번만 로드). (Task 9, 11)
- 도구 스키마의 인자 이름과 타입이 Node와 같고, 잘못된 타입(예: `ages`에 숫자)은 이해할 수 있는 오류가 나야 한다. (Task 12)
- `.env`가 이미 설정된 환경변수를 덮어쓰지 않고, 키가 로그와 오류 메시지에 나오지 않아야 한다. (Task 2)

## 파일 구조

```
pyproject.toml, .env.example, .gitignore
src/ne_naver_api_mcp/
  __init__.py
  config.py        # 자격증명 + .env 로딩
  endpoints.py     # HUB URL/헤더
  errors.py        # API 오류 메시지 형식
  dates.py         # "today"(KST) 처리
  client.py        # NaverApiClient (httpx 비동기)
  categories.py    # find_category
  data/categories.json
  cache.py         # FileCache, CallCounter, cached_call
  analysis/{brand,budget,rescale,compare_trend,mentions,candidates,tokenizer}.py
  export.py
  tool_filter.py
  tools/{search,datalab,category,analysis}.py   # 도구 등록
  server.py        # create_server(), main()
tests/  (+ fixtures/*.json 유지, live/)
scripts/record_fixtures.py
docs/superpowers/parity.md
```

---

### Task 1: 프로젝트 골격과 MCP SDK 2.x 확인 (Node 파일 제거)

**Files:**
- Delete: `src/**/*.ts`, `tests/*.js`, `tests/live/*.js`, `package.json`, `package-lock.json`, `tsconfig.json`, `Dockerfile`, `.dockerignore`, `RELEASE_NOTES.md`, `scripts/*.mjs`
- Create: `pyproject.toml`, `src/ne_naver_api_mcp/__init__.py`, `src/ne_naver_api_mcp/server.py`, `tests/test_smoke.py`, `docs/superpowers/parity.md`
- Modify: `.gitignore`(`.venv/`, `__pycache__/`, `.pytest_cache/`, `.cache/` 유지), `.env`(Node 폴더 `<node-project>\.env`에서 복사; 커밋 금지)
- Keep: `LICENSE`, `README*.md`(Task 14에서 다시 씀), `docs/`, `data/categories.json`(→ Task 5에서 패키지 안으로 이동), `tests/fixtures/`, `skills/`(Task 14)

**Interfaces:**
- Produces:
  - `ne_naver_api_mcp.server.create_server() -> MCPServer` (이 Task에서는 도구 없이 이름 "ne-naver-api-mcp"로 생성)
  - `ne_naver_api_mcp.server.main() -> None` — stdio로 서버 실행. `pyproject.toml`의 콘솔 스크립트 `ne-naver-api-mcp = "ne_naver_api_mcp.server:main"`.
  - 빌드 백엔드 hatchling, `[tool.pytest.ini_options]`에 `asyncio_mode = "auto"`, `markers = ["live: 실제 API 호출 (NAVER_LIVE_TEST=1)"]`, 라이브 마커가 `NAVER_LIVE_TEST`가 없으면 자동 skip(conftest).
  - 의존성: `mcp>=2,<3`, `httpx`, `openpyxl`, `kiwipiepy`; dev: `pytest`, `pytest-asyncio`.

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/test_smoke.py`): MCP 클라이언트(SDK의 stdio 클라이언트)로 `uv run ne-naver-api-mcp`를 자식 프로세스로 띄워 `initialize` 후 `list_tools()`가 성공하고 서버 이름이 `"ne-naver-api-mcp"`임을 확인한다. 도구 목록은 이 Task에서는 빈 목록이어도 된다.
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_smoke.py -v` / Expected: FAIL (패키지/스크립트 없음)
- [ ] **Step 3: Node 파일 제거, `pyproject.toml`과 `server.py` 구현.** 먼저 `git show node-v1:src/index.ts`로 서버 이름 등을 확인. MCP SDK 2.x의 `MCPServer` 생성, 도구 등록 데코레이터, stdio 실행 방법은 설치된 SDK의 문서/소스(`https://py.sdk.modelcontextprotocol.io/v2/`)로 확인하고, 확인한 사용법을 `docs/superpowers/parity.md` 맨 위 "SDK 메모"에 3~5줄로 적는다. `.env`를 복사한다(`git check-ignore -v .env`로 무시되는지 확인).
- [ ] **Step 4: 통과 확인.** Run: `uv run pytest -v` / Expected: PASS
- [ ] **Step 5: 로컬 uvx 확인.** Run: `uvx --from . ne-naver-api-mcp` 를 stdin이 닫힌 상태로 실행 / Expected: 오류 없이 시작하고 종료 (stdout에 프로토콜 외 출력 없음)
- [ ] **Step 6: Commit.** `git add -A && git commit -m "build: replace Node project with a uv Python project skeleton"` (`git status`로 `.env`가 포함되지 않았는지 먼저 확인)

---

### Task 2: 자격증명, 엔드포인트, 오류 형식, 날짜 (Node 파일 4개 이식)

**Files:**
- Create: `src/ne_naver_api_mcp/{config,endpoints,errors,dates}.py`
- Test: `tests/test_config.py`, `tests/test_endpoints.py`, `tests/test_errors.py`, `tests/test_dates.py`
- Modify: `docs/superpowers/parity.md`

**Interfaces:**
- Produces:
  - `config.py`: `@dataclass(frozen=True) Credentials(client_id: str, client_secret: str)`; `resolve_credentials(env: Mapping[str, str | None]) -> Credentials`; `load_dotenv_if_present(path: Path | None = None, env: MutableMapping[str, str] | None = None) -> None` (기본 `Path.cwd() / ".env"`, **이미 값이 있는 환경변수는 덮어쓰지 않는다**, 빈 값은 설정으로 치지 않는다, UTF-8, `KEY=VALUE`와 `#` 주석, 따옴표 제거). 외부 라이브러리 없이 구현.
  - `endpoints.py`: `BASE_URL`, `SEARCH_BASE = f"{BASE_URL}/search/v1"`, `TREND_URL = f"{BASE_URL}/search-trend/v1/search"`, `SHOPPING_BASE = f"{BASE_URL}/shopping/v1"`, `AUTH_HEADER_NAMES = ("X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY")`.
  - `errors.py`: `format_api_error(url: str, status: int | None, body: object) -> str` — `"[NAVER API HUB] HTTP {status} — {url}\n{body}"`, 응답 없음이면 `no response`, 401이면 HUB 키 확인 안내 한 줄.
  - `dates.py`: `korean_today(now: datetime | None = None) -> str`, `resolve_date(s: str) -> str`, `resolve_date_range(start: str, end: str) -> tuple[str, str]` (`"today"`는 KST, `yyyy-mm-dd` 검증, 그 외 `ValueError("Invalid date format ...")`).
  - 오류 클래스 `CredentialsError(Exception)`.

- [ ] **Step 1: 실패하는 테스트 작성.** Node 테스트를 `git show node-v1:tests/{credentials,naver-api-endpoints,naver-api-error,date-utils}.test.js`로 읽고 HUB에 해당하는 케이스를 모두 옮긴다. 추가/대체 케이스:
  - `test_resolve_credentials_ok`, `test_missing_both_raises_with_setup_guide`(메시지에 두 변수 이름), `test_half_hub_key_names_missing_one`(`NCP_APIGW_API_KEY` 없음을 지목), `test_legacy_only_raises_with_hub_guidance`(`NAVER_CLIENT_ID/SECRET`만 있으면 `CredentialsError`, 메시지에 `NCP_APIGW_API_KEY_ID`와 "개발자센터 키는 지원하지 않습니다"), `test_whitespace_values_are_trimmed`.
  - `.env`: `test_dotenv_does_not_override_existing_env`, `test_dotenv_empty_value_is_not_set`, `test_dotenv_missing_file_is_noop`, `test_dotenv_reads_utf8_and_comments_and_quotes`.
  - `test_error_message_never_contains_key`: `format_api_error`에 키가 들어간 body를 넘기지 않는 한 키 값이 출력에 없음을 확인 (호출부가 키를 넘기지 않는다는 계약).
  - `test_korean_today_ignores_host_timezone`: `now`를 UTC 15:30(= KST 다음 날 00:30)으로 주입해 KST 날짜가 나오는지.
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_config.py tests/test_endpoints.py tests/test_errors.py tests/test_dates.py -v` / Expected: FAIL (모듈 없음)
- [ ] **Step 3: 네 모듈 구현.** Node 코드(`git show node-v1:src/config/credentials.ts`, `src/clients/naver-api-endpoints.ts`, `naver-api-error.ts`, `src/utils/date.utils.ts`)의 동작을 따르되 legacy 분기는 위 규칙으로 대체. KST는 `zoneinfo.ZoneInfo("Asia/Seoul")`(Windows에서 `tzdata` 필요하면 의존성에 추가).
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: parity.md에 네 파일의 이식 결과(legacy 케이스는 "대체함")를 적고 Commit.** `git commit -m "feat: port credentials, endpoints, error format and date helpers"`

---

### Task 3: HTTP 클라이언트 (naver-search-client 이식)

**Files:**
- Create: `src/ne_naver_api_mcp/client.py`
- Test: `tests/test_client.py`
- Modify: `docs/superpowers/parity.md`

**Interfaces:**
- Consumes: Task 2 `Credentials`, `endpoints`, `format_api_error`.
- Produces: `class NaverApiClient`
  - `__init__(self, credentials: Credentials, *, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 30.0)`
  - `async aclose(self) -> None`
  - `async search(self, type: str, params: dict) -> dict` — `GET {SEARCH_BASE}/{type}` (`type` ∈ news, encyc, blog, webkr, image, kin, cafearticle, local)
  - `async search_trend(self, req: dict) -> dict` — `POST TREND_URL`
  - 쇼핑(모두 `POST`): `shopping_category(req)` → `/categories`, `shopping_by_device` → `/category/device`, `shopping_by_gender` → `/category/gender`, `shopping_by_age` → `/category/age`, `shopping_keywords` → `/category/keywords`, `shopping_keyword_by_device` → `/category/keyword/device`, `shopping_keyword_by_gender` → `/category/keyword/gender`, `shopping_keyword_by_age` → `/category/keyword/age` (모두 `async (self, req: dict) -> dict`).
  - `class ApiError(Exception)` — 메시지는 `format_api_error` 결과.
  - 이 클라이언트는 Task 8~9의 `AnalysisApi` 프로토콜(`search_trend`, `shopping_keywords`, `search`)을 구조적으로 만족한다.

- [ ] **Step 1: 실패하는 테스트 작성.** `git show node-v1:tests/naver-search-client.test.js`의 해당 케이스를 옮기되 `httpx.MockTransport`로 요청을 가로챈다. 케이스: `test_headers_carry_hub_auth_names_only`(HUB 헤더 두 개, `Content-Type: application/json`), `test_search_uses_get_with_params_and_path`(경로 `/search/v1/blog`, 쿼리 `query`, `display`, `start`, `sort`), `test_trend_and_each_shopping_endpoint_path_and_method`(9개 경로를 표로 검증), `test_http_error_becomes_api_error_with_status_and_url`, `test_network_error_message_is_preserved`(타임아웃/연결 실패도 원인 메시지 유지), `test_error_message_does_not_contain_credentials`(헤더 값이 메시지에 없음), `test_none_params_are_dropped`(값이 `None`인 쿼리 파라미터는 보내지 않음).
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_client.py -v` / Expected: FAIL
- [ ] **Step 3: `NaverApiClient` 구현** (`httpx.AsyncClient` 하나를 재사용). Node: `git show node-v1:src/clients/naver-api-core.client.ts naver-search.client.ts`.
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: parity.md 갱신(싱글톤/초기화 전 오류 케이스는 "해당 없음: 인스턴스를 직접 만든다") 후 Commit.** `git commit -m "feat: port the HUB HTTP client"`

---

### Task 4: 실제 키로 도구 후보 엔드포인트 확인 (관문)

**Files:**
- Create: `tests/live/test_hub_endpoints.py`
- Modify: `docs/superpowers/specs/2026-10-21-python-rewrite-design.md`(§8 아래에 결과 기록), `docs/superpowers/parity.md`
- Test: `tests/live/test_hub_endpoints.py`

**Interfaces:**
- Produces: 검증 결과 표. 이후 Task 11이 이 표에서 **유효한 도구만** 등록한다. 결과는 `src/ne_naver_api_mcp/endpoints.py`에 `UNVERIFIED_OR_INVALID: frozenset[str]`(등록하지 않을 검색 타입 이름)로 반영한다 (기본 빈 집합).

> `.env`의 키가 필요하다 (Task 1에서 복사). 호출은 합계 25회 이내. 키가 없으면 여기서 멈추고 사용자에게 요청한다.

- [ ] **Step 1: 라이브 테스트 작성** (`@pytest.mark.live`; Node `tests/live/hub.live.test.js`의 5개 케이스를 옮기고 추가): 8개 검색 타입(`news`, `encyc`, `blog`, `webkr`, `image`, `kin`, `cafearticle`, `local`) 각각 `query="그래머인사이드", display=1`로 호출해 최상위 키에 `items`가 있는지(타입별 파라미터 제약은 응답 오류 메시지를 기록), 쇼핑 8개 경로가 200을 돌려주는지(분야 `50005951`, 기간 2025-01-01~2025-06-30, month), 블로그 `postdate`가 8자리, 카페/웹에 날짜 필드 없음, 쇼핑 그룹 5개 허용·6개 400, `param` 2개 400.
- [ ] **Step 2: 실행.** Run: `NAVER_LIVE_TEST=1 uv run pytest tests/live -v` (Windows PowerShell에서는 `$env:NAVER_LIVE_TEST=1`) / Expected: 기존에 확인한 항목은 PASS. 새로 확인하는 검색 타입 중 실패한 것은 이유(HTTP 상태와 오류 메시지 첫 줄)를 기록한다. 실패해도 이 Step의 목적은 결과를 얻는 것이다.
- [ ] **Step 3: 결과 반영.** 스펙 §8 아래 "확인 결과(2026-MM-DD)" 표에 타입별 유효/무효를 적고, 무효인 타입이 있으면 `UNVERIFIED_OR_INVALID`에 넣고 live 테스트에서 그 타입의 기대를 "무효"로 바꾼다. 라이브 테스트가 모두 통과하도록 만든다.
- [ ] **Step 4: 기본 실행에서 건너뛰는지 확인.** Run: `uv run pytest -q` / Expected: live 테스트는 skipped로 표시
- [ ] **Step 5: Commit.** `git commit -m "test: live endpoint verification for all search types"`

---

### Task 5: find_category (category.handlers 이식)

**Files:**
- Move: `data/categories.json` → `src/ne_naver_api_mcp/data/categories.json`
- Create: `src/ne_naver_api_mcp/categories.py`
- Test: `tests/test_categories.py`
- Modify: `pyproject.toml`(데이터 파일이 휠에 포함되도록 hatch include), `docs/superpowers/parity.md`

**Interfaces:**
- Produces:
  - `load_categories() -> list[dict]` — `importlib.resources`로 패키지 데이터를 읽고(UTF-8) 프로세스 안에서 캐시. 파일이 없으면 `[]` + stderr 경고.
  - `find_category(query: str, max_results: int = 10) -> dict` — Node `findCategoryHandler`의 결과 형태 그대로: 결과 없으면 `{"message": ..., "suggestions": [...]}`, 있으면 `{"message", "total_found", "categories": [{"code","category","match_type","score","levels":{"대분류","중분류","소분류","세분류"}}], "next_steps": {...}}`.
  - 점수: 정확일치 100/시작 80/포함 60/유사(레벤슈타인 유사도 > 0.6이면 `floor(sim*40)`) + 단계 보너스(대분류 50, 중분류 30, 소분류 20, 세분류 10), 정렬은 점수 내림차순 후 코드 오름차순(문자열 비교).

- [ ] **Step 1: 실패하는 테스트 작성.** Node에는 이 핸들러의 전용 테스트가 없으므로(`git show node-v1:src/handlers/category.handlers.ts`가 기준) 동작 테스트를 새로 쓴다: `test_exact_match_scores_100_plus_level_bonus`("패션의류"/"도서" 등 실제 대분류로 `match_type`에 "정확일치(대분류)"와 점수 150), `test_starts_with_and_contains_scores`, `test_fuzzy_match_requires_similarity_over_0_6`, `test_sorted_by_score_then_code`, `test_max_results_limit`, `test_no_result_returns_message_and_suggestions`, `test_book_grammar_category_is_found`("영어" 검색 결과에 코드 `50005951`("문법/독해/작문")이 포함됨), `test_data_loaded_from_package_resources`(작업 폴더와 무관, `monkeypatch.chdir(tmp_path)`).
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_categories.py -v` / Expected: FAIL
- [ ] **Step 3: 구현.** 레벤슈타인은 자체 구현(외부 의존성 추가 금지).
- [ ] **Step 4: 통과 확인.** Run: `uv run pytest tests/test_categories.py -v` / Expected: PASS. 그리고 `uv build`로 만든 휠에 `data/categories.json`이 들어 있는지 `python -m zipfile -l dist/*.whl`로 확인.
- [ ] **Step 5: Commit.** `git commit -m "feat: port find_category with bundled category data"`

---

### Task 6: 캐시와 호출 예산 (file-cache, budget 이식)

**Files:**
- Create: `src/ne_naver_api_mcp/cache.py`, `src/ne_naver_api_mcp/analysis/__init__.py`, `src/ne_naver_api_mcp/analysis/budget.py`
- Test: `tests/test_cache.py`, `tests/test_budget.py`

**Interfaces:**
- Produces:
  - `cache.py`: `cache_key(endpoint: str, params: object) -> str` (키 순서 무관, sha256 hex); `class FileCache(directory: Path, ttl_ms: int, now: Callable[[], float] | None = None)` with `get(key: str) -> object | None`, `set(key: str, value: object) -> None` (**응답 값과 저장 시각만 저장**, UTF-8, 손상/만료 파일은 `None`); `default_cache() -> FileCache`(환경변수 `NAVER_CACHE_DIR`, `NAVER_CACHE_TTL_HOURS` 사용); `@dataclass class CallCounter: used: int = 0; hit: int = 0`; `async cached_call(cache: FileCache, counter: CallCounter, endpoint: str, params: object, fn: Callable[[], Awaitable[T]]) -> T`.
  - `budget.py`: `DEFAULT_MAX_CALLS = 30`; `class BudgetExceededError(Exception)` with `estimated: int`, `max_calls: int` (메시지에 `confirm` 안내); `check_budget(estimated: int, max_calls: int | None = None, confirm: bool = False) -> None`.

- [ ] **Step 1: 실패하는 테스트 작성.** `git show node-v1:tests/file-cache.test.js tests/budget.test.js`의 케이스를 모두 옮긴다 (`tmp_path` 사용, `now` 주입으로 TTL). 추가: `test_cache_stores_korean_values_as_utf8`(한글 값 저장 후 `path.read_bytes().decode("utf-8")`로 확인, 기본 인코딩 비의존), `test_cache_file_never_contains_params_or_secret`(`params`에 `SECRET-KEY-123`을 넣어도 캐시 파일에 없음), `test_none_value_is_not_confused_with_miss`(`None` 응답은 저장하지 않는다 — 값이 `None`이면 `set`이 무시).
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_cache.py tests/test_budget.py -v` / Expected: FAIL
- [ ] **Step 3: 구현** (Node `src/cache/file-cache.ts`, `src/analysis/budget.ts`).
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: parity.md 갱신 후 Commit.** `git commit -m "feat: port file cache and call budget guard"`

---

### Task 7: 브랜드 모델과 상대 지수 환산 (brand, rescale 이식)

**Files:**
- Create: `src/ne_naver_api_mcp/analysis/brand.py`, `src/ne_naver_api_mcp/analysis/rescale.py`
- Test: `tests/test_brand.py`, `tests/test_rescale.py`

**Interfaces:**
- Produces:
  - `brand.py`: `@dataclass(frozen=True) Brand(name: str, aliases: tuple[str, ...] = ())`; `MAX_KEYWORDS_PER_BRAND = 20`; `brand_keywords(brand: Brand) -> list[str]` (공백 제거·빈 값 제거·대소문자 무시 중복 제거, 20개 초과 시 `ValueError("... 최대 20개 ...")`); `validate_brands(brands: Sequence[Brand]) -> None` (키워드 검증 + 빈 이름이면 `ValueError("브랜드 이름이 비어 있습니다 ...")`); `matches_brand(text: str, brand: Brand) -> bool` (공백/대소문자 무시 부분 일치); `class BrandInput(pydantic.BaseModel)` with `name: str = Field(min_length=1)`, `aliases: list[str] = []`, 메서드 `to_brand() -> Brand`.
  - `rescale.py`: `@dataclass SeriesPoint(period: str, ratio: float)`; `BatchResult = dict[str, list[SeriesPoint]]`; `@dataclass ScaledSeries(brand: str, points: list[SeriesPoint], low_precision: bool)`; `class AnchorError(Exception)`; `plan_batches(brands: list[str], anchor: str, slots_per_call: int) -> list[list[str]]`; `estimate_trend_calls(brand_count: int, slots_per_call: int) -> int`; `rescale(anchor: str, batches: list[BatchResult], low_threshold: float = 1.0) -> list[ScaledSeries]`; `pick_median_anchor(scaled: list[ScaledSeries]) -> str`.
  - 의미: Node `src/analysis/rescale.ts`와 같다 — 배치 b의 환산 계수 `k_b = Σ(첫 배치 기준 값) / Σ(배치 b 기준 값)`; 배치가 하나면 환산하지 않고 기준 값 0도 허용; 다중 배치에서 기준 합이 0/누락이면 `AnchorError`("기준 브랜드" 포함); 다중 배치에서 해당 배치 기준의 최댓값이 임계값 미만이면 그 배치 브랜드를 `low_precision`으로; `pick_median_anchor`는 합계가 0보다 큰 브랜드만(없으면 `AnchorError`), 짝수면 아래쪽 중앙값.

- [ ] **Step 1: 실패하는 테스트 작성.** `git show node-v1:tests/brand.test.js tests/rescale.test.js`의 케이스를 **모두** 옮긴다 (숫자 그대로: 기준 합 비율 환산 `[200,100]`, `plan_batches(["A".."F"], "A", 5) == [["A","B","C","D","E"],["A","F"]]`, `estimate_trend_calls` 1/5/6/10 → 1/1/2/3 등). `BrandInput`: `test_brand_input_defaults_aliases_to_empty`, `test_brand_input_rejects_empty_name`.
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_brand.py tests/test_rescale.py -v` / Expected: FAIL
- [ ] **Step 3: 구현** (Node `src/analysis/brand.ts`, `rescale.ts`).
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: parity.md 갱신 후 Commit.** `git commit -m "feat: port brand model and relative index rescaling"`

---

### Task 8: 브랜드 비교 트렌드 (compare-trend 이식)

**Files:**
- Create: `src/ne_naver_api_mcp/analysis/compare_trend.py`
- Test: `tests/test_compare_trend.py`

**Interfaces:**
- Consumes: Task 2 `resolve_date_range`; Task 6 `FileCache`, `CallCounter`, `cached_call`, `check_budget`, `DEFAULT_MAX_CALLS`; Task 7 전부.
- Produces:
  - `class AnalysisApi(Protocol)`: `async search_trend(self, req: dict) -> dict`, `async shopping_keywords(self, req: dict) -> dict`, `async search(self, type: str, params: dict) -> dict`.
  - 상수 `SEARCH_SLOTS_PER_CALL = 5`, `SHOPPING_SLOTS_PER_CALL = 5`, `SHOPPING_KEYWORDS_PER_BRAND = 1`, `SHOPPING_ALIAS_TRIES = 2`.
  - `@dataclass CompareInput(brands: list[Brand], source: Literal["search","shopping"], start_date: str, end_date: str, time_unit: Literal["date","week","month"], category: str | None = None, anchor: str | None = None, device: str | None = None, gender: str | None = None, ages: list[str] | None = None, max_calls: int | None = None, confirm: bool = False, dry_run: bool = False)`.
  - `@dataclass CompareResult(...)` + `to_dict() -> dict` — camelCase 키: `source, anchor, reanchored, series[{brand, points[{period, ratio}], lowPrecision}], callsUsed, cacheHits, estimatedCalls, estimatedCallsMax, warnings, limitations, dryRun`.
  - `async compare_brand_trend(input: CompareInput, api: AnalysisApi, cache: FileCache, counter: CallCounter | None = None) -> CompareResult`.
  - 동작은 Node `src/analysis/compare-trend.ts`(태그 `node-v1`)와 Node 설계서 §5, §9, §11 및 파이썬 설계서 §5 체크리스트 1~6, 9와 같다: 기준 지정/자동, 데이터 없는 기준 대체, 정밀도 경고, 자동 재기준(예산 이내·배치 2개 이상·0만 있는 브랜드는 트리거 제외·비슷한 크기끼리 묶기), 쇼핑 별칭 순차 시도, `dry_run`, `check_budget`, 중복 이름/검증 오류, `limitations` 3문장(Node와 같은 문구).

- [ ] **Step 1: 실패하는 테스트 작성.** `git show node-v1:tests/compare-trend.test.js`의 **모든** 케이스를 옮긴다 (가짜 API는 요청 안 최댓값을 100으로 정규화하는 `make_api(world)`와 키워드로 조회하는 `make_keyword_api(world_by_keyword)` 두 가지; 기대 숫자 동일: 6개 브랜드 `F ≈ 2.5`, 재기준 후 `anchor == "E"`와 호출 배치 `["E","A","B","C","F"]`, `["E","D"]`, `confirm`이어도 `callsUsed == 2`와 `estimatedCallsMax == 4`, 쇼핑 별칭 `calls == 2`와 `ratio == 40` 등). 비동기 테스트는 `async def test_...`.
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_compare_trend.py -v` / Expected: FAIL
- [ ] **Step 3: 구현.** 요청 dict 키는 API 사양 그대로(`startDate`, `endDate`, `timeUnit`, `keywordGroups`, `category`, `keyword` 등).
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: parity.md 갱신 후 Commit.** `git commit -m "feat: port brand comparison trend"`

---

### Task 9: 언급 수집·집계와 후보 추출 (mentions, candidates, tokenizer)

**Files:**
- Create: `src/ne_naver_api_mcp/analysis/{mentions,candidates,tokenizer}.py`
- Test: `tests/test_mentions.py`, `tests/test_candidates.py`, `tests/test_tokenizer.py`

**Interfaces:**
- Consumes: Task 6 캐시, Task 7 `Brand`, `matches_brand`, Task 8 `AnalysisApi`.
- Produces:
  - `mentions.py`: `MentionSource = Literal["blog","cafearticle","webkr"]`; `@dataclass Post(source: MentionSource, title: str, description: str, link: str, date: str | None = None)`; `@dataclass KeptPost(Post)` + `brands: list[str]`; `strip_html(s: str) -> str`(태그 제거, 엔티티 복원, `&amp;`는 마지막, 공백 정리); `normalize_post(source, raw: dict) -> Post`(`postdate` 8자리 → `yyyy-mm-dd`, 그 외 `None`); `async collect_posts(api, source, query, max_posts, cache, counter) -> tuple[list[Post], int]`(sort=date, display=100, start 1,101,…≤901, 링크 중복 제거, 빈 페이지/`len(items)<100`이면 중단, `cached_call` 사용); `filter_by_brands(posts, brands) -> tuple[list[KeptPost], int]`; `monthly_counts(kept) -> tuple[list[dict], dict[str,int]]`(행 키 `month, brand, source, count`, `undated`는 소스별 정수); `estimate_mention_calls(brands, sources, queries_per_brand, max_posts) -> int`.
  - `tokenizer.py`: `Tokenizer = Callable[[str], list[str]]`; `regex_tokenizer(text: str) -> list[str]`(Node 규칙: `[가-힣A-Za-z0-9]{2,}`, 소문자); `class KiwiTokenizer(user_words: Iterable[str] = ())`(호출 가능; **첫 호출 때 kiwipiepy를 import하고 모델을 로드**; 사용자 사전에 `user_words`를 `NNP`로 등록; 품사 `NNG`, `NNP`, `SL`, `XR`의 형태만, 소문자, 길이 ≥ 2); `default_tokenizer(brands: Sequence[Brand]) -> Tokenizer`(브랜드 키워드를 사용자 사전으로 넣은 `KiwiTokenizer`).
  - `candidates.py`: `@dataclass Candidate(term, total, by_brand: dict[str,int], examples: list[str], sources: list[str], baseline_rate: float | None = None, lift: float | None = None)` + `to_dict()`(camelCase `byBrand`, `baselineRate`, `lift`); `DEFAULT_STOPWORDS: frozenset[str]`(Node 목록); `DEFAULT_GENERIC_RATE = 0.15`; `extract_candidates(kept, brands, *, top: int = 30, stopwords: frozenset[str] | None = None, baseline: Sequence[Post] | None = None, generic_rate: float = 0.15, tokenize: Tokenizer = regex_tokenizer) -> list[Candidate]` — 글당 토큰 중복 제거, 숫자만/불용어/브랜드 키워드(전체와 공백 단위 단어)/브랜드명+조사(≤2자) 토큰 제외, 기준 비율 ≥ `generic_rate`인 단어 제외, `lift = total/len(kept)/max(rate, 1/(N+1))`, 정렬은 `total` 내림차순 후 사전순, 예시는 단어가 든 문장 조각 100자 이내 최대 3개.

- [ ] **Step 1: 실패하는 테스트 작성.**
  - `test_mentions.py`: `git show node-v1:tests/mentions.test.js`의 **모든** 케이스 이식 (`strip_html("<b>천일문</b> &quot;후기&quot; &amp; 정리") == '천일문 "후기" & 정리'`, `postdate` 형식 3종, 페이지 수 3·2·10, `maxPosts=150`이면 150건, 중복 링크, 캐시 재사용, `<b>`로 쪼개진 제목 매칭, 월별/undated, `estimate_mention_calls`=40).
  - `test_candidates.py`: `git show node-v1:tests/candidates.test.js`의 모든 케이스를 **`tokenize=regex_tokenizer`(기본값)로** 같은 입력·같은 기대값(`total`, `baseline_rate == 0.1`, `lift > 1`, `top` 정렬 등)으로 이식.
  - `test_tokenizer.py`: `test_regex_tokenizer_matches_node_rule`, `test_kiwi_strips_particles`(`"그래머인사이드는 좋아요"` → 결과에 `"그래머인사이드"`가 있고 `"그래머인사이드는"`은 없다), `test_kiwi_keeps_user_dictionary_brand_whole`(`KiwiTokenizer(["워크북"])`/`["NE능률"]`로 "워크북 NE능률 숙제"가 쪼개지지 않고 `"워크북"`, `"ne능률"` 포함), `test_kiwi_keeps_only_nouns_foreign_roots`(조사/어미/동사 제외), `test_kiwi_lowercases_english`(`"Grammar Inside"` → `"grammar"`, `"inside"`), `test_kiwi_is_lazy`(`KiwiTokenizer` 생성과 이 모듈 import만으로는 `"kiwipiepy" in sys.modules`가 거짓이고, 첫 호출 후에 참 — 서브프로세스로 검사), `test_extract_candidates_with_kiwi_tokenizer`(브랜드명+조사 글에서 조사가 붙은 토큰이 후보에 없고 "쎄듀" 같은 명사가 있음).
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_mentions.py tests/test_candidates.py tests/test_tokenizer.py -v` / Expected: FAIL
- [ ] **Step 3: 구현** (Node `src/analysis/mentions.ts`, `candidates.ts`). 결과 객체의 `to_dict()`는 Task 12의 도구 출력에서 쓴다.
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS (kiwipiepy 모델 로드 포함 소요 시간 30초 이내)
- [ ] **Step 5: parity.md 갱신(토크나이저 기반 후보 테스트는 "대체함: 정규식 토크나이저로 이식 + kiwi 별도 테스트") 후 Commit.** `git commit -m "feat: port mention collection and candidate extraction with a Korean tokenizer"`

---

### Task 10: xlsx/CSV 내보내기 (export 이식)

**Files:**
- Create: `src/ne_naver_api_mcp/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Produces: `Cell = str | int | float | None`; `@dataclass Sheet(name: str, columns: list[str], rows: list[list[Cell]])`; `@dataclass ExportResult(xlsx_path: str, csv_paths: list[str])` + `to_dict()`(`xlsxPath`, `csvPaths`); `sanitize_base_name(name: str) -> str`; `neutralize_formula(v: Cell) -> Cell`; `export_sheets(sheets: Sequence[Sheet], directory: Path, base_name: str) -> ExportResult`.
- 규칙은 Node `src/export/export.ts`와 같다: `\ / : * ? " < > |`·제어 문자·`..` 치환(백슬래시 포함), 비면 `"export"`; `=`, `+`, `-`, `@`, 탭, CR로 시작하는 **문자열** 셀은 앞에 `'`(숫자와 `None`은 그대로); CSV는 UTF-8 BOM, 쉼표/따옴표/개행 이스케이프, 헤더 포함 모든 셀 무력화; xlsx는 openpyxl, 시트 이름 금지 문자 `[ ] * ? : \ /` 치환·31자 이내·중복 시 `_2`; 결과 경로는 모두 `directory` 아래.

- [ ] **Step 1: 실패하는 테스트 작성.** `git show node-v1:tests/export.test.js`의 **모든** 케이스 이식 (`tmp_path`; xlsx는 `openpyxl.load_workbook`으로 다시 읽기). 백슬래시 케이스 포함: `sanitize_base_name("a\\b") == "a_b"`, `"..\\..\\evil"`, 시트 이름 `"가\\나"`. 추가: `test_writes_are_utf8_regardless_of_locale`(서브프로세스를 `PYTHONUTF8=0`, `PYTHONIOENCODING=cp949`로 실행해 한글 시트명/CSV가 올바르게 써지는지 확인), `test_existing_file_is_overwritten_not_error`(같은 이름 재실행).
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_export.py -v` / Expected: FAIL
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: parity.md 갱신 후 Commit.** `git commit -m "feat: port xlsx and csv export"`

---

### Task 11: 서버 조립, 도구 노출 필터, 시작 오류 처리

**Files:**
- Create: `src/ne_naver_api_mcp/tool_filter.py`
- Modify: `src/ne_naver_api_mcp/server.py`
- Test: `tests/test_tool_filter.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: Task 2 `resolve_credentials`, `load_dotenv_if_present`, `CredentialsError`; Task 3 `NaverApiClient`.
- Produces:
  - `tool_filter.py`: `parse_tool_allow_list(raw: str | None) -> set[str] | None`(빈 값/공백만이면 `None`); `class ToolRegistrar` — `__init__(self, server: MCPServer, allow: set[str] | None)`, `register(self, name: str, fn: Callable, description: str) -> None`(허용 목록에 없으면 등록하지 않음), `warn_unknown(self, known: set[str]) -> None`(허용 목록에 있는데 알려진 도구가 아닌 이름을 stderr에 경고).
  - `server.py`: `create_server(api: AnalysisApi-compatible client | None = None, *, allow: set[str] | None = None) -> MCPServer` — 각 `tools/*.py`의 `register_*_tools(registrar, client)`를 호출(이 Task에서는 모듈이 비어 있어도 됨); `main() -> None`: `.env` 로딩 → `resolve_credentials(os.environ)` → 실패하면 **stderr에 메시지를 쓰고 종료 코드 1** (stdout 출력 없음) → `NaverApiClient` 생성 → `NAVER_TOOLS_ALLOW` 적용 → stdio 실행. 종료 시 `aclose()`.

- [ ] **Step 1: 실패하는 테스트 작성.** `git show node-v1:tests/tool-filter.test.js`의 케이스 이식 + `ToolRegistrar` 케이스(허용된 이름만 등록, `None`이면 전부, 알려지지 않은 이름 경고가 stderr로). `test_server.py`(서브프로세스): `test_main_without_keys_exits_1_with_stderr_message_and_empty_stdout`(환경에서 `NCP_APIGW_*`·`NAVER_CLIENT_*` 제거, 작업 폴더에 `.env` 없음 → returncode 1, stdout 빈 문자열, stderr에 `NCP_APIGW_API_KEY_ID`), `test_main_with_legacy_keys_only_exits_1`, `test_main_starts_with_dummy_hub_keys_and_lists_tools_over_stdio`(더미 키로 MCP 클라이언트 연결 성공, 키 값 `dummysecretvalue`가 stdout/stderr 전체에 없음), `test_dotenv_in_cwd_is_used_when_env_missing`, `test_import_does_not_load_kiwipiepy`(`import ne_naver_api_mcp.server` 후 `"kiwipiepy" not in sys.modules`, 서브프로세스).
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_tool_filter.py tests/test_server.py -v` / Expected: FAIL
- [ ] **Step 3: 구현.** Task 1의 "SDK 메모"(도구 등록 방식)를 따른다.
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: Commit.** `git commit -m "feat: assemble the server with tool filtering and fail-fast startup"`

---

### Task 12: 도구 등록 — 검색·데이터랩·카테고리 18개와 분석 2개

**Files:**
- Create: `src/ne_naver_api_mcp/tools/{__init__,search,datalab,category,analysis}.py`
- Modify: `src/ne_naver_api_mcp/server.py`
- Test: `tests/test_tools_schema.py`, `tests/test_tools_behavior.py`, `tests/test_analysis_tools.py`
- Modify: `docs/superpowers/parity.md`

**Interfaces:**
- Consumes: Task 3 `NaverApiClient`, Task 4 `UNVERIFIED_OR_INVALID`, Task 5 `find_category`, Task 2 `resolve_date_range`, Task 6~10 전부, Task 11 `ToolRegistrar`.
- Produces:
  - `tools/search.py`: `register_search_tools(registrar: ToolRegistrar, client: NaverApiClient) -> None` — `search_webkr`, `search_news`, `search_blog`, `search_cafearticle`, `search_image`, `search_kin`, `search_encyc`, `search_local`(Task 4에서 무효로 판정된 것은 등록하지 않음). 인자: `query: str`, `display: int | None`, `start: int | None`, `sort: Literal["sim","date"] | None`(`search_local`은 `sort: Literal["random","comment"]`, `display ≤ 5`, `start ≤ 1`). 결과는 응답 dict를 JSON 문자열로(`json.dumps(..., ensure_ascii=False, indent=2)`).
  - `tools/datalab.py`: `register_datalab_tools(registrar, client)` — 9개. 인자 스키마는 `git show node-v1:src/schemas/datalab.schemas.ts`와 같다(`startDate`, `endDate`, `timeUnit`, `keywordGroups[{groupName, keywords}]`, 쇼핑 `category`(문자열 또는 `[{name, param[]}]`), `device`, `gender`, `ages`(`"10"`~`"60"` 문자열 열거), `keyword`). 날짜는 `resolve_date_range`로 `"today"` 처리 후 요청에 담는다. 각 핸들러가 클라이언트의 어느 메서드로 보내는지는 Node `src/handlers/datalab.handlers.ts`와 같다 (예: `datalab_shopping_by_device`는 `category`, `device`만 전달).
  - `tools/category.py`: `register_category_tools(registrar)` — `find_category(query: str, max_results: int = 10)`.
  - `tools/analysis.py`: `register_analysis_tools(registrar, api: AnalysisApi, cache: FileCache | None = None)` — `brand_compare_trend`(인자는 `CompareInput`과 `exportAs: str | None`, 결과는 `CompareResult.to_dict()` + 내보냈다면 `exported`, 내보내기 실패 시 `exportError`와 경고 추가), `brand_mentions`(인자 `brands`, `sources`(기본 `["blog","cafearticle"]`), `maxPostsPerBrand`(100), `queriesPerBrand`(1), `topCandidates`(30), `baselineQuery`, `baselinePosts`(100), `maxCalls`, `confirm`, `dryRun`, `exportAs`; 결과 키는 Node `src/analysis/tools.ts`와 같다: `dryRun, monthly(rows에 partial), comparableFrom, apiTotals(collected, oldestDate, truncated), collected, kept, excluded, candidates, baselineCollected, undated, callsUsed, cacheHits, estimatedCalls, warnings, limitations`; `baselineQuery`가 있으면 호출 수에 포함; `validate_brands`를 호출 전에 실행). `brand_mentions`의 후보 추출은 `default_tokenizer(brands)`를 쓰고(키워드 사전 등록), 내보내기 시트는 `월별언급`(부분집계 열 포함)·`후보`·`한계`, 비교 트렌드는 `트렌드`·`한계`.
  - `server.create_server`가 위 `register_*`를 모두 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성.**
  - `test_tools_schema.py`: MCP 클라이언트로 서버를 띄워(더미 키) `list_tools()` 결과를 검사: 도구 이름 집합이 (Task 4 결과 반영한) 기대 목록과 같다; `brand_compare_trend`의 입력 스키마 속성에 `brands`, `source`, `startDate`, `endDate`, `timeUnit`, `exportAs`가 있다; `datalab_shopping_by_age`의 `ages` 항목 열거가 `["10","20","30","40","50","60"]`; `search_blog`에 `query`, `display`, `start`, `sort`; `find_category`에 `max_results`; 각 도구 `description`이 비어 있지 않다. `test_wrong_type_gives_readable_error`: `ages`에 숫자 `[10]`을 넣어 호출하면 오류 응답(`isError`)이고 메시지에 `ages`가 언급된다. `test_tools_allow_env_limits_tools`(`NAVER_TOOLS_ALLOW=find_category,brand_mentions`면 두 개만).
  - `test_tools_behavior.py`: 가짜 클라이언트(`MockTransport` 또는 메서드 기록 객체)로 각 핸들러가 올바른 클라이언트 메서드/요청 dict를 만드는지(예: `datalab_search`에 `endDate="today"`가 KST 날짜로 치환, `datalab_shopping_keyword_by_gender`가 `category`, `keyword`, `gender`만 전달), 응답이 JSON 문자열(한글 비이스케이프)로 나오는지, 클라이언트 오류가 도구 오류로 전달되는지.
  - `test_analysis_tools.py`: `git show node-v1:tests/analysis-tools.test.js`의 **모든** 케이스 이식 (도구 2개 등록, dryRun, exportAs 파일 생성, 카페 날짜 없음 경고, 표본 잘림 경고, `comparableFrom`/`partial`, `maxPostsPerBrand` 기본 100, `baselineQuery`로 일반 단어 제거와 호출 수 2, 내보내기 실패 시 결과 유지, 20개 키워드 초과 사전 오류, 상한 초과 시 `confirm` 오류).
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_tools_schema.py tests/test_tools_behavior.py tests/test_analysis_tools.py -v` / Expected: FAIL
- [ ] **Step 3: 구현.** 도구 설명(이모지 + 영어 + 한글)은 `git show node-v1:src/index.ts`에서 그대로 옮기고, 분석 도구 설명은 `git show node-v1:src/analysis/tools.ts`에서 옮긴다. 도구 함수의 매개변수 이름은 camelCase를 유지한다 (`# ruff: noqa: N803`).
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS. 이어서 전체 `uv run pytest -q` / Expected: 전부 PASS, live는 skipped.
- [ ] **Step 5: parity.md 갱신(`removed-tools.test.js`는 "해당 없음: Node 클라이언트 내부 확인") 후 Commit.** `git commit -m "feat: register all search, datalab, category and analysis tools"`

---

### Task 13: 녹화 샘플 계약 테스트와 샘플 재녹화 스크립트

**Files:**
- Create: `scripts/record_fixtures.py`
- Test: `tests/test_fixtures.py`, `tests/live/test_live_contract.py`(Task 4 파일과 합쳐도 됨)
- Keep: `tests/fixtures/*.json`

**Interfaces:**
- Consumes: Task 3 클라이언트, Task 8~9 분석, Task 9 `normalize_post` 등.
- Produces: `scripts/record_fixtures.py` — 실제 API로 `tests/fixtures/`의 6개 파일(`search-blog`, `search-cafearticle`, `search-webkr`, `search-trend`, `shopping-keywords`, `shopping-param-limit-error`)을 다시 만든다. **제3자 글은 합성 텍스트로 치환**(제목 `<b>그래머인사이드</b> 샘플 제목 N`, 요약 `샘플 요약입니다. <b>그래머인사이드</b> 문법 교재 예시 문장 N.`, 링크·블로거/카페 이름·주소는 `example.invalid`)하고, 저장 전에 키 값이 포함되었는지 검사해 포함되면 중단한다. 샘플 파일의 현재 내용은 이미 이 규칙으로 정리되어 있으므로 이 Task에서 바꾸지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성** (`test_fixtures.py`, `git show node-v1:tests/fixtures.test.js`의 **8개 케이스 모두** 이식): 검색 응답 구조(최상위 키 5개, 블로그 `postdate` 8자리, 카페/웹 날짜 없음), 블로그 항목 정규화(`yyyy-mm-dd`, 태그 없음), 카페/웹 `date is None`, 수집+브랜드 필터(`<b>`로 감싸진 브랜드명), 검색어 트렌드 샘플로 단일 브랜드 최댓값 100과 호출 1회, **서버 제한을 흉내 낸 엄격한 쇼핑 가짜 API**(그룹 5개 초과 또는 `param` 2개 이상이면 녹화된 400 메시지로 거절)에 대해 별칭이 있는 브랜드로도 요청이 통과, 데이터 빈 키워드의 "데이터 없음" 경고, 서버 오류 메시지 전달과 키 비노출. 샘플 경로는 `Path(__file__).parent / "fixtures"`.
- [ ] **Step 2: 실패 확인.** Run: `uv run pytest tests/test_fixtures.py -v` / Expected: 모듈은 이미 있으므로 PASS여야 한다 — 먼저 통과하면 **변이 확인**을 한다: `client.py`/`compare_trend.py`에서 쇼핑 `param`을 별칭 전체로 보내도록 임시로 바꿔 `test_strict_shopping_api...`가 **실패**하는지 확인하고 되돌린다 (테스트가 문제를 잡는다는 증거).
- [ ] **Step 3: `scripts/record_fixtures.py` 작성** (Node `git show node-v1:scripts/record-fixtures.mjs`). 라이브 키가 있으면 실행해 파일이 같은 구조로 만들어지는지(내용은 날짜/수치가 다를 수 있음) 확인하되, 결과로 샘플을 바꾸지 말고 `git checkout -- tests/fixtures`로 되돌린다.
- [ ] **Step 4: 전체 확인.** Run: `uv run pytest -q` / Expected: PASS (live skipped). `NAVER_LIVE_TEST=1 uv run pytest tests/live -q` / Expected: PASS
- [ ] **Step 5: parity.md 갱신 후 Commit.** `git commit -m "test: recorded-fixture contract tests and a fixture recording script"`

---

### Task 14: 문서, 스킬, 설치 확인

**Files:**
- Modify: `README-ko.md`(다시 작성), `README.md`, `README-en.md`, `.env.example`, `skills/naver-search-mcp/SKILL.md`, `docs/superpowers/parity.md`
- Test: 없음 (명령 실행으로 검증)

**Interfaces:** 없음.

- [ ] **Step 1: README 작성.** `README-ko.md`를 먼저 완성하고 `README.md`, `README-en.md`는 같은 구조로 만든다. 포함: 포크 출처 안내(원본 isnow890, MIT, `LICENSE` 유지)와 "Node 버전은 태그 `node-v1`" 한 줄; 도구 20개(또는 Task 4 결과 반영) 목록과 검증일; 설치: Claude Code `claude mcp add ne-naver-api -s user -e NCP_APIGW_API_KEY_ID=... -e NCP_APIGW_API_KEY=... -e NAVER_EXPORT_DIR=... -- uvx --from git+https://github.com/neneungyul2/ne-naver-api-mcp ne-naver-api-mcp`, Claude Desktop `claude_desktop_config.json` 예시(`command: "uvx"`, `args: ["--from", "git+https://github.com/neneungyul2/ne-naver-api-mcp", "ne-naver-api-mcp"]`, `env`), 로컬 개발 `uv run`, 환경변수 표, 한도 조회 API 없음(콘솔 Usage Statistics), 분석 도구 사용법(`dryRun`, `maxCalls`, `confirm`, `exportAs`, `baselineQuery`, `comparableFrom`/`partial` 설명), 테스트 방법(`uv run pytest`, 라이브: `NAVER_LIVE_TEST=1`), `.env`는 작업 폴더에 있을 때만 읽고 환경변수가 우선. **GitHub 주소로 설치하는 방법은 "main이 파이썬 버전으로 바뀐 뒤"에만 동작한다**는 주의를 넣는다.
- [ ] **Step 2: `.env.example`과 `skills/naver-search-mcp/SKILL.md`를 uvx/HUB 기준으로 고친다** (node, npx, legacy 변수 언급 제거).
- [ ] **Step 3: `docs/superpowers/parity.md` 마무리**: Node 테스트 파일 18개 각각의 상태 표를 완성하고, 각 "해당 없음"에 이유가 있는지 확인한다.
- [ ] **Step 4: 설치 확인 (로컬).** Run: `uv build` / Expected: sdist와 휠 생성, 휠에 `categories.json` 포함. Run: `uvx --from . ne-naver-api-mcp` (더미 키 환경변수, stdin 닫음) / Expected: 오류 없이 시작/종료. 실제 키가 있으면 MCP 클라이언트 스크립트로 `find_category`와 `brand_compare_trend`(`dryRun`)를 호출해 결과를 확인한다.
- [ ] **Step 5: 전체 검증.** Run: `uv run pytest -q` / Expected: 전부 PASS(live skipped), `git status`가 깨끗하고 `.env`가 추적되지 않음(`git ls-files | grep -i "^\.env$"`가 비어 있음), 추적 파일에 개인 이메일 계정명, 로컬 절대 경로, 실제 API 키 값이 없음(`.env`의 키 값을 `git grep -F`로 전체 이력에서 검색해 0건).
- [ ] **Step 6: Commit.** `git commit -m "docs: Python/uvx documentation, skill and parity report"`

---

## Self-Review

- **스펙 커버리지:** §2 목표(도구 20개 → Task 5, 12; 동작 동일 → Task 6~10; 형태소 → Task 9; uvx → Task 1, 14), §3 제약(Python/SDK 2.x/환경변수 → Global Constraints, Task 1·2), §4 도구 목록 → Task 4·12, §5 체크리스트 1~6·9 → Task 7·8·12, 7 → Task 9·12, 8 → Task 10, §6 차이점(후보/`.env`/설치) → Task 2·9·14, §7 저장소 전략 → Global Constraints와 Task 1, §8 검증 → Task 4·11·12·14, §10 판단 6개 → legacy 오류(Task 2·11), 토크나이저 주입(Task 9), 키 복사(Task 1), 로컬 uvx(Task 1·14), 파일 처리(Task 1·13·14), 테스트 기준(규칙과 parity.md).
- **스펙 §8의 "uvx --from git+" 확인은 완료 조건이 아니며** README에 사용 가능 시점을 적는 것으로 대신한다(스펙 §10-4).
- **타입 일관성:** `AnalysisApi`(Task 8)를 Task 9·12가 쓰고 `NaverApiClient`가 만족한다(`search_trend`, `shopping_keywords`, `search`). `Brand`/`BrandInput`(Task 7)과 `ScaledSeries.low_precision` ↔ 출력 `lowPrecision`(Task 8 `to_dict`). `Sheet`/`ExportResult`(Task 10)를 Task 12가 쓴다. `ToolRegistrar`(Task 11)를 Task 12가 쓴다.
- **Review Focus 매핑:** stdout 오염·시작 오류(Task 11), 인코딩(Task 6·10), kiwi 지연 로딩(Task 9·11), 스키마·타입 오류(Task 12), `.env` 우선순위와 키 비노출(Task 2·11).
- **비율:** 이 계획은 구현 코드를 쓰지 않고 시그니처와 테스트 이름으로 결정한다. 동작이 Node 구현에 이미 있는 부분은 파일 경로를 가리키는 데 그쳤다.
