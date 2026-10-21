# ne-naver-api-mcp

NAVER API HUB(검색, 데이터랩)를 쓰는 MCP(Model Context Protocol) 서버입니다. 네이버 웹문서/블로그/카페 검색, 검색어 트렌드, 쇼핑 인사이트와 함께, **도서 제품 브랜드의 검색·쇼핑·언급 추이를 비교하는 분석 도구**(`brand_compare_trend`, `brand_mentions`)와 엑셀/CSV 내보내기를 제공합니다.

> **포크 안내:** 이 프로젝트는 [isnow890/naver-search-mcp](https://github.com/isnow890/naver-search-mcp)(MIT License)를 바탕으로 합니다. 원본(Node/TypeScript)의 HUB 호출 방식, 인증 처리, 쇼핑 분야 코드 데이터(`categories.json`)를 파이썬으로 옮기고 분석 기능을 추가했습니다. 원본의 저작권 고지와 라이선스는 [`LICENSE`](LICENSE)에 그대로 유지됩니다. Node 버전은 태그 `node-v1`에 남아 있습니다.

## 도구 (20개)

| 구분 | 도구 |
|---|---|
| 카테고리 | `find_category` — 자연어로 쇼핑 분야 코드 검색 |
| 검색 | `search_webkr`, `search_blog`, `search_cafearticle`, `search_news`, `search_image`, `search_kin`, `search_encyc`, `search_local` |
| 데이터랩 | `datalab_search`(검색어 트렌드), `datalab_shopping_category`, `datalab_shopping_by_device`, `datalab_shopping_by_gender`, `datalab_shopping_by_age`, `datalab_shopping_keywords`, `datalab_shopping_keyword_by_device`, `datalab_shopping_keyword_by_gender`, `datalab_shopping_keyword_by_age` |
| 분석 | `brand_compare_trend`, `brand_mentions` |

날짜 인자에는 `"today"`(한국 시간 기준 오늘)를 쓸 수 있습니다.

> **NAVER API HUB에서 API를 Application에 추가해야 합니다.** 검증일(2026-10-21) 기준 확인된 것은 `search_webkr`, `search_blog`, `search_cafearticle`과 데이터랩 전체(검색어 트렌드, 쇼핑 인사이트 8종)입니다. `search_news`, `search_image`, `search_kin`, `search_encyc`, `search_local`은 HUB에 경로가 있지만 확인에 쓴 Application에는 추가되어 있지 않아 HTTP 401 `요청한 API는 이 Application에서 활성화되어 있지 않습니다`가 돌아왔고, **응답 구조는 확인하지 못했습니다.** NCP 콘솔 > NAVER API HUB에서 Application에 해당 API를 추가하면 사용할 수 있습니다.

## 설치

필요한 것: [uv](https://docs.astral.sh/uv/) (파이썬은 uv가 알아서 준비합니다), NAVER API HUB 키(`NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY`; NCP 콘솔 > NAVER API HUB에서 Application을 만들어 발급).

### Claude Code

```
claude mcp add ne-naver-api -s user ^
  -e NCP_APIGW_API_KEY_ID=발급ID -e NCP_APIGW_API_KEY=발급Key ^
  -e NAVER_EXPORT_DIR=C:\Users\내이름\Documents\naver-exports ^
  -- uvx --from git+https://github.com/neneungyul2/ne-naver-api-mcp ne-naver-api-mcp
```

(줄 끝 `^`는 Windows cmd의 줄 이음입니다. PowerShell은 `` ` ``, macOS/Linux는 `\`를 쓰세요.)

### Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json`에 추가한 뒤 앱을 완전히 종료했다가 다시 실행합니다.

```json
{
  "mcpServers": {
    "ne-naver-api": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/neneungyul2/ne-naver-api-mcp", "ne-naver-api-mcp"],
      "env": {
        "NCP_APIGW_API_KEY_ID": "발급ID",
        "NCP_APIGW_API_KEY": "발급Key",
        "NAVER_EXPORT_DIR": "C:\\Users\\내이름\\Documents\\naver-exports"
      }
    }
  }
}
```

`uvx`를 찾지 못하면 `"command"`에 `uvx.exe`의 전체 경로를 쓰세요. 배포할 때는 주소 끝에 커밋이나 태그를 붙여 버전을 고정하세요(`git+https://...ne-naver-api-mcp@<커밋>`).

> 위 GitHub 주소로 설치하는 방법은 이 저장소의 `main`이 파이썬 버전일 때만 동작합니다. 그 전에는 로컬 폴더로 설치하세요: `uvx --from <이 저장소를 받은 폴더> ne-naver-api-mcp`.

### 환경변수

| 이름 | 설명 | 기본값 |
|---|---|---|
| `NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY` | NAVER API HUB 키 (필수) | — |
| `NAVER_EXPORT_DIR` | 엑셀/CSV 저장 폴더. **지정을 권장합니다**(MCP 클라이언트가 서버를 실행하는 작업 폴더를 알 수 없어서) | `<작업 폴더>/exports` |
| `NAVER_CACHE_DIR` | API 응답 캐시 폴더 | `<홈>/.naver-search-mcp/cache` |
| `NAVER_CACHE_TTL_HOURS` | 캐시 유지 시간(시간) | `24` |
| `NAVER_TOOLS_ALLOW` | 노출할 도구 이름(쉼표 구분, 비우면 전체). 예: `find_category,brand_compare_trend,brand_mentions` | 전체 |

서버는 환경변수를 우선 쓰고, 비어 있는 키는 **작업 폴더의 `.env`**(`KEY=VALUE` 형식)에서 채웁니다. 키가 없으면 서버는 시작하지 않고 stderr에 안내를 남긴 뒤 종료 코드 1로 끝납니다. 네이버 개발자센터(legacy) 키는 지원하지 않습니다.

## 도서 브랜드 분석

브랜드는 `{ "name": "그래머인사이드", "aliases": ["그래머 인사이드", "Grammar Inside"] }` 형식입니다(별칭은 표기가 갈리는 이름). 모든 결과에는 `limitations`가 붙습니다.

### `brand_compare_trend`

여러 브랜드의 검색어 트렌드(`source: "search"`) 또는 쇼핑 클릭 추이(`source: "shopping"`, `category` 필요)를 **한 척도의 상대 지수**로 비교합니다. Data Lab의 지수는 요청마다 최댓값이 100인 상대값이라, 기준 브랜드를 모든 호출에 넣고 합계 비율로 환산합니다.

- 기준 브랜드를 생략하면 첫 브랜드를 쓰고, 정밀도가 낮은 브랜드가 있으면 중간 규모 브랜드로 기준을 바꿔 **한 번만** 다시 계산합니다. 기준 브랜드에 데이터가 없으면 첫 묶음에서 가장 큰 브랜드로 바꿉니다.
- 쇼핑 인사이트는 키워드 그룹당 1개만 받으므로 **이름으로 먼저 조회**하고, 데이터가 없으면 별칭을 순서대로(최대 2개) 시도합니다.
- 값은 실제 검색/클릭 횟수가 아니며, 첫 묶음의 최댓값을 100으로 한 척도라 100을 넘을 수 있습니다.

### `brand_mentions`

블로그/카페글/웹문서에서 브랜드 언급 글을 **최근 순으로 수집**(기본 검색어당 100건)해 월별로 집계하고, 함께 언급된 **후보 단어**와 예시 문장을 돌려줍니다. 최근 언급 경향을 보는 용도입니다.

- 검색 API에는 기간 필터가 없어 표본이 최근 글에 한정됩니다. 브랜드마다 닿는 과거가 다르므로 결과의 `comparableFrom`(소스별 비교 가능 시작일)과 월별 행의 `partial`(부분 집계)을 확인하세요.
- 카페글과 웹문서는 날짜가 없어 월별 집계에서 제외됩니다(건수와 후보 분석에는 포함).
- `baselineQuery`(예: `"중등 영어 문법 교재"`)를 주면 그 일반 검색 결과에서 흔한 단어(문법, 영어 등)를 후보에서 뺍니다.
- 후보 단어는 한국어 형태소 분석(kiwipiepy)으로 뽑으며, 조사는 떼어 내고 브랜드 이름과 별칭은 쪼개지지 않게 처리합니다. 후보가 **브랜드인지는 직접 판단**하세요.

### 공통 인자와 호출 한도

| 인자 | 설명 |
|---|---|
| `dryRun` | 호출 없이 예상 호출 수(`estimatedCalls`, 비교 트렌드는 최악의 경우 `estimatedCallsMax`)만 계산 |
| `maxCalls` | 한 번의 실행에서 쓸 API 호출 상한 (기본 30) |
| `confirm` | 예상 호출 수가 상한을 넘어도 진행 |
| `exportAs` | 지정하면 결과를 `<이름>.xlsx`와 시트별 CSV로 저장 (엑셀의 `=`로 시작하는 셀은 수식으로 실행되지 않게 처리, 내보내기가 실패해도 분석 결과는 돌려줌) |

NAVER API HUB에는 **호출 한도를 조회하는 API나 응답 헤더가 없습니다.** 월 사용량(검색 775,000건, 데이터랩 API별 50,000건)은 NCP 콘솔 > NAVER API HUB > Usage Statistics에서 확인하세요. 이 서버는 한 번의 실행 안에서의 호출 수만 세고, 같은 요청은 캐시로 호출을 아낍니다.

## 개발

```
uv sync                                   # 의존성 설치
uv run pytest                             # 테스트 (네트워크 없음, 라이브 테스트는 건너뜀)
NAVER_LIVE_TEST=1 uv run pytest tests/live   # 실제 API 확인 (.env의 키 필요, 호출 약 23회)
uv run python scripts/record_fixtures.py  # 테스트 샘플을 실제 응답으로 다시 녹화 (호출 6회)
```

PowerShell에서는 `$env:NAVER_LIVE_TEST=1; uv run pytest tests/live`처럼 실행하세요.

로컬 폴더로 설치(`uvx --from <폴더> ne-naver-api-mcp`)할 때 uv는 빌드 결과를 캐시합니다. 소스를 고치면 다시 빌드하도록 `pyproject.toml`에 `[tool.uv] cache-keys`를 설정해 두었습니다. 그래도 이전 코드가 실행되는 것 같으면 `uv cache clean ne-naver-api-mcp`로 캐시를 비우세요.

구성: `src/ne_naver_api_mcp/` — `client.py`(HUB HTTP 클라이언트), `analysis/`(환산, 비교 트렌드, 언급 수집, 후보 추출), `export.py`, `cache.py`, `tools/`(MCP 도구 등록), `server.py`. Node 구현과의 테스트 대응표는 [`docs/superpowers/parity.md`](docs/superpowers/parity.md), 설계 문서는 `docs/superpowers/specs/`에 있습니다.

## 라이선스

MIT License. 원본 저작권 고지는 [`LICENSE`](LICENSE)를 보세요.
