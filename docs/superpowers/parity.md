# Node(태그 `node-v1`) → 파이썬 이식 현황

## SDK 메모 (mcp 2.3.0, 2026-10-21 확인)

- `from mcp.server.mcpserver import MCPServer` — `FastMCP`는 `MCPServer`로 이름이 바뀌었다. `mcp.server.fastmcp`는 없다.
- 서버 생성 `MCPServer(name)`, 도구 등록은 `server.add_tool(fn, name=..., description=...)` 또는 `@server.tool(name=..., description=...)`. 함수의 타입 힌트로 입력 스키마가 만들어진다.
- 실행은 동기 함수 `server.run()` (기본 stdio).
- 클라이언트(테스트용): `from mcp import Client`; `Client(StdioServerParameters(...))` 또는 `Client(server_instance)`(프로세스 내 연결); `async with ... as client:` 후 `client.list_tools()`, `client.call_tool(name, args)`, `client.server_info.name`.

## 파일별 상태

| Node 테스트 | 파이썬 테스트 | 상태 |
|---|---|---|
| credentials.test.js | test_config.py | 이식함: HUB 키 케이스(성공, 둘 다 없음, 반쪽, 공백, 트림). 대체함: legacy 키 케이스 → "legacy만 있으면 오류" 1건. 해당 없음: HUB 우선/legacy 폴백, `warning` 키(legacy 미지원). 추가: `.env` 로딩 5건 |
| naver-api-endpoints.test.js | test_endpoints.py | 이식함: HUB URL, 검색 URL 조립, 쇼핑 suffix 8종, 헤더 이름. 해당 없음: legacy URL/헤더 |
| naver-api-error.test.js | test_errors.py | 이식함: 상태/URL/본문, 401 힌트, no response, 문자열 본문. 해당 없음: legacy 표기. 추가: 한글 본문, 키 비노출 |
| date-utils.test.js | test_dates.py | 이식함: KST 오늘, 이중 보정 방지(`now` 주입), today 대소문자, 형식 거부 5종, 범위 |
| naver-search-client.test.js | test_client.py | 이식함: HUB 헤더, 응답 없는 실패의 원인 메시지(ConnectError/ReadTimeout). 대체함: URL 노출 테스트 → 9개 엔드포인트 경로/메서드 표 + 검색 타입 7종 경로. 해당 없음: legacy 케이스, 싱글톤 초기화 전 오류, 요청 중 인스턴스 정리(싱글톤 없음). 추가: HTTP 오류, 401 안내와 키 비노출, 비 JSON 응답, None 파라미터 제거, aclose 중복 호출 |
| (live) hub.live.test.js | tests/live/test_hub_endpoints.py | 이식함: blog postdate 8자리, 카페/웹 날짜 없음, 트렌드 형태, 쇼핑 그룹 5/6, param 1개. 추가: 검색 8종·쇼핑 8종 경로 확인(5종은 Application 미활성이라 skip), 없는 경로 404 구분 |
| (category.handlers.ts, 전용 테스트 없음) | test_categories.py | 신규 작성: 정확/시작/포함/유사 점수, 정렬(점수→코드), max_results, 결과 없음, 결과 구조/next_steps, 대소문자·공백, 패키지 리소스 로딩(작업 폴더 무관)과 캐시, 영어 문법 분야 코드(50005951). `find_category`에 테스트용 `categories=` 인자 추가 |
| file-cache.test.js | test_cache.py | 이식함: 키 순서 무관/엔드포인트 구분, TTL 만료, 깨진 파일, cached_call 1회 호출, params/비밀 미저장. 추가: 한글 UTF-8 저장, None 미저장, 디렉터리 자동 생성, 인자별 구분, 환경변수/기본값/잘못된 TTL |
| budget.test.js | test_budget.py | 이식함: 기본 30, confirm, 지정 상한. 추가: dryRun 안내 문구 |
| brand.test.js | test_brand.py | 이식함: 키워드 중복 제거/공백 변형 유지, 빈 별칭, 20개 초과, 공백 무시 매칭. 추가: validate_brands(빈 이름), BrandInput 기본값/빈 이름/튜플 변환, 정확히 20개 허용 |
| rescale.test.js | test_rescale.py | 이식함: 합계 비율 환산([200,100]), 다중 배치 기준 0, 단일 배치 기준 0 허용, 후속 배치 기준 0, 기준 누락, 정밀도 임계값, 후속 배치 약한 기준 표시, plan_batches, estimate_trend_calls, 중앙값(0 합계 제외, 짝수 아래쪽) |
| compare-trend.test.js | test_compare_trend.py | 이식함: 전 케이스(6개 브랜드 환산 F≈2.5, 별칭 묶음, dryRun, 예산/confirm, 캐시 재사용, 재기준 E와 배치 순서, 직접 지정 기준, 단일 배치, 쇼핑 category/param 1개/device 거부/데이터 없음, 중복 이름, 비밀 비노출, 데이터 없는 첫 브랜드와 기준 교체, 0 브랜드 재기준 제외, confirm 예산 상한과 estimatedCallsMax, 약한 기준 경고, 사전 검증, 쇼핑 별칭 순차 시도 4건). 추가: to_dict 키 집합(camelCase) |
| mentions.test.js | test_mentions.py | 이식함: 전 케이스(strip_html 이중 복원 방지, postdate 3종, 페이지 3·2·10과 start≤901, maxPosts 150, 중복 링크, 빈 페이지·캐시 재사용, <b>로 쪼개진 제목 매칭, 월별/undated, 호출 수 추정 40·4). 추가: 엔티티 종류, 1000건 상한 추정 |
| candidates.test.js | test_candidates.py + test_tokenizer.py | **대체함**: 로직 테스트(집계, 제외 규칙, 정렬, baseline 필터/rate/lift, genericRate, 조사 제외+복합어 유지)는 Node와 같은 입력·기대값을 정규식 토크나이저(기본값)로 이식. 형태소 분석 기반 후보는 별도 테스트(조사 분리, 명사/외래어/어근만, 영문 소문자, 1글자 제외, 사용자 사전 보존, 브랜드 키워드 사전 등록, 지연 로딩, kiwi 후보). 추가: 토크나이저 주입, to_dict camelCase |
| export.test.js | test_export.py | 이식함: 전 케이스(파일명 정리와 백슬래시, 수식 무력화, xlsx+CSV 생성과 경로 안 보장, 경로 문자가 든 baseName, CSV BOM/이스케이프, xlsx 재읽기, 시트 이름 정리). 추가: CSV 셀 무력화, 제어 문자 제거, 중복 시트 이름, 재저장 덮어쓰기, 빈 시트 목록, 콘솔 로케일(cp949)과 무관한 UTF-8 저장, to_dict camelCase |
| tool-filter.test.js | test_tool_filter.py | 이식함: 허용 목록 파싱(빈 값/공백/쉼표), 허용된 도구만 등록, null이면 전부. 대체함: `applyToolFilter`(서버 메서드 감싸기) → `ToolRegistrar`. 추가: 알 수 없는 이름 stderr 경고, MCP 클라이언트에서 실제로 숨겨지는지 |
| (index.ts 시작 로직, 전용 테스트 없음) | test_server.py | 신규: 키 없음/legacy만/반쪽 키 → 종료 코드 1과 stderr 안내와 빈 stdout, 더미 키로 시작과 비밀 비노출, MCP 클라이언트 연결, .env 사용과 환경변수 우선, stderr UTF-8, kiwipiepy 지연 로딩(서버 생성) |
| analysis-tools.test.js | test_analysis_tools.py + test_tools_schema.py + test_tools_behavior.py | 이식함: 전 케이스(도구 2개 등록, dryRun, exportAs 파일, 카페 날짜 없음 경고, mentions dryRun 3회와 기본 100건=1회, 예산 초과 confirm, 표본 잘림 경고, comparableFrom/partial, 내보내기 실패 시 결과 유지, 사전 검증, baselineQuery). 대체함: 예외 타입 → ToolError(mcp 2.x). 추가: 20개 도구 목록·스키마(camelCase 인자, ages 열거, 기본값), 잘못된 타입 오류 메시지, NAVER_TOOLS_ALLOW(stdio), 검색 8종/데이터랩 9종 요청 형태, find_category, ApiError 메시지 전달, kiwi 기본 토크나이저 |
| removed-tools.test.js | (없음) | 해당 없음: Node 클라이언트 내부(제거된 search_shop/book/doc, searchAcademic, 싱글톤 메서드 목록) 확인용이라 새 코드베이스에 의미 없음. 도구 목록은 test_tools_schema.py가 보증한다 |
| fixtures.test.js | test_fixtures.py | 이식함: 8개 케이스 전부(검색 응답 구조, 블로그 정규화, 카페/웹 날짜 없음, 수집+필터, 트렌드 최댓값 100, 엄격한 쇼핑 API(별칭 있어도 param 1개/그룹 5개 준수), 데이터 빈 키워드 경고, 오류 메시지 전달과 키 비노출). 변이 확인: 쇼핑 param에 별칭 전체를 보내게 하면 실패함을 확인하고 복구 |
| (scripts/record-fixtures.mjs) | scripts/record_fixtures.py | 이식함: 합성 텍스트 치환, 키 검사, 6개 샘플. 실제 키로 실행해 재녹화한 샘플로도 계약 테스트가 통과함을 확인(날짜/건수만 다름) |

## 요약

Node 테스트 파일 18개(live 포함)가 모두 위 표에 있다. 파이썬 테스트는 단위·계약·서버 테스트와 라이브 테스트로 나뉜다.
