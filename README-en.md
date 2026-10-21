# ne-naver-api-mcp

An MCP (Model Context Protocol) server for NAVER API HUB (Search and DataLab). Besides Naver web/blog/cafe search, search-trend and shopping-insight tools, it provides **analysis tools that compare search, shopping and mention trends of book-brand products** (`brand_compare_trend`, `brand_mentions`) with xlsx/CSV export.

> **Fork notice:** Based on [isnow890/naver-search-mcp](https://github.com/isnow890/naver-search-mcp) (MIT License). The original Node/TypeScript HUB calling logic, credential handling and shopping category data (`categories.json`) were ported to Python and analysis features were added. The original copyright notice and license are kept in [`LICENSE`](LICENSE). The Node version is kept at tag `node-v1`.

## Tools (20)

| Group | Tools |
|---|---|
| Category | `find_category` — find shopping category codes from natural language |
| Search | `search_webkr`, `search_blog`, `search_cafearticle`, `search_news`, `search_image`, `search_kin`, `search_encyc`, `search_local` |
| DataLab | `datalab_search`, `datalab_shopping_category`, `datalab_shopping_by_device`, `datalab_shopping_by_gender`, `datalab_shopping_by_age`, `datalab_shopping_keywords`, `datalab_shopping_keyword_by_device`, `datalab_shopping_keyword_by_gender`, `datalab_shopping_keyword_by_age` |
| Analysis | `brand_compare_trend`, `brand_mentions` |

Date arguments accept `"today"` (today in Korea Standard Time).

> **APIs must be added to your Application in NAVER API HUB.** As of 2026-10-21, verified: `search_webkr`, `search_blog`, `search_cafearticle` and all DataLab tools. `search_news`, `search_image`, `search_kin`, `search_encyc` and `search_local` exist in the HUB gateway but were not enabled for the Application used for verification (HTTP 401, "the requested API is not activated for this Application"); their response shapes are **unverified**. Add those APIs to your Application in the NCP console.

## Install

Requires [uv](https://docs.astral.sh/uv/) and NAVER API HUB keys (`NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY`).

**Claude Code**

```
claude mcp add ne-naver-api -s user \
  -e NCP_APIGW_API_KEY_ID=YOUR_ID -e NCP_APIGW_API_KEY=YOUR_KEY \
  -e NAVER_EXPORT_DIR=/path/to/naver-exports \
  -- uvx --from git+https://github.com/neneungyul2/ne-naver-api-mcp ne-naver-api-mcp
```

**Claude Desktop** (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "ne-naver-api": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/neneungyul2/ne-naver-api-mcp", "ne-naver-api-mcp"],
      "env": {
        "NCP_APIGW_API_KEY_ID": "YOUR_ID",
        "NCP_APIGW_API_KEY": "YOUR_KEY",
        "NAVER_EXPORT_DIR": "/path/to/naver-exports"
      }
    }
  }
}
```

Installing from the GitHub URL works only once `main` of this repository is the Python version; before that use a local folder: `uvx --from /path/to/ne-naver-api-mcp-py ne-naver-api-mcp`. Pin a commit or tag (`...ne-naver-api-mcp@<commit>`) when distributing.

| Variable | Meaning | Default |
|---|---|---|
| `NCP_APIGW_API_KEY_ID`, `NCP_APIGW_API_KEY` | NAVER API HUB keys (required) | — |
| `NAVER_EXPORT_DIR` | Folder for xlsx/CSV exports (recommended: the server's working directory is chosen by the MCP client) | `<cwd>/exports` |
| `NAVER_CACHE_DIR` | API response cache folder | `<home>/.naver-search-mcp/cache` |
| `NAVER_CACHE_TTL_HOURS` | Cache lifetime in hours | `24` |
| `NAVER_TOOLS_ALLOW` | Comma-separated tool names to expose (empty = all) | all |

Environment variables win; missing keys are read from a `.env` file in the working directory. Without keys the server refuses to start (message on stderr, exit code 1). Naver Developers Center (legacy) keys are not supported.

## Analysis tools

A brand is `{ "name": "...", "aliases": ["..."] }`. Every result carries `limitations`.

- **`brand_compare_trend`** — compares search-trend (`source: "search"`) or shopping-click (`source: "shopping"`, needs `category`) series on **one relative scale**. DataLab ratios are relative per request (max = 100), so an anchor brand is put in every call and batches are rescaled by the anchor's sums. Values are not real counts and may exceed 100. Shopping insight accepts one keyword per group, so the name is queried first and aliases are tried (max 2) only when the name has no data.
- **`brand_mentions`** — collects the most recent blog/cafe/web posts that mention the brands (default 100 per query), counts them per month, and returns co-mentioned **candidate terms** with examples (Korean morphological analysis via kiwipiepy; judge yourself whether a candidate is a brand). The search API has no date filter, so check `comparableFrom` and the per-month `partial` flag. Cafe/web results have no dates and are excluded from monthly counts. `baselineQuery` (e.g. a generic category query) removes words common in generic results.
- Common arguments: `dryRun` (estimate calls only), `maxCalls` (default 30), `confirm`, `exportAs` (writes `<name>.xlsx` and one CSV per sheet).

NAVER API HUB has no API or response header for remaining quota; check the console (NAVER API HUB > Usage Statistics). This server only counts calls within one run and caches identical requests.

## Development

```
uv sync
uv run pytest                                # offline tests; live tests are skipped
NAVER_LIVE_TEST=1 uv run pytest tests/live   # real API checks (needs keys, ~23 calls)
uv run python scripts/record_fixtures.py     # re-record test fixtures (6 calls)
```

Test mapping from the Node implementation: [`docs/superpowers/parity.md`](docs/superpowers/parity.md). Design documents: `docs/superpowers/specs/`.

## License

MIT License — see [`LICENSE`](LICENSE) for the original copyright notice.
