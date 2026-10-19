# 도서 브랜드 분석 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 포크한 naver-search-mcp에 브랜드 비교 트렌드, 언급 분석, 엑셀/CSV 내보내기 도구를 새 파일로 추가한다.

**Architecture:** 분석 로직은 `src/analysis/`의 순수 함수와, API를 주입받는 오케스트레이션 함수로 나눈다. 기존 `NaverSearchClient` 싱글톤은 수정하지 않고 구조적 타입(`AnalysisApi`)으로 주입한다. 캐시(`src/cache/`)와 내보내기(`src/export/`)는 독립 모듈이다. `src/index.ts`는 도구 노출 필터 적용과 등록 호출만 추가한다.

**Tech Stack:** TypeScript(ESM, NodeNext), `@modelcontextprotocol/sdk` 1.17.1, zod, `exceljs`(신규), `node:test`(테스트는 빌드된 `dist/`를 대상으로 한다).

**Spec:** `docs/superpowers/specs/2026-10-16-book-brand-analysis-design.md`

## Global Constraints

- Node 18 이상. 상대 import는 `.js` 확장자를 붙인다(NodeNext). 코드/주석 스타일은 기존 파일(한국어 주석, 2칸 들여쓰기, 큰따옴표)을 따른다.
- 기존 파일 수정은 `src/index.ts`(필터 적용과 등록 호출), `package.json`(의존성), `.gitignore`, `README-ko.md`(설명 추가)로 한정한다. `src/clients/`, `src/config/`, `src/handlers/`는 수정하지 않는다.
- 엑셀은 `exceljs`를 쓴다. `package.json`의 `xlsx`는 제거한다(소스에서 쓰이지 않음).
- API 한도: `keywordGroups` 최대 5개, 그룹당 키워드 최대 20개, 검색 `display` 1~100, `start` 1~1000, 쇼핑 `category` 최대 3쌍.
- 기본값: 호출 상한 `maxCalls` 30, 캐시 TTL 24시간, 후보 상위 30개, 낮은 정밀도 임계값 1(환산 지수 최댓값 기준), 자동 재기준은 1회.
- 환경변수: `NAVER_EXPORT_DIR`(기본 `<cwd>/exports`), `NAVER_CACHE_DIR`(기본 `<홈>/.naver-search-mcp/cache`), `NAVER_CACHE_TTL_HOURS`(기본 24), `NAVER_TOOLS_ALLOW`(쉼표 구분, 비어 있으면 전체).
- 모든 분석 결과는 `limitations: string[]`에 "상대 지수", "수집 표본 기준 근사", "후보" 문구를 싣는다. 엑셀에도 같은 문구의 시트를 넣는다.
- 커밋 메시지 끝에 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`를 붙인다.
- 테스트 실행: `npm test`(= 빌드 후 `node --test`). 단일 파일은 `npm run build && node --test tests/<file>.test.js`.

## Review Focus

- 검색 결과의 `<b>` 태그와 HTML 엔티티(`&quot;` 등)가 브랜드 매칭과 월별 집계, 후보 단어에 섞이지 않아야 한다. (Task 6)
- 기준 브랜드 값이 전부 0이거나 한 배치에서 빠졌을 때 NaN/무한대 대신 이유가 분명한 오류가 나야 한다. (Task 4)
- `postdate`가 비었거나 형식이 틀린 글은 죽지 않고 "날짜 없음"으로 세어야 한다. (Task 6)
- 내보내기 파일명에 `../`나 경로 문자가 들어 있어도 지정 폴더 밖에 쓰지 않고, 수식으로 해석되는 셀(`=`, `+`, `-`, `@`로 시작)은 무력화돼야 한다. (Task 8)
- API 키가 캐시 파일, 오류 메시지, 내보내기 파일에 들어가지 않아야 한다. (Task 3)

---

### Task 1: HUB 경로와 응답 형식 검증 (관문)

**Files:**
- Create: `scripts/verify-hub.mjs`
- Modify: `docs/superpowers/specs/2026-10-16-book-brand-analysis-design.md` (§7에 확인 결과 추가)

**Interfaces:**
- Produces: 아래 사실의 확인 결과. 이후 Task가 이 결과에 의존한다.
  - A. `/shopping/v1/category/keywords` 등 쇼핑 하위 경로 유효 여부와 키워드 그룹 최대 개수 → `SHOPPING_SLOTS_PER_CALL` 상수(Task 5)
  - B. `/search/v1/webkr`, `/search/v1/cafearticle` 유효 여부
  - C. 블로그 `postdate` 형식, 카페글/웹문서 응답에 날짜 필드가 있는지
  - D. "도서 > 학습/참고서"의 쇼핑 분야 코드 (`find_category` 또는 `data/categories.json`)

> 사용자가 `NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY` 환경변수를 설정해 두어야 한다. 키가 없으면 이 Task에서 멈추고 사용자에게 요청한다. 호출은 합계 20회 이내로 한다(월 한도 보호).

- [ ] **Step 1: `scripts/verify-hub.mjs` 작성.** `npm run build` 후 `dist/src/clients/naver-search.client.js`의 클라이언트로 `resolveCredentials`(`dist/src/config/credentials.js`)를 거쳐 초기화한다. 호출 항목은 블로그/카페글/웹문서 각 1건(`query: "그래머인사이드"`, `display: 3`), 쇼핑 `keywords` 1회, 검색어 트렌드 1회. 각 응답의 최상위 키와 `items[0]`의 키 목록만 출력한다(본문, 키 값은 출력하지 않는다). 실패 시 HTTP 상태와 URL만 출력한다.
- [ ] **Step 2: 실행.** Run: `npm run build && node scripts/verify-hub.mjs` / Expected: A~C의 결과(유효/무효, 필드 목록)가 출력된다.
- [ ] **Step 3: 쇼핑 `keywords` 그룹 개수 한도 확인.** 같은 스크립트에 그룹 5개, 6개로 호출하는 경우를 추가하고 어느 개수까지 성공하는지 기록한다. D는 `find_category`의 입력 "도서 학습 참고서"로 얻은 코드를 기록한다.
- [ ] **Step 4: 결과 반영.** 스펙 §7 각 항목 옆에 확인 결과(날짜, 값)를 적는다. 카페글에 날짜가 없으면 스펙 §9-3의 대체 동작(월별 집계는 블로그만)을 그대로 적용한다. 경로가 무효인 항목이 있으면 이 Task에서 멈추고 사용자에게 알린다.
- [ ] **Step 5: Commit.** `git add scripts/verify-hub.mjs docs && git commit -m "chore: verify HUB endpoints for brand analysis"`

---

### Task 2: 브랜드 모델

**Files:**
- Create: `src/analysis/brand.ts`
- Test: `tests/brand.test.js`

**Interfaces:**
- Produces:
  - `type Brand = { name: string; aliases: string[] }`
  - `const BrandSchema: z.ZodType<Brand>` (`aliases` 기본값 `[]`)
  - `brandKeywords(brand: Brand): string[]` — `[name, ...aliases]`에서 공백 제거 후 빈 문자열 제거, 대소문자 무시 중복 제거, 최대 20개. 20개 초과는 오류를 던진다.
  - `matchesBrand(text: string, brand: Brand): boolean` — 공백 제거, 소문자화한 텍스트에 공백 제거, 소문자화한 키워드 중 하나라도 포함되면 true. (그래머인사이드 ≡ 그래머 인사이드)

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/brand.test.js`, `../dist/src/analysis/brand.js`를 import):
  - `brandKeywords`는 `{name:"그래머인사이드", aliases:["그래머 인사이드","그래머인사이드","Grammar Inside"]}`에서 중복(공백만 다른 항목은 별개로 유지, 완전 동일 문자열만 제거)과 대소문자만 다른 항목을 제거한 목록을 돌려준다.
  - 키워드가 21개 이상이면 `/최대 20개/` 오류.
  - `matchesBrand("천일문 중등 그래머 후기", {name:"천일문중등그래머",aliases:[]})`는 true. `matchesBrand("그래머 수업", {name:"그래머인사이드",aliases:[]})`는 false.
- [ ] **Step 2: 실패 확인.** Run: `npm run build && node --test tests/brand.test.js` / Expected: 빌드 실패 또는 모듈 없음
- [ ] **Step 3: `src/analysis/brand.ts` 구현** (위 시그니처).
- [ ] **Step 4: 통과 확인.** Run: `npm run build && node --test tests/brand.test.js` / Expected: PASS
- [ ] **Step 5: Commit.** `git add src/analysis/brand.ts tests/brand.test.js && git commit -m "feat: add brand model"`

---

### Task 3: 파일 캐시와 호출 예산

**Files:**
- Create: `src/cache/file-cache.ts`, `src/analysis/budget.ts`
- Test: `tests/file-cache.test.js`, `tests/budget.test.js`

**Interfaces:**
- Produces (`file-cache.ts`):
  - `cacheKey(endpoint: string, params: unknown): string` — 키 순서와 무관하게 같은 결과(안정적 JSON 직렬화 후 sha256 hex).
  - `class FileCache { constructor(opts: { dir: string; ttlMs: number; now?: () => number }); get<T>(key: string): Promise<T | undefined>; set(key: string, value: unknown): Promise<void> }` — TTL이 지났거나 파일이 깨졌으면 `undefined`.
  - `defaultCache(): FileCache` — 환경변수(`NAVER_CACHE_DIR`, `NAVER_CACHE_TTL_HOURS`)를 읽어 만든다.
  - `class CallCounter { used: number; hit: number; increment(): void; recordHit(): void }`
  - `cachedCall<T>(cache: FileCache, counter: CallCounter, endpoint: string, params: unknown, fn: () => Promise<T>): Promise<T>` — 캐시에 있으면 `recordHit()`만, 없으면 `fn()` 호출 후 `increment()`하고 저장한다.
- Produces (`budget.ts`):
  - `class BudgetExceededError extends Error { estimated: number; maxCalls: number }`
  - `checkBudget(opts: { estimated: number; maxCalls?: number; confirm?: boolean }): void` — `maxCalls` 기본 30. `estimated > maxCalls`이고 `confirm !== true`이면 `BudgetExceededError`(메시지에 예상 호출 수와 "confirm" 안내 포함).

- [ ] **Step 1: 실패하는 테스트 작성.**
  - `cacheKey("/a", {x:1,y:2}) === cacheKey("/a", {y:2,x:1})`, 엔드포인트가 다르면 다르다.
  - `FileCache`: set 후 get이 같은 값을 준다. `now`를 주입해 TTL 경과 후 `undefined`. 임시 디렉터리를 쓴다(`fs.mkdtemp`).
  - `cachedCall`: 같은 인자로 두 번 호출하면 `fn`은 1번, `counter.used === 1`, `counter.hit === 1`.
  - **보안:** 캐시 디렉터리의 모든 파일 내용에 테스트용 키 문자열(`"SECRET-KEY-123"`)이 없다. (`cachedCall`의 `params`에 키가 들어오지 않는다는 것이 계약이고, 파일에는 `params`도 저장하지 않고 값만 저장한다.)
  - `checkBudget({estimated:31})`은 던지고, `{estimated:31, confirm:true}`와 `{estimated:30}`은 통과한다. `maxCalls: 5, estimated: 6`은 던진다.
- [ ] **Step 2: 실패 확인.** Run: `npm run build && node --test tests/file-cache.test.js tests/budget.test.js` / Expected: FAIL
- [ ] **Step 3: 구현.** 캐시 파일은 `<dir>/<key>.json`에 `{savedAt, value}`로 저장한다. 디렉터리는 없으면 만든다.
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: Commit.** `git add src/cache src/analysis/budget.ts tests && git commit -m "feat: add file cache and call budget guard"`

---

### Task 4: 상대 지수 환산 (순수 함수)

**Files:**
- Create: `src/analysis/rescale.ts`
- Test: `tests/rescale.test.js`

**Interfaces:**
- Produces:
  - `type SeriesPoint = { period: string; ratio: number }`
  - `type BatchResult = Record<string, SeriesPoint[]>` — 배치 하나의 결과. 키는 그룹명(브랜드명), 모든 배치에 기준 브랜드가 들어 있다.
  - `type ScaledSeries = { brand: string; points: SeriesPoint[]; lowPrecision: boolean }`
  - `class AnchorError extends Error`
  - `planBatches(brands: string[], anchor: string, slotsPerCall: number): string[][]` — 각 배치는 `[anchor, ...최대 slotsPerCall-1개]`. 기준 브랜드가 `brands`에 없으면 오류. 브랜드가 기준 하나뿐이면 `[[anchor]]`.
  - `estimateTrendCalls(brandCount: number, slotsPerCall: number): number` — `max(1, ceil((brandCount-1)/(slotsPerCall-1)))`.
  - `rescale(anchor: string, batches: BatchResult[], opts?: { lowThreshold?: number }): ScaledSeries[]` — 첫 배치를 기준 척도로 두고, 배치 b의 환산 계수는 `k_b = Σ(첫 배치의 기준 값) / Σ(배치 b의 기준 값)`이다. 배치 b의 브랜드 값은 `ratio × k_b`. 기준 브랜드 결과는 첫 배치 값을 그대로 쓴다. `lowPrecision`은 환산 후 최댓값이 `lowThreshold`(기본 1) 미만일 때 true.
  - `pickMedianAnchor(scaled: ScaledSeries[]): string` — 기간 합계가 중앙값인 브랜드(짝수면 아래쪽 중앙값).

- [ ] **Step 1: 실패하는 테스트 작성.**
  - 배치1: `{A:[100,50], X:[10,5]}`, 배치2: `{A:[50,25], Y:[100,50]}` → `rescale("A", ...)`에서 Y는 `[200,100]`(k=150/75=2), X는 `[10,5]`, A는 `[100,50]`.
  - 기준 브랜드 값이 첫 배치에서 전부 0 → `AnchorError`(메시지에 "기준 브랜드"). 배치2에서 기준 합이 0 → `AnchorError`.
  - 어떤 배치에 기준 키가 없으면 `AnchorError`.
  - `lowPrecision`: 환산 후 최댓값 0.4인 브랜드는 true, 5인 브랜드는 false.
  - `planBatches(["A","B","C","D","E","F"], "A", 5)` → `[["A","B","C","D","E"],["A","F"]]`. `planBatches(["A"], "A", 5)` → `[["A"]]`. 기준이 목록에 없으면 던진다.
  - `estimateTrendCalls(1,5)=1`, `(5,5)=1`, `(6,5)=2`, `(10,5)=3`.
  - `pickMedianAnchor`: 합계 10/20/30 브랜드 중 20인 브랜드.
- [ ] **Step 2: 실패 확인.** Run: `npm run build && node --test tests/rescale.test.js` / Expected: FAIL
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: Commit.** `git add src/analysis/rescale.ts tests/rescale.test.js && git commit -m "feat: add relative index rescaling"`

---

### Task 5: 브랜드 비교 트렌드 오케스트레이션

**Files:**
- Create: `src/analysis/compare-trend.ts`
- Test: `tests/compare-trend.test.js`

**Interfaces:**
- Consumes: Task 2 `Brand`, `brandKeywords`; Task 3 `FileCache`, `CallCounter`, `cachedCall`, `checkBudget`, `BudgetExceededError`; Task 4 전부; 기존 타입 `DatalabSearchRequest`, `DatalabShoppingKeywordsRequest`, `DatalabShoppingResponse`(`src/types/datalab.types.js`); `resolveDateRange`(`src/utils/date.utils.js`).
- Produces:
  - `interface AnalysisApi { searchTrend(req: DatalabSearchRequest): Promise<DatalabShoppingResponse>; datalabShoppingKeywords(req: DatalabShoppingKeywordsRequest): Promise<DatalabShoppingResponse>; search(type: "blog" | "cafearticle" | "webkr", params: SearchArgs): Promise<any> }` — 기존 `NaverSearchClient`가 그대로 만족한다.
  - `const SHOPPING_SLOTS_PER_CALL: number` — Task 1 A의 결과 값. 검색어 트렌드는 5(`SEARCH_SLOTS_PER_CALL`).
  - `interface CompareInput { brands: Brand[]; source: "search" | "shopping"; startDate: string; endDate: string; timeUnit: "date"|"week"|"month"; category?: string; anchor?: string; device?: "pc"|"mo"; gender?: "f"|"m"; ages?: string[]; maxCalls?: number; confirm?: boolean; dryRun?: boolean }` — `device/gender/ages`는 `source: "search"`에서만 허용한다.
  - `interface CompareResult { source: string; anchor: string; reanchored: boolean; series: ScaledSeries[]; callsUsed: number; cacheHits: number; estimatedCalls: number; warnings: string[]; limitations: string[]; dryRun: boolean }`
  - `compareBrandTrend(input: CompareInput, deps: { api: AnalysisApi; cache: FileCache; counter?: CallCounter }): Promise<CompareResult>`

동작 규칙: 브랜드 이름은 2개 이상이 아니어도 된다(1개면 단일 호출). 중복된 브랜드 이름은 오류. `source: "shopping"`이면 `category` 필수. `estimateTrendCalls`로 예상 호출 수를 구해 `checkBudget`을 통과해야 하며, `dryRun`이면 호출 없이 `estimatedCalls`만 채워 반환한다. 초기 기준은 `input.anchor` 또는 첫 브랜드. 결과에 `lowPrecision` 브랜드가 있고 `input.anchor`가 없으면 `pickMedianAnchor`로 기준을 바꿔 **한 번만** 다시 계산한다(`reanchored: true`). 재계산은 `maxCalls - counter.used ≥ estimatedCalls`일 때만 하고, 아니면 `warnings`에 "정밀도 낮음 브랜드가 있으나 호출 예산이 부족해 재기준을 생략" 사유를 싣는다. 재계산 후에도 `lowPrecision`이 남으면 `warnings`에 해당 브랜드명을 싣는다. 쇼핑 키워드 응답이 비어 있으면(`results`가 비었거나 모든 값이 0) 해당 브랜드를 `warnings`에 "해당 분야에서 데이터 없음/희소"로 싣고 오류로 처리하지 않는다. 브랜드 매핑: 검색은 `keywordGroups: [{groupName: brand.name, keywords: brandKeywords(brand)}]`, 쇼핑은 `keyword: [{name: brand.name, param: brandKeywords(brand)}]`.

- [ ] **Step 1: 실패하는 테스트 작성.** 가짜 `api`(호출 기록 + 미리 정한 응답)와 임시 폴더 캐시를 쓴다.
  - 브랜드 6개(A~F), 검색어 트렌드: 호출이 2번이고, 각 호출의 `keywordGroups[0].groupName`이 기준 브랜드 A, 두 번째 호출은 `["A","F"]`. 결과는 Task 4의 환산 값과 일치한다.
  - `dryRun: true`면 `api` 호출 0번, `estimatedCalls === 2`.
  - `maxCalls: 1`이고 브랜드 6개면 `BudgetExceededError`. `confirm: true`면 진행.
  - 같은 입력으로 두 번 실행하면 두 번째는 `callsUsed === 0`, `cacheHits === 2`.
  - 낮은 정밀도 브랜드가 있으면 재기준이 일어나 `reanchored === true`, `anchor`가 바뀐다. `input.anchor`를 지정하면 재기준하지 않고 `warnings`에 해당 브랜드명이 있다.
  - `source: "shopping"`에 `category`가 없으면 `/category/` 오류. 쇼핑 호출의 요청 바디에 `category`와 `keyword: [{name, param}]`이 들어간다.
  - `source: "shopping"`에 `device`를 주면 오류.
  - 쇼핑 응답의 한 브랜드가 모두 0이면 오류 없이 `warnings`에 "데이터 없음/희소".
  - 브랜드 이름 중복이면 오류.
  - **보안:** 오류 메시지와 결과 JSON에 `"SECRET-KEY-123"`이 없다(가짜 `api`가 던지는 오류에는 포함시키지 않고, 결과 직렬화에 환경변수 값이 섞이지 않음을 확인).
- [ ] **Step 2: 실패 확인.** Run: `npm run build && node --test tests/compare-trend.test.js` / Expected: FAIL
- [ ] **Step 3: 구현.** 검색어 트렌드 `ages` 코드는 사용자가 준 문자열 배열을 그대로 전달한다(`1`~`11`).
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: Commit.** `git add src/analysis/compare-trend.ts tests/compare-trend.test.js && git commit -m "feat: add brand comparison trend with anchor rescaling"`

---

### Task 6: 글 수집, 필터, 월별 집계

**Files:**
- Create: `src/analysis/mentions.ts`
- Test: `tests/mentions.test.js`

**Interfaces:**
- Consumes: Task 2 `Brand`, `brandKeywords`, `matchesBrand`; Task 3 `FileCache`, `CallCounter`, `cachedCall`; Task 5 `AnalysisApi`.
- Produces:
  - `type MentionSource = "blog" | "cafearticle" | "webkr"`
  - `type Post = { source: MentionSource; title: string; description: string; link: string; date?: string }` — `date`는 `yyyy-mm-dd`, 없으면 `undefined`.
  - `stripHtml(s: string): string` — 태그 제거, 엔티티(`&quot; &amp; &lt; &gt; &#39; &nbsp;`) 복원, 연속 공백 정리.
  - `normalizePost(source: MentionSource, raw: any): Post` — `postdate`가 `^\d{8}$`면 `yyyy-mm-dd`로 바꾼다(형식은 Task 1 C의 결과를 따른다). 그 외는 `date` 없음.
  - `collectPosts(api: AnalysisApi, source: MentionSource, query: string, maxPosts: number, ctx: { cache: FileCache; counter: CallCounter }): Promise<{ posts: Post[]; total: number }>` — `sort: "date"`, `display: 100`, `start`를 1, 101, … 로 올리며 `maxPosts`(최대 1000)나 `total`에 닿거나 빈 페이지가 나올 때까지 수집한다. `link` 기준 중복 제거.
  - `filterByBrands(posts: Post[], brands: Brand[]): { kept: Array<Post & { brands: string[] }>; excluded: number }` — 제목+요약(태그 제거 후)에 어느 브랜드의 키워드라도 들어 있는 글만 남기고, 포함된 브랜드명 목록을 붙인다.
  - `monthlyCounts(kept: Array<Post & { brands: string[] }>): { rows: Array<{ month: string; brand: string; source: MentionSource; count: number }>; undated: Record<MentionSource, number> }` — `month`는 `yyyy-mm`. 날짜 없는 글은 `undated`에 센다. 카페글이 모두 날짜 없음이면 `rows`에 카페 행이 없다.
  - `estimateMentionCalls(brands: Brand[], sources: MentionSource[], queriesPerBrand: number, maxPosts: number): number` — `brands × sources × queriesPerBrand × ceil(maxPosts/100)`.

- [ ] **Step 1: 실패하는 테스트 작성.**
  - `stripHtml("<b>천일문</b> &quot;후기&quot; &amp; 정리")` → `천일문 "후기" & 정리`.
  - `normalizePost("blog", {title, link, description, postdate:"20250312"})`의 `date === "2025-03-12"`. `postdate:""`, `postdate:"2025-3"`, 필드 없음은 `date === undefined`이고 예외 없음.
  - `collectPosts`: 가짜 `api.search`가 `total: 250`에 페이지당 100건씩 줄 때 호출은 3번(start 1, 101, 201), 요청 파라미터에 `sort:"date"`, `display:100`. `maxPosts: 150`이면 2번 호출하고 150건. 같은 `link`는 한 번만. 빈 페이지가 오면 중단. 두 번째 실행은 캐시로 `counter.used`가 늘지 않는다.
  - `filterByBrands`: `<b>`로 감싸진 제목("<b>그래머</b> <b>인사이드</b>")도 매칭된다. 어느 브랜드도 없는 글은 `excluded`에 센다.
  - `monthlyCounts`: 날짜 있는 글은 `yyyy-mm` × 브랜드 × 소스로 센다. 글 하나에 브랜드가 둘이면 두 브랜드에 각각 1건. 날짜 없는 글은 `undated`.
  - `estimateMentionCalls(2 brands, ["blog","cafearticle"], 1, 1000)` === 40.
- [ ] **Step 2: 실패 확인.** Run: `npm run build && node --test tests/mentions.test.js` / Expected: FAIL
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: Commit.** `git add src/analysis/mentions.ts tests/mentions.test.js && git commit -m "feat: collect, filter and bucket mention posts"`

---

### Task 7: 동시 언급 후보 추출

**Files:**
- Create: `src/analysis/candidates.ts`
- Test: `tests/candidates.test.js`

**Interfaces:**
- Consumes: Task 2 `Brand`, `brandKeywords`; Task 6 `Post`, `stripHtml`.
- Produces:
  - `type Candidate = { term: string; total: number; byBrand: Record<string, number>; examples: string[]; sources: MentionSource[] }`
  - `const DEFAULT_STOPWORDS: Set<string>` — 후기, 리뷰, 추천, 구매, 정리 등 일반 단어 소규모 목록.
  - `extractCandidates(kept: Array<Post & { brands: string[] }>, brands: Brand[], opts?: { top?: number; stopwords?: Set<string> }): Candidate[]` — 제목+요약(태그 제거 후)을 `/[가-힣A-Za-z0-9]{2,}/g`로 토큰화한다. 숫자만으로 된 토큰, 불용어, 브랜드 키워드(공백 제거, 소문자 비교)와 같은 토큰은 제외한다. `byBrand[b]`는 글에 브랜드 `b`가 포함된 글에서 나온 횟수. `examples`는 해당 토큰이 들어 있는 문장 조각(최대 100자) 최대 3개. 같은 글에서 같은 토큰이 여러 번 나와도 글당 1회로 센다. `total` 내림차순, 같으면 토큰 사전순으로 상위 `top`(기본 30). 조사 제거(형태소 분석)는 하지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성.**
  - 글 3개(A 브랜드 2개, B 브랜드 1개)에서 공통 단어 "쎄듀"가 3건이면 `total 3`, `byBrand {A:2, B:1}`, `examples.length <= 3`, 각 100자 이하.
  - 브랜드 키워드, 불용어("후기"), 숫자만("2024"), 1글자는 후보에서 제외된다.
  - 같은 글에서 같은 토큰이 3번 나와도 `total`에 1로 반영.
  - `<b>` 태그가 후보 토큰으로 나타나지 않는다(`"b"`, `"<b>"` 없음).
  - `top: 2`면 2개만, 순서는 `total` 내림차순.
- [ ] **Step 2: 실패 확인.** Run: `npm run build && node --test tests/candidates.test.js` / Expected: FAIL
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인.** 같은 명령 / Expected: PASS
- [ ] **Step 5: Commit.** `git add src/analysis/candidates.ts tests/candidates.test.js && git commit -m "feat: extract co-mention candidate terms"`

---

### Task 8: 엑셀/CSV 내보내기

**Files:**
- Create: `src/export/export.ts`
- Modify: `package.json` (`exceljs` 추가, `xlsx` 제거), `package-lock.json`
- Test: `tests/export.test.js`

**Interfaces:**
- Produces:
  - `type Cell = string | number | null`
  - `type Sheet = { name: string; columns: string[]; rows: Cell[][] }`
  - `type ExportResult = { xlsxPath: string; csvPaths: string[] }`
  - `sanitizeBaseName(name: string): string` — 경로 구분자, `..`, 제어 문자, 윈도우 금지 문자(`<>:"/\|?*`)를 `_`로 바꾸고, 앞뒤 공백과 점을 제거한다. 결과가 비면 `"export"`.
  - `neutralizeFormula(v: Cell): Cell` — 문자열이 `=`, `+`, `-`, `@`, 탭, CR로 시작하면 앞에 `'`를 붙인다. 숫자와 null은 그대로.
  - `exportSheets(sheets: Sheet[], opts: { dir: string; baseName: string }): Promise<ExportResult>` — `dir`을 만들고, `<baseName>.xlsx`(시트별 한 시트, 시트 이름은 엑셀 규칙에 맞게 31자 이내로 정리)와 시트별 CSV `<baseName>-<시트이름>.csv`(UTF-8 BOM, 필드의 따옴표/쉼표/개행 이스케이프)를 쓴다. 모든 셀은 `neutralizeFormula`를 거친다. 반환 경로는 모두 `dir` 아래다.

- [ ] **Step 1: 실패하는 테스트 작성** (임시 폴더 사용).
  - `sanitizeBaseName("../../evil")`에 `/`, `\`, `..`이 없다. `sanitizeBaseName("그래머 비교 2025")`는 한글과 공백을 보존. `sanitizeBaseName("...")`는 `"export"`.
  - `neutralizeFormula("=HYPERLINK(\"x\")")` → `'=HYPERLINK("x")`. `neutralizeFormula(-3)` → `-3`. `neutralizeFormula("정상")` 그대로.
  - `exportSheets` 후 `xlsxPath`, `csvPaths[0]`가 존재하고 `dir` 안에 있다(`path.relative`가 `..`로 시작하지 않음). `baseName: "../x"`로 호출해도 `dir` 밖에 파일이 생기지 않는다.
  - CSV는 BOM(`EF BB BF`)으로 시작하고, `"가,나"` 같은 쉼표/따옴표/개행 셀이 올바르게 이스케이프된다. 한글이 깨지지 않는다.
  - `exceljs`로 xlsx를 다시 읽어 시트 이름과 첫 데이터 행이 입력과 같고, 수식 시작 셀이 `'`로 시작한다.
  - 시트 이름이 32자 이상이면 31자 이내로 정리된다.
- [ ] **Step 2: 실패 확인.** Run: `npm install exceljs && npm uninstall xlsx && npm run build && node --test tests/export.test.js` / Expected: FAIL (구현 없음)
- [ ] **Step 3: 구현.**
- [ ] **Step 4: 통과 확인.** Run: `npm run build && node --test tests/export.test.js` / Expected: PASS
- [ ] **Step 5: Commit.** `git add src/export tests/export.test.js package.json package-lock.json && git commit -m "feat: export analysis results to xlsx and csv"`

---

### Task 9: MCP 도구 등록, 노출 필터, 문서

**Files:**
- Create: `src/analysis/tool-filter.ts`, `src/analysis/tools.ts`
- Modify: `src/index.ts` (서버 생성 직후 필터 적용 1줄, 마지막 등록 이후 `registerAnalysisTools` 호출 1줄과 import), `.gitignore`(`exports/`, `.cache/`), `README-ko.md`(새 도구와 환경변수 설명)
- Test: `tests/tool-filter.test.js`, `tests/analysis-tools.test.js`

**Interfaces:**
- Consumes: Task 5 `compareBrandTrend`, `AnalysisApi`; Task 6~7 `collectPosts`, `filterByBrands`, `monthlyCounts`, `estimateMentionCalls`, `extractCandidates`; Task 3 `defaultCache`, `CallCounter`, `checkBudget`; Task 8 `exportSheets`, `Sheet`.
- Produces:
  - `parseToolAllowList(raw: string | undefined): Set<string> | null` — 빈 값이면 `null`(전체 허용), 아니면 쉼표 구분 이름(공백 제거).
  - `applyToolFilter(server: { registerTool: (...args: any[]) => any }, allow: Set<string> | null): void` — 허용 목록이 있으면 `server.registerTool`을 감싸 목록에 없는 이름은 등록하지 않는다.
  - `registerAnalysisTools(server: McpServer, api: AnalysisApi): void` — 도구 2개를 등록한다.
    - `brand_compare_trend`: 입력은 `CompareInput` + `exportAs?: string`. 결과(JSON 문자열)를 `content`로 돌려주고, `exportAs`가 있으면 시계열을 `Sheet`(열: 기간, 브랜드별 지수)와 "한계" 시트로 내보낸 경로를 결과에 포함한다.
    - `brand_mentions`: 입력 `{ brands: Brand[]; sources: MentionSource[] (기본 ["blog","cafearticle"]); maxPostsPerBrand: number (기본 300, 최대 1000); queriesPerBrand: number (기본 1, 최대 3); topCandidates: number (기본 30); maxCalls?; confirm?; dryRun?; exportAs?: string }`. 브랜드마다 `brandKeywords(brand).slice(0, queriesPerBrand)`를 쿼리로 수집하고, 필터, 월별 집계, 후보 추출을 거쳐 `{ monthly, undated, total(소스별 API total), excluded, candidates, callsUsed, cacheHits, estimatedCalls, warnings, limitations }`를 돌려준다. 카페글이 전부 날짜 없음이면 `warnings`에 "카페글은 날짜 정보가 없어 월별 집계에서 제외" 문구를 싣는다.
  - 도구 이름 상수로 `NAVER_TOOLS_ALLOW`에서 쓸 수 있는 이름을 문서화한다: 기존 이름(`search_blog` 등)과 `brand_compare_trend`, `brand_mentions`.

- [ ] **Step 1: 실패하는 테스트 작성.**
  - `parseToolAllowList(undefined)`와 `""`는 `null`. `" search_blog , brand_mentions "`는 두 이름의 Set.
  - `applyToolFilter`: 가짜 `server.registerTool`에 이름 3개를 등록 시도하고, 허용 목록 2개만 원본에 전달된다. `null`이면 전부 전달된다.
  - `registerAnalysisTools`: 가짜 서버(등록 인자를 저장)에 `brand_compare_trend`, `brand_mentions`가 각각 한 번 등록되고, 핸들러를 직접 호출해 가짜 `api`로 결과 JSON에 `limitations`가 비어 있지 않음을 확인한다. `dryRun: true`로 호출하면 `api` 호출 0번.
  - `brand_mentions`의 카페 전부 날짜 없음 시나리오에서 `warnings`에 카페 제외 문구가 있다.
  - `exportAs`를 주면 `NAVER_EXPORT_DIR`(테스트에서 임시 폴더로 설정)에 xlsx와 csv가 생기고 결과에 경로가 있다.
- [ ] **Step 2: 실패 확인.** Run: `npm run build && node --test tests/tool-filter.test.js tests/analysis-tools.test.js` / Expected: FAIL
- [ ] **Step 3: 구현.** `src/index.ts`의 기존 `server.registerTool(` 호출이 반환값을 쓰지 않는지 먼저 확인한다(`grep -n "= server.registerTool" src/index.ts`). 필터는 `const server = new McpServer(...)` 직후, 등록 호출은 마지막 기존 `registerTool` 뒤에 둔다. 도구 설명은 기존 스타일(이모지 + 영어 + 한글)로 쓴다.
- [ ] **Step 4: 통과와 전체 테스트 확인.** Run: `npm test` / Expected: 기존 40개 테스트와 신규 테스트 모두 PASS
- [ ] **Step 5: 서버 기동 스모크.** Run: `NCP_APIGW_API_KEY_ID=x NCP_APIGW_API_KEY=y NAVER_TOOLS_ALLOW=brand_mentions node dist/src/index.js` 로 기동해 stdin을 닫는다. / Expected: 오류 없이 시작하고 종료한다(stderr에 키 값이 출력되지 않는다).
- [ ] **Step 6: Commit.** `git add src/analysis src/index.ts tests .gitignore README-ko.md && git commit -m "feat: register brand analysis tools with tool filter"`

---

### Task 10: 실제 키로 종단 확인

**Files:**
- Modify: `docs/superpowers/specs/2026-10-16-book-brand-analysis-design.md` (§7 아래에 실제 호출 결과 요약)

**Interfaces:**
- Consumes: Task 9까지의 전체. 사용자의 `NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY`.

- [ ] **Step 1: `dryRun` 확인.** "그래머인사이드", "천일문 중등 그래머" 두 브랜드로 `brand_compare_trend`(search, 최근 2년, month)와 `brand_mentions`를 `dryRun: true`로 호출해 예상 호출 수를 확인한다. / Expected: 각각 1회, 40회 안팎(상한 30을 넘으면 `confirm`이 필요하다는 안내).
- [ ] **Step 2: 실제 실행.** `brand_compare_trend`를 실행해 두 브랜드의 월별 지수와 `limitations`를 확인하고, `exportAs`로 xlsx와 CSV가 생성되는지, 엑셀에서 한글이 정상 표시되는지 확인한다. 같은 호출을 다시 해서 `callsUsed: 0`(캐시)을 확인한다.
- [ ] **Step 3: `brand_mentions` 실행**(`maxPostsPerBrand: 100`으로 작게) 후, 후보 목록에 같은 카테고리의 다른 교재가 나오는지, 노이즈 글이 `excluded`로 걸러지는지 확인한다. 결과 요약을 스펙에 적는다.
- [ ] **Step 4: Commit.** `git add docs && git commit -m "docs: record end-to-end verification results"`

---

## Self-Review

- **Spec coverage:** §4(기준 보정, 브랜드 두 입력 방식, 출력, 포크 방식) → Task 4~5, 7, 8, 9. §5.2의 도구 2개와 내보내기 → Task 5, 6~7, 8. §5.3 캐시와 호출 예산 → Task 3(검색 호출도 같은 카운터로 센다). §5.4 도구 노출 제어 → Task 9. §5.5 경계 → Global Constraints. §7 검증 → Task 1, 10. §8 한계 문구 → Global Constraints와 각 결과의 `limitations`. §9-1~6 → Task 3, 5, 6, 1, 5, 7. 월 한도 자체 집계는 스펙이 빌더 몫으로 남겼고 YAGNI로 제외했다(응답의 `callsUsed`만 제공).
- **스펙과 다른 점 하나:** 스펙 §5.2는 기준 브랜드를 "사전 호출로 가늠해" 고른다고 했지만, 이 계획은 사전 호출 대신 §9-2의 자동 재기준(1회)으로 대체한다. 호출 수를 줄이고 같은 목적(기준이 너무 작거나 큰 경우 보정)을 달성한다.
- **타입 일관성:** `AnalysisApi`(Task 5)를 Task 6, 9가 쓰고, `Post`/`MentionSource`(Task 6)를 Task 7, 9가 쓴다. `Brand`, `ScaledSeries`, `Sheet` 이름이 모든 Task에서 같다.
- **Review Focus 매핑:** 다섯 항목 모두 해당 Task의 테스트에 있다(Task 3 보안, Task 4 기준 0, Task 6 태그와 날짜, Task 8 경로와 수식).
