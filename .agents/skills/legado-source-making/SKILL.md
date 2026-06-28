---
name: legado-source-making
description: Create, repair, and validate Legado-compatible child book sources for this project. Use when adding a website as a source under backend/data/sources, writing ruleSearch/ruleBookInfo/ruleToc/ruleContent selectors, handling mobile/desktop domain differences, or proving a source works through the backend rule engine and HTTP client.
---

# Legado Source Making

## Workflow

1. Inspect existing project behavior before writing rules:
   - Read `backend/app/models/source.py` for accepted source fields.
   - Read `backend/app/core/rule_engine.py` for supported rule syntax.
   - Read `backend/app/api/public.py` for URL matching and response flow.
   - Compare existing JSON files in `backend/data/sources/`.

2. Discover the target site with plain HTTP requests:
   - Find the search form action and parameter names.
   - Open one working search result and identify detail fields.
   - Follow the catalog link and confirm whether it is full or paginated.
   - Open at least one chapter and identify the cleanest content container.
   - Prefer `Invoke-WebRequest`, `urllib`, or project `http_client`; do not use Playwright unless explicitly requested.

3. Write source rules using the project's supported subset:
   - Use CSS `selector@text`, `selector@href`, `selector@src`, or `selector@html`.
   - Use Legado index suffixes only at the end of a selector segment, such as `.block_txt2 p.0@text`.
   - For nested "first/second field" extraction, prefer standard CSS such as `p:nth-of-type(2) a@text` or `span:nth-of-type(2)@text`; it is more portable than chaining index suffixes through multiple selector segments.
   - Use `##regex##replacement` or `##regex` to clean labels and noise.
   - Use `{{encodeURIComponent(key)}}` in `searchUrl` when the site expects encoded Chinese keywords.
   - Keep `bookSourceUrl` on the domain that should own detail/content URLs.
   - When a site uses a common mobile novel layout, try these generic anchors before inventing bespoke rules:
     - Search/list item: `.container .item`
     - Title: `.itemtxt h3 a@text||.itemtxt h1 a@text`
     - Author label: `.itemtxt p:nth-of-type(2) a@text##作者：\s*##`
     - Cover/detail URL: `.item > a img@src` and `.item > a@href`
     - Detail intro: `.des.0@text`
     - Catalog list: `#list li`
     - Chapter content: `.con@html` plus normal HTML cleanup filters.

4. Handle catalog edge cases:
   - If the mobile catalog is paginated but the desktop catalog has all chapters, extract the mobile detail page's catalog link and transform it to the desktop full catalog URL.
   - If crossing from `m.example.com` to `www.example.com`, ensure backend source matching can still find the intended source.
   - If another enabled source owns the exact desktop host, append `?sourceId=<current-source-id>` to generated internal `tocUrl` and make `_find_source_by_url` honor that hint before host matching.
   - Transform desktop chapter links back to the mobile chapter URL when desktop chapter pages are empty, encrypted, or otherwise not supported by the current rule engine.
   - For same-page catalog pagination, use text-specific next rules such as `.pages a:contains('下一页')@href`; avoid broad "last link" selectors because final pages often still contain previous-page controls.
   - For multi-page chapter content, use text-specific next rules such as `.prenext a:contains('下一页')@href`; do not match `下一章`, or the backend may merge later chapters into the current chapter.

5. Validate the source end to end:
   - Load the JSON through `BookSource` or `source_manager.load_all(force=True)`.
   - Build and execute search with `build_search_request` and `execute_request`.
   - Apply `RuleEngine.apply_rules` for search, book info, toc, and content.
   - Verify at minimum: search returns the target book, detail returns name/author/tocUrl, toc returns many chapter URLs, and content length is nontrivial.
   - Validate at least two books when possible: one long completed book with paginated catalog/content and one current serial book with a latest chapter.
   - Prefer direct async calls to the project helper functions for multi-step HTTP validation. `TestClient` can create a different event loop per request, which may not mix well with the singleton aiohttp client.
   - Run backend tests with `python -m pytest` from `backend/`.

## Project Rule Notes

- Source files live in `backend/data/sources/<uuid>.json`; include `id`, `createdAt`, and `updatedAt` when writing a static source file.
- `ruleSearch.bookList` and `ruleToc.chapterList` are list roots; child rules run against each list item.
- Relative `noteUrl`, `coverUrl`, `tocUrl`, and `chapterUrl` are resolved by backend APIs after extraction.
- The backend HTTP client may need `trust_env=True` to honor system proxy settings used by Python/urllib and Windows tooling.
- Avoid adding unsupported Legado-only rules such as custom encrypted content markers unless the project runtime implements them.

## Example Pattern From `m.xsw.tw`

- Search: `https://m.xsw.tw/modules/article/wap_search.php?searchkey={{encodeURIComponent(key)}}`
- Search list: `.bookbox`
- Mobile detail: `/1713745/`
- Mobile detail fields: `.block_txt2 h2@text`, `.block_txt2 p.0@text##作者：\s*##`, `.intro_info@text`
- Full catalog: transform `/1713745/page-1.html` to `https://www.xsw.tw/book/1713745/?sourceId=<source-id>`
- Catalog list: `.liebiao li`
- Chapter URL transform: `/book/1713745/250143505.html` to `https://m.xsw.tw/1713745/250143505.html`
- Content: `#nr1@html` with optional cleanup for watermark-like punctuation.
