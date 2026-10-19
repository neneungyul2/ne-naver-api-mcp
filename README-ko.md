<p align="center">
  <img src="https://img1.kakaocdn.net/thumb/R0x200a.i/?fname=https%3A%2F%2Ft1.kakaocdn.net%2Fkomi%2Fupload-files%2Fmcp%2Fimages%2FnQzoe8vIxql0oK7Rwi239dxO2iYrxozLLQCIPRpVjmOjwGyPw0ZNUnNJfGkO1kAZmKf16eLZPAYi8NIS8XaBZJ.png" alt="Naver Search MCP Server Logo" width="128" />
</p>

# Naver Search MCP Server

[![npm version](https://img.shields.io/npm/v/@isnow890/naver-search-mcp.svg)](https://www.npmjs.com/package/@isnow890/naver-search-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

네이버 검색 API 및 DataLab(데이터랩) API 연동을 위한 Model Context Protocol(MCP) 서버입니다.  
웹, 뉴스, 블로그, 쇼핑인사이트, 검색어 트렌드 분석 및 자연어 쇼핑 카테고리 검색을 지원합니다.

> **포크 안내:** 이 저장소는 [isnow890/naver-search-mcp](https://github.com/isnow890/naver-search-mcp)(MIT License)를 포크해 도서 브랜드 분석 도구(`brand_compare_trend`, `brand_mentions`)와 xlsx/CSV 내보내기를 추가한 것입니다. 원본의 저작권 고지와 라이선스는 `LICENSE`에 그대로 유지됩니다. 아래 상단의 npm 배지는 원본 패키지를 가리킵니다.

---

## 빠른 설정 (Quick Start)

Claude Desktop, Cursor, Claude Code, Cline 등 사용하시는 MCP 클라이언트 설정 파일(`claude_desktop_config.json`, `mcp.json` 등)의 `mcpServers`에 아래 설정을 추가하세요.

> **안내:** [Kakao PlayMCP](https://playmcp.kakao.com/mcp/154) 연동 서비스는 지원이 종료되었습니다. 로컬 환경에서 직접 API 키를 설정하여 이용해 주세요.

### 1. NAVER API HUB (권장 / 신규 발급)
네이버 클라우드 플랫폼(NCP)의 [NAVER API HUB](https://www.ncloud.com/product/applicationService/naverApiHub) 키를 사용하는 경우:

```json
{
  "mcpServers": {
    "naver-search": {
      "command": "npx",
      "args": ["-y", "@isnow890/naver-search-mcp"],
      "env": {
        "NCP_APIGW_API_KEY_ID": "your_client_id",
        "NCP_APIGW_API_KEY": "your_client_secret"
      }
    }
  }
}
```

### 2. 네이버 개발자센터 (기존 발급자 전용)
기존 네이버 개발자센터(`openapi.naver.com`) 키를 사용하는 경우 (2027-06-30까지 지원):

```json
{
  "mcpServers": {
    "naver-search": {
      "command": "npx",
      "args": ["-y", "@isnow890/naver-search-mcp"],
      "env": {
        "NAVER_CLIENT_ID": "your_client_id",
        "NAVER_CLIENT_SECRET": "your_client_secret"
      }
    }
  }
}
```

### 3. OpenClaw (ClawHub)
OpenClaw를 사용하는 경우 ClawHub 스킬로 즉시 설치할 수 있습니다:

```bash
openclaw skills install naver-search-mcp
```

> **참고:** OpenClaw 환경에 NAVER API HUB 쌍(`NCP_APIGW_API_KEY_ID` / `NCP_APIGW_API_KEY`) 또는 개발자센터 쌍(`NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET`) 중 **한 쌍**을 설정해야 합니다.

---

## API 키 발급 안내

사용하시는 환경변수 쌍에 따라 호출 플랫폼이 자동으로 결정됩니다. (둘 중 **한 쌍만** 설정하세요)

| 플랫폼 | 환경변수 | 비고 |
|---|---|---|
| **NAVER API HUB (권장)** | `NCP_APIGW_API_KEY_ID`<br>`NCP_APIGW_API_KEY` | • [네이버 클라우드 플랫폼 콘솔](https://www.ncloud.com) 접속<br>• Menu > All Services > Application Services > **NAVER API HUB** > Application 등록 후 '인증 정보' 확인 |
| **네이버 개발자센터 (기존)** | `NAVER_CLIENT_ID`<br>`NAVER_CLIENT_SECRET` | • 2026-07-31 부로 신규 발급 차단됨<br>• 기존 발급된 키는 2027-06-30까지 정상 동작 |

---

## 제공 도구 (Tools)

### 1. 카테고리 검색
- **`find_category`**: 카테고리 번호를 몰라도 자연어로 검색하여 쇼핑 인사이트용 카테고리 ID를 조회합니다.

### 2. 검색 도구 (Search)
- **`search_webkr`**: 웹 문서 검색
- **`search_news`**: 뉴스 검색
- **`search_blog`**: 블로그 검색
- **`search_cafearticle`**: 카페 글 검색
- **`search_image`**: 이미지 검색
- **`search_kin`**: 지식iN 검색
- **`search_encyc`**: 백과사전 검색
- **`search_local`**: 지역 장소 검색

### 3. 데이터랩 트렌드 분석 (DataLab)
날짜 파라미터에 `"today"` 키워드를 지원합니다 (예: `endDate: "today"`).
- **`datalab_search`**: 검색어 트렌드 분석
- **`datalab_shopping_category`**: 쇼핑 카테고리별 클릭 트렌드
- **`datalab_shopping_by_device`**: 기기별(PC/모바일) 쇼핑 트렌드
- **`datalab_shopping_by_gender`**: 성별 쇼핑 트렌드
- **`datalab_shopping_by_age`**: 연령대별 쇼핑 트렌드
- **`datalab_shopping_keywords`**: 쇼핑 키워드 트렌드
- **`datalab_shopping_keyword_by_device`**: 키워드 기기별 트렌드
- **`datalab_shopping_keyword_by_gender`**: 키워드 성별 트렌드
- **`datalab_shopping_keyword_by_age`**: 키워드 연령별 트렌드

### 4. 도서 브랜드 분석 (이 포크에서 추가)
브랜드는 `{ name, aliases[] }` 형식으로 넘깁니다 (별칭: 띄어쓰기/영문 표기 등). 모든 결과에는 `limitations`가 붙습니다.
- **`brand_compare_trend`**: 여러 브랜드의 검색어 트렌드(`source: "search"`) 또는 쇼핑 클릭 추이(`source: "shopping"`, `category` 필요)를 기준 브랜드로 환산해 **한 척도의 상대 지수**로 비교합니다. 정밀도가 낮은 브랜드가 있으면 중간 규모 브랜드로 기준을 바꿔 한 번 재계산합니다.
  - 쇼핑 인사이트는 키워드 그룹당 1개만 받습니다. 이름으로 먼저 조회하고, 데이터가 없으면 별칭을 순서대로(최대 2개) 시도합니다.
- **`brand_mentions`**: 블로그/카페글/웹문서에서 브랜드 언급 글을 **최근 순으로 수집**(기본 검색어당 100건)해 월별로 집계하고, 함께 언급된 **후보 단어**와 예시 문장을 돌려줍니다. 최근 언급 경향을 보는 용도입니다.
  - 표본이 최근 글에 한정되므로 브랜드마다 닿는 과거가 다릅니다. 결과의 `comparableFrom`(소스별 비교 가능 시작일)과 월별 행의 `partial`(부분 집계)을 확인하세요.
  - `baselineQuery`(예: `"중등 영어 문법 교재"`)를 주면 그 일반 검색 결과에서 흔한 단어(문법, 영어 등)를 후보에서 뺍니다. 후보에는 `baselineRate`와 `lift`가 붙습니다. 소스당 호출이 1회 이상 늘어납니다.
  - 후보가 브랜드인지는 직접 판단하세요. 카페글처럼 날짜가 없는 소스는 월별 집계에서 제외됩니다.

공통 인자: `dryRun`(호출 없이 예상 호출 수만 계산), `maxCalls`(기본 30), `confirm`(상한 초과 시 진행), `exportAs`(xlsx와 CSV로 저장할 파일 이름).

> NAVER API HUB에는 호출 한도를 조회하는 API나 응답 헤더가 없습니다. 월 사용량은 NCP 콘솔의 NAVER API HUB > Usage Statistics에서 확인하세요. 이 도구는 한 번 실행 안에서의 호출 수만 셉니다.

### 테스트
- `npm test`: 단위 테스트와, 실제 응답을 녹화한 샘플(`tests/fixtures/`) 기반 테스트. 네트워크를 쓰지 않습니다.
- `npm run test:live`: 실제 API를 호출해 코드가 기대는 가정(날짜 형식, 키워드 개수 제한 등)을 확인합니다. `.env`의 키가 필요하고 호출 약 9회를 씁니다.
- `node scripts/record-fixtures.mjs`: 샘플을 실제 응답으로 다시 녹화합니다(호출 6회).

| 환경변수 | 설명 | 기본값 |
|---|---|---|
| `NAVER_EXPORT_DIR` | xlsx/CSV 저장 폴더 | `<작업 디렉터리>/exports` |
| `NAVER_CACHE_DIR` | API 응답 캐시 폴더 | `<홈>/.naver-search-mcp/cache` |
| `NAVER_CACHE_TTL_HOURS` | 캐시 유지 시간(시간) | `24` |
| `NAVER_TOOLS_ALLOW` | 노출할 도구 이름 목록(쉼표 구분, 비우면 전체). 예: `brand_compare_trend,brand_mentions,find_category` | 전체 |

---

## License
MIT License
