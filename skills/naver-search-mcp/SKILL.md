---
name: naver-search-mcp
description: Use for Korean web/blog/cafe search, Naver DataLab search-trend and shopping-insight analysis, and book-brand comparison (search/shopping trends, mention counts, co-mentioned terms, xlsx/CSV export) through the ne-naver-api-mcp server (NAVER API HUB).
version: 0.1.0
metadata:
  openclaw:
    requires:
      env:
        - NCP_APIGW_API_KEY_ID
        - NCP_APIGW_API_KEY
      bins:
        - uvx
    primaryEnv: NCP_APIGW_API_KEY
    envVars:
      - name: NCP_APIGW_API_KEY_ID
        required: true
        description: NAVER API HUB Client ID (NAVER Cloud Platform console > NAVER API HUB).
      - name: NCP_APIGW_API_KEY
        required: true
        description: NAVER API HUB Client Secret.
      - name: NAVER_EXPORT_DIR
        required: false
        description: Folder for xlsx/CSV exports (recommended; the server's working directory is chosen by the MCP client).
    homepage: https://github.com/neneungyul2/ne-naver-api-mcp
---

# Naver Search MCP (NAVER API HUB)

Use this skill for Korean search tasks that Naver serves better than general web search (blogs, cafe posts, Korean web documents), for DataLab trend analysis, and for comparing book-brand products.

Run the server with `uvx --from git+https://github.com/neneungyul2/ne-naver-api-mcp ne-naver-api-mcp` and pass `NCP_APIGW_API_KEY_ID` / `NCP_APIGW_API_KEY` as environment variables. Naver Developers Center (legacy) keys are not supported.

## Which tool

- Search: `search_blog`, `search_cafearticle`, `search_webkr` (verified). `search_news`, `search_image`, `search_kin`, `search_encyc`, `search_local` need the API to be added to the Application in NAVER API HUB first; if a call returns HTTP 401 "활성화되어 있지 않습니다", tell the user to add that API in the NCP console.
- Trends: `datalab_search` for search-keyword trends. For shopping insight, find the category code first with `find_category` (Korean query such as `도서`, `영어`), then use the `datalab_shopping_*` tools. Date arguments accept `"today"` (KST).
- Brand comparison (book products such as "그래머인사이드" vs "천일문 중등 그래머"): `brand_compare_trend` and `brand_mentions`.

## Brand analysis workflow

1. Define brands as `{ "name": ..., "aliases": [...] }` (aliases = spacing/English variants).
2. Run `dryRun: true` first to see `estimatedCalls`; the default budget is 30 calls (`maxCalls`, `confirm` to go beyond).
3. `brand_compare_trend`: `source: "search"` for search volume trends, `source: "shopping"` (+ `category`) for shopping clicks. Values are **relative indexes**, not counts; they can exceed 100. Read `warnings` (low precision, no data, anchor changes).
4. `brand_mentions`: recent posts only (default 100 per query), so use it for recent tendency and evidence, not long history. Check `comparableFrom` and each month's `partial` flag. Pass `baselineQuery` (a generic category query such as `"중등 영어 문법 교재"`) so generic words are removed from the co-mention candidates. Candidates are **terms, not verified brands**; decide which are brands yourself, then feed the confirmed list back into `brand_compare_trend`.
5. Use `exportAs` to save xlsx/CSV; mention the path from `exported`. If `exportError` is present the analysis is still valid.

Always report `limitations` to the user when presenting numbers.
