# ne-naver-api-mcp 파이썬 재작성 설계

작성일: 2026-10-21
작업 위치: 이 저장소의 `python-rewrite` 브랜치 (git worktree `<worktree>`). 현재 Node/TypeScript 버전은 태그 `node-v1`(커밋 `919e1ba`)로 보존한다.

표기: **[결정]** 사용자가 정한 것, **[내 판단]** 설계자(Claude)가 정한 것(검토 필요), **[빌더 몫]** 구현자가 정할 것.

## 1. 의도와 이유

NAVER API HUB(검색, Data Lab)를 쓰는 MCP 서버를 **파이썬으로 새로 만든다.** 기능은 현재 Node 버전과 같고, 도구 범위는 **원본 18개 전부 + 분석 도구 2개**다. **[결정]**

파이썬을 택한 이유(사용자 판단): `uvx` 설치, 한국어 형태소 분석기(kiwipiepy)로 동시 언급 후보 품질 개선, 엑셀 처리 편의. **[결정]**

## 2. 목표 / 비목표 / 안티 목표

**목표**
- 도구 20개를 파이썬으로 제공한다 (§4).
- Node 버전과 **동작이 같다**. 같은 입력에 같은 결과, 같은 경고, 같은 한계 표시. 기준은 Node 설계서(`docs/superpowers/specs/2026-10-16-book-brand-analysis-design.md`) §1~§11이다.
- 동시 언급 후보 추출은 형태소 분석(kiwipiepy)으로 개선한다 (조사 분리, 브랜드명 보존).
- `uvx`로 GitHub에서 바로 설치/실행할 수 있다.

**비목표**
- 단일 exe 배포(PyInstaller 등). 요청이 있을 때 따로 한다.
- 개발자센터(legacy) 키 지원. NAVER API HUB 키만 지원한다 **[내 판단]** (원본 README 기준 신규 발급이 막혔고 2027-06-30 종료).
- 원본 저장소 업데이트의 병합. 파이썬 재작성 후에는 그 경로가 없다. **[결정]**(방향 수용)

**안티 목표**
- Node 버전에서 검토와 실사용으로 잡은 문제를 되살리는 것: 데이터 없는 브랜드로 인한 오류, 승인 호출 수 초과, 파일명 백슬래시 문제, 내보내기 실패 시 결과 손실, 상대 지수를 실제 값처럼 보이게 하는 표시 (§5 체크리스트).
- 키가 로그, 캐시, 오류 메시지, 내보내기 파일에 노출되는 것.
- MCP 표준 출력(stdout)에 프로토콜 외 텍스트가 섞여 서버가 깨지는 것 (로그는 stderr).

## 3. 제약

- 파이썬 3.11 이상. 이 PC의 uv가 쓰는 3.12와 설치된 3.14.6 양쪽에서 확인된 의존성만 쓴다. **[내 판단]**
- MCP SDK는 `mcp` **2.x**(2026-10 기준 2.3.0)를 쓴다. 2.x에서 `FastMCP`가 `MCPServer`(`from mcp.server.mcpserver import MCPServer`)로 바뀌었다. **[내 판단]** (확인: 2026-10-21 임시 환경에서 3.12/3.14 설치 성공, `mcp.server.fastmcp`는 없음)
- API 한도와 사양은 Node 설계서 §3, §10과 같다: 검색 `display` 1~100, `start` 1~1000, 키워드 그룹 5개, 쇼핑 키워드 그룹당 `param` 1개, 쇼핑 `category` 최대 3쌍 등. 월 한도 검색 775,000건, Data Lab 각 50,000건.
- 환경변수 이름은 Node 버전과 같게 유지한다: `NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY`, `NAVER_EXPORT_DIR`, `NAVER_CACHE_DIR`, `NAVER_CACHE_TTL_HOURS`, `NAVER_TOOLS_ALLOW`. **[내 판단]**
- 라이선스: 원본(isnow890, MIT)의 코드(HUB 호출 방식, 인증 처리, `data/categories.json`)를 옮기므로 `LICENSE`와 README의 출처 표기를 유지한다.

## 4. 도구 목록 (이름과 인자는 Node 버전과 동일 **[결정]**)

| 구분 | 도구 |
|---|---|
| 카테고리 (1) | `find_category` (자연어로 쇼핑 분야 코드 검색, 유사 일치) |
| 검색 (8) | `search_webkr`, `search_news`, `search_blog`, `search_cafearticle`, `search_image`, `search_kin`, `search_encyc`, `search_local` |
| 데이터랩 (9) | `datalab_search`, `datalab_shopping_category`, `datalab_shopping_by_device`, `datalab_shopping_by_gender`, `datalab_shopping_by_age`, `datalab_shopping_keywords`, `datalab_shopping_keyword_by_device`, `datalab_shopping_keyword_by_gender`, `datalab_shopping_keyword_by_age` |
| 분석 (2) | `brand_compare_trend`, `brand_mentions` |

- 인자 스키마와 도구 설명(이모지 + 영어 + 한글)은 `node-v1` 태그의 `src/index.ts`, `src/schemas/*.ts`를 기준으로 옮긴다. 날짜 인자는 `"today"`(KST 기준)를 지원한다.
- `search_local`, `search_news`, `search_image`, `search_kin`, `search_encyc`의 HUB 경로는 아직 실제 키로 확인하지 않았다 (확인한 것은 blog, cafearticle, webkr, 검색어 트렌드, 쇼핑 8종). §8의 검증 항목이다. 유효하지 않은 도구는 등록하지 않고 README에 이유를 적는다.
- `NAVER_TOOLS_ALLOW`로 노출할 도구를 제한한다. 허용 목록에 없는 이름이 섞이면 stderr에 경고한다 (Node 버전에서 미뤄 둔 항목을 이번에 포함). **[내 판단]**

## 5. 동작 동일성 체크리스트 (Node 설계서 §5~§11, 코드 검토 수정 포함)

모두 파이썬에서도 테스트로 증명한다.

1. **기준 키워드 환산**: 배치마다 기준 브랜드를 고정 슬롯에 넣고 합계 비율로 환산. 배치 하나면 환산 없음. 기준이 0/누락이면 명확한 오류 (다중 배치).
2. **데이터 없는 브랜드**: 5개 이하는 오류 없이 "데이터 없음/희소" 경고. 기준이 비면 첫 묶음의 최대 브랜드로 기준 교체. 모두 0이면 첫 묶음만 표시하고 경고. 중앙값 기준 선택은 합계 0 브랜드를 제외.
3. **정밀도 표시**: 최댓값 < 1이거나, 다중 배치에서 기준의 지수가 해당 배치에서 1 미만이면 "정밀도 낮음". 값이 100을 넘을 수 있음을 한계 문구에 명시.
4. **자동 재기준**: 정밀도 낮은(값이 0이 아닌) 브랜드가 있고, 기준 미지정, 배치 2개 이상, 승인 예산 이내일 때만 1회. 재계산 시 비슷한 크기끼리 배치. 예산 초과(`confirm`이어도 예상 호출 수까지만) 시 생략하고 경고. `estimatedCalls`와 `estimatedCallsMax`를 보고.
5. **쇼핑**: `category` 필수, `device/gender/ages` 불가, 키워드 그룹당 1개(이름), 이름에 데이터가 없으면 별칭을 순서대로 최대 2개 시도 (예산 내). 별칭이 쓰이지 않았다는 안내 경고.
6. **호출 보호**: 파일 캐시(TTL 24시간, 응답 값만 저장, 키/params 미저장), 호출 상한(기본 30, `confirm`, `dryRun`), 실행 전 브랜드 검증(키워드 20개 초과, 빈 이름).
7. **언급 분석**: 최근 순 수집(기본 검색어당 100건, 최대 1000, `start` ≤ 1000), 링크 중복 제거, `<b>`와 HTML 엔티티 제거 후 브랜드 매칭(공백/대소문자 무시), 날짜 없는 글은 `undated`, 카페/웹은 월별 집계 제외 경고, 표본이 잘린 소스는 `oldestDate`/`truncated`/`comparableFrom`과 월별 `partial` 표시 및 경고, `baselineQuery`로 일반 단어 제거(`genericRate` 기본 0.15, `baselineRate`, `lift`).
8. **내보내기**: xlsx 하나와 시트별 CSV(UTF-8 BOM). 파일명에서 `\ / : * ? " < > |`, 제어 문자, `..` 치환 (백슬래시 포함), 지정 폴더 밖에 쓰지 않음, `= + - @` 탭 CR로 시작하는 셀은 앞에 `'`. 시트 이름 31자 이내·금지 문자 치환. 내보내기가 실패해도 분석 결과를 돌려주고 경고.
9. 모든 분석 결과에 `limitations`(상대 지수, 근사, 후보) 포함, 엑셀에도 "한계" 시트.

## 6. Node 버전과 다른 점 (의도한 것)

- **후보 추출**: 정규식 토큰 대신 kiwipiepy 형태소 분석. 명사(NNG, NNP), 외래어/영문(SL), 어근(XR)만 후보로 삼는다. 조사는 분석 단계에서 분리되므로 "브랜드명+조사" 예외 처리는 필요 없다. 브랜드 이름과 별칭은 사용자 사전에 고유명사로 등록해 쪼개지지 않게 한다 (확인: "워크북"이 "워크"+"북", "NE능률"이 "NE"+"능률"로 쪼개지는 경우가 있다). 모델은 처음 필요할 때 한 번만 불러온다(서버 시작을 늦추지 않는다). **[내 판단]**
- **`.env`**: 서버는 환경변수를 우선 쓰고, 없으면 현재 작업 폴더의 `.env`가 있을 때 읽는다. 환경변수가 항상 이긴다. **[내 판단]**
- **설치**: `uvx --from git+https://github.com/neneungyul2/ne-naver-api-mcp ne-naver-api-mcp` (콘솔 스크립트 이름 `ne-naver-api-mcp`). 구체적인 동작은 구현 중 확인한다.
- 개발자센터(legacy) 키 미지원 (§2).

## 7. 저장소 전략 **[내 판단 — 승인 필요]**

- 작업은 로컬 브랜치 `python-rewrite`(worktree)에서만 한다. 첫 커밋에서 Node 파일(`src/`, `package.json`, `tsconfig.json`, `Dockerfile`, JS 테스트 등)을 제거하고 파이썬 프로젝트를 만든다. 문서(`docs/`), 라이선스, 녹화 샘플(`tests/fixtures/`), `data/categories.json`은 유지한다.
- Node 버전은 태그 `node-v1`로 남긴다 (태그는 로컬에만 있다).
- **공개 저장소 `main`을 파이썬 버전으로 바꾸는 것과 태그/브랜치 푸시는 사용자가 확인한 뒤에만 한다.** 구현 중에는 푸시하지 않는다.
- 커밋 작성자는 `neneungyul2 <neneungyul2@gmail.com>` (저장소 설정이 이미 되어 있다). 샘플과 문서에 개인 정보나 제3자 글을 넣지 않는다 (공개 저장소).

## 8. 구현 전/중에 실제 키로 확인할 사실

- `/search/v1/news`, `image`, `kin`, `encyc`, `local`의 유효 여부와 응답 구조 (호출 약 5회).
- 쇼핑 `category/keyword/*`, 연령/기기/성별 8종의 파이썬 구현이 Node와 같은 응답을 받는지 (기존 샘플과 대조).
- MCP SDK 2.x의 `MCPServer` 도구 등록/인자 스키마 방식과 stdio 실행. 실제 MCP 클라이언트로 연결해 도구 목록과 호출이 되는지.
- `uvx --from git+...` 설치와 실행 (Windows).
- kiwipiepy가 설치된 모든 대상 파이썬(3.12, 3.14)에서 동작 (임시 환경에서는 확인됨).

## 9. 빌더 몫

- 패키지 구조(`src/ne_naver_api_mcp/...`), 모듈 분리, 타입 표기(pydantic 모델 vs 데이터클래스).
- 비동기(httpx.AsyncClient)와 동기 중 선택. MCP 서버가 비동기 도구를 지원하므로 비동기를 권장.
- 테스트 도구: pytest. 가짜 API 주입 방식은 Node 테스트와 같게 하고, 녹화 샘플 기반 계약 테스트와 라이브 테스트(`NAVER_LIVE_TEST=1`일 때만, 기본 건너뜀)를 둔다. Node 테스트 파일 하나를 파이썬 테스트 파일 하나로 옮기고, 같은 케이스를 모두 포함한다 (143개 중 라이브 5개 제외 138개가 기준선).
- 형태소 분석 후보의 세부(복합명사 처리, 불용어, 후보 개수)는 §5-7의 동작과 테스트가 통과하는 선에서 정한다.
- 의존성 버전 하한, 빌드 백엔드(hatchling 등), 린트 설정.

## 10. 구현자 검토 후 확정한 판단 (모두 내 판단 — 검토 필요)

1. **legacy 키만 설정된 경우**: 서버를 시작하지 않고 명확한 오류로 종료한다. 메시지에 필요한 HUB 변수 이름(`NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY`)과 "개발자센터 키는 지원하지 않는다"를 적는다. HUB 키가 반쪽이면 어느 쪽이 빠졌는지 알려 주는 Node 버전의 오류 형식은 유지한다. 자격증명 테스트는 HUB 케이스만 옮기고 legacy 케이스는 "legacy만 있으면 오류" 한 건으로 대체한다.
2. **후보 테스트와 토크나이저**: 후보 추출은 토크나이저를 주입받는 순수 함수로 만든다 (`tokenize(text) -> list[str]`). 집계, 일반 단어 제거, `baselineRate`, `lift`, 정렬, 예시 문장 같은 로직의 테스트는 Node 테스트의 입력과 기대값 그대로 옮기되 **정규식 토크나이저(Node와 같은 규칙)를 주입**해 검증한다. 이 부분은 숫자(total, rate, lift)까지 같아야 한다. 형태소 분석 기반 토크나이저(kiwipiepy)는 별도 테스트로 검증한다: 조사 분리("그래머인사이드는" → "그래머인사이드"), 사용자 사전의 브랜드 보존, 명사/외래어만 통과, 영문은 소문자화. 기준 검색 글과 브랜드 글은 **같은 토크나이저**를 거친다. 도구(`brand_mentions`)의 기본 토크나이저는 kiwipiepy다. 따라서 "같은 입력에 같은 결과" 원칙은 토크나이저가 같을 때 적용되고, 기본 토크나이저를 쓰는 종단 결과는 후보 단어 목록이 달라질 수 있다 (의도한 것).
3. **API 키**: 사용자가 키를 이미 `.env`에 갖고 있다. 구현자는 Node 폴더의 `.env`를 파이썬 작업 폴더로 복사해 쓴다 (둘 다 gitignore 대상, 커밋하지 않는다). HUB 경로 확인(§8)은 구현 첫 단계에 한다. **확인되지 않은 도구는 등록하지 않는다.** 확인되면 등록하고 README에 "확인일"을 적는다.
4. **uvx 설치 확인**: 구현 중에는 로컬 경로(`uvx --from <worktree 경로> ne-naver-api-mcp`)로 확인한다. GitHub 주소로 설치하는 확인은 사용자가 푸시를 승인한 **뒤의 마지막 단계**이며 구현 계획의 완료 조건에는 넣지 않는다.
5. **§7에 없던 파일**: 
   - `skills/naver-search-mcp/SKILL.md`: uvx/파이썬 기준으로 다시 쓴다 (node, legacy 변수 언급 제거).
   - `scripts/record-fixtures.mjs` → `scripts/record_fixtures.py`로 옮긴다 (샘플 정리 규칙 포함). `run-live-tests.mjs`와 `verify-hub.mjs`는 라이브 테스트(`pytest -m live`)가 대체하므로 삭제한다. `smoke-endpoints.mjs`도 삭제한다.
   - `README-ko.md`, `README.md`, `README-en.md`: 파이썬/uvx 기준으로 다시 쓴다. 한국어 README를 먼저 완성하고 영문은 같은 구조로 옮긴다. 포크 출처 안내는 유지한다.
   - `RELEASE_NOTES.md`(원본 Node 릴리스 노트), `Dockerfile`, `.dockerignore`: 삭제한다. `.env.example`은 파이썬 기준으로 갱신한다.
6. **테스트 기준선**: 138개는 합격 기준이 아니다. 규칙은 "Node 테스트 파일 하나당 파이썬 테스트 파일 하나, **해당되는 모든 케이스를 포함**"이다. 파이썬에서 의미가 없는 케이스(예: Node 클라이언트 싱글톤 내부, 제거된 도구 확인, legacy 키 케이스)는 `docs/superpowers/parity.md`에 파일별로 "이식함/대체함/해당 없음(이유)"로 적는다.

## 11. §8 검증 결과 (2026-10-21, 실제 키, `tests/live/test_hub_endpoints.py`)

| 항목 | 결과 |
|---|---|
| `webkr`, `blog`, `cafearticle` | 유효 (응답 구조는 Node 확인과 같다) |
| `news`, `image`, `kin`, `encyc`, `local` | 요청이 HTTP 401 `요청한 API는 이 Application에서 활성화되어 있지 않습니다.`로 거절됨. 존재하지 않는 경로는 HTTP 404 `URL not found`로 다르게 응답하므로 **경로는 HUB에 있고, 현재 Application에 이 API가 추가되지 않은 것**이다. 응답 구조는 이 계정으로 확인할 수 없다 (미확인) |
| 검색어 트렌드, 쇼핑 인사이트 8종 | 모두 유효 (Node에서 확인한 사실과 같음: 그룹 5개, `param` 1개 제한) |

**결정(내 판단):** 위 5개 검색 도구도 등록한다 (사용자가 원본 18개 전부를 요청했고, 404가 아니므로 경로는 존재한다). 도구 설명과 README에 "NCP 콘솔 > NAVER API HUB에서 Application에 해당 API를 추가해야 하며, 응답 구조는 미확인"을 적는다. `UNVERIFIED_OR_INVALID`는 비워 둔다. 401 오류 메시지는 "키 확인"이 아니라 "Application에 API 추가"를 안내하도록 구분했다 (`errors.py`).
