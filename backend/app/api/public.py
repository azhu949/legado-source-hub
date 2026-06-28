"""对外开放 API：供阅读 APP 调用的聚合接口。"""

import asyncio
import hashlib
import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import APIRouter, Query, Request

from app.core.aggregator import Aggregator
from app.core.cache import cache
from app.core.legado import build_search_request, execute_request, response_is_json
from app.core.http_client import http_client
from app.core.rule_engine import RuleEngine
from app.core.source_manager import source_manager
from app.models.responses import success, error
from app.utils.helpers import normalize_author, normalize_title, resolve_relative_url, similarity
from app.utils.public_url import get_public_origin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["public"])
_MAX_TOC_PAGES = 20
_MAX_CONTENT_PAGES = 20
_SEARCH_CACHE_VERSION = "rel4"
_BOOK_CACHE_VERSION = "book3"
_TOC_CACHE_VERSION = "toc3"
_TITLE_SIMILARITY_THRESHOLD = 0.82
_AUTHOR_SIMILARITY_THRESHOLD = 0.86


@router.get("/search")
async def search(
    request: Request,
    keyword: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    source_id: str | None = Query(None, alias="sourceId", description="限定子书源ID"),
    source_filter: str | None = Query(None, alias="source", description="限定子书源名称或ID，多个用英文逗号分隔"),
    merge: int = Query(0, ge=0, le=1, description="是否聚合去重：0分源候选，1聚合去重"),
):
    """搜索：默认返回分源候选；merge=1 时聚合去重。"""
    # 记录搜索量
    await cache.incr_search_count()

    keyword, quick_source = _split_keyword_source(keyword)
    source_filter = source_filter or quick_source
    sources = _select_sources(source_id=source_id, source_filter=source_filter)
    sources = [source for source in sources if _source_search_enabled(source)]
    if not sources:
        logger.info(
            "搜索无可用书源 keyword=%r page=%s merge=%s sourceId=%s source=%r",
            keyword,
            page,
            merge,
            source_id,
            source_filter,
        )
        return success(data=[])

    source_scope = _source_cache_scope(sources)
    cached = await cache.get_search(keyword, page, source_scope=source_scope, merge=merge)
    if cached is not None:
        _log_search_cache_hit(keyword, page, merge, cached)
        return success(data=_proxify_search_results(cached, get_public_origin(request)))

    logger.info(
        "开始搜索 keyword=%r page=%s merge=%s sourceId=%s source=%r selected=%s",
        keyword,
        page,
        merge,
        source_id,
        source_filter,
        _source_summary(sources),
    )

    # 并发搜索
    semaphore = asyncio.Semaphore(15)

    async def _search_one(src):
        async with semaphore:
            search_request = await build_search_request(src, keyword, page)
            if not search_request:
                logger.info(
                    "搜索源跳过 keyword=%r source=%s reason=no_search_request",
                    keyword,
                    _source_log_label(src),
                )
                return src.id, src.weight, []
            headers = src.headers or {}
            resp = await execute_request(search_request, source_headers=headers)
            if resp["status"] != 200 or not resp["body"]:
                logger.info(
                    "搜索源请求无结果 keyword=%r source=%s status=%s body_len=%d",
                    keyword,
                    _source_log_label(src),
                    resp.get("status"),
                    len(str(resp.get("body") or "")),
                )
                return src.id, src.weight, []
            is_json = response_is_json(resp)
            try:
                rules = src.ruleSearch.model_dump()
                extracted = RuleEngine.apply_rules(
                    resp["body"],
                    rules,
                    is_json=is_json,
                    base_url=search_request.url,
                )
                books = extracted.get("bookList", []) if isinstance(extracted, dict) else []
                if isinstance(books, dict):
                    books = [books]
                raw_count = _count_books(books)
                books = _filter_search_books(books, keyword)
                filtered_count = len(books)
                for book in books:
                    book["sourceId"] = src.id
                    book["sourceName"] = src.bookSourceName
                    _normalize_book_result_urls(book, src.bookSourceUrl)
                logger.info(
                    "搜索源结果 keyword=%r source=%s raw=%d filtered=%d",
                    keyword,
                    _source_log_label(src),
                    raw_count,
                    filtered_count,
                )
                return src.id, src.weight, books
            except Exception as e:  # noqa: BLE001
                logger.warning("搜索源提取失败 keyword=%r source=%s err=%s", keyword, _source_log_label(src), e)
                return src.id, src.weight, []

    tasks = [_search_one(src) for src in sources]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    _log_search_source_results(keyword, page, merge, sources, results)

    books = (
        Aggregator.aggregate_search_results(results)
        if merge == 1
        else _flatten_search_results(results)
    )
    logger.info("搜索完成 keyword=%r page=%s merge=%s total=%d", keyword, page, merge, len(books))

    # 写缓存
    await cache.set_search(keyword, page, books, source_scope=source_scope, merge=merge)
    return success(data=_proxify_search_results(books, get_public_origin(request)))


@router.get("/explore")
async def explore(
    request: Request,
    url: str = Query("", description="源站发现/分类页URL"),
    source_id: str | None = Query(None, alias="sourceId", description="限定子书源ID"),
    source_filter: str | None = Query(None, alias="source", description="限定子书源名称或ID"),
):
    """发现/分类：从子书源的 exploreUrl + ruleExplore 提取书籍列表。"""
    source = _find_source_by_url(url, source_id) if url else None
    if not source:
        candidates = _select_sources(source_id=source_id, source_filter=source_filter)
        source = next((src for src in candidates if _source_has_explore(src)), None)
    if not source:
        return error("NOT_FOUND", "未找到匹配的书源")
    if not _source_has_explore(source):
        return success(data={"books": [], "nextUrl": ""})

    target_url = url or _first_explore_url(source)
    if not target_url:
        return success(data={"books": [], "nextUrl": ""})

    resp = await http_client.get(target_url, headers=source.headers or {})
    if resp["status"] != 200:
        return error("FETCH_FAILED", f"源站请求失败: HTTP {resp['status']}")

    extracted = RuleEngine.apply_rules(
        resp["body"],
        source.ruleExplore.model_dump(),
        is_json=response_is_json(resp),
        base_url=target_url,
    )
    books = extracted.get("bookList", []) if isinstance(extracted, dict) else []
    if isinstance(books, dict):
        books = [books]
    for book in books:
        if not isinstance(book, dict):
            continue
        book["sourceId"] = source.id
        book["sourceName"] = source.bookSourceName
        _normalize_book_result_urls(book, target_url)

    next_url = ""
    if isinstance(extracted, dict) and extracted.get("nextUrl"):
        next_url = resolve_relative_url(target_url, extracted["nextUrl"])
        next_url = _proxy_api_url(get_public_origin(request), "/api/explore", next_url, source_id=source.id)

    return success(
        data={
            "books": _proxify_search_results(books, get_public_origin(request)),
            "nextUrl": next_url,
        }
    )


@router.get("/book")
async def get_book_info(
    request: Request,
    url: str = Query(..., description="源站书籍页URL"),
    source_id: str | None = Query(None, alias="sourceId", description="限定子书源ID"),
):
    """书籍详情：从对应源站获取详情信息。"""
    source_hint = source_id or _source_id_from_url(url)
    url_hash = hashlib.md5(f"{_BOOK_CACHE_VERSION}:{source_hint}:{url}".encode()).hexdigest()
    cached = await cache.get_book(url_hash)
    if cached is not None:
        if source_id and isinstance(cached, dict):
            cached = {**cached, "sourceId": source_id}
        return success(data=_proxify_book_info(cached, get_public_origin(request)))

    source = _find_source_by_url(url, source_id)
    if not source:
        return error("NOT_FOUND", "未找到匹配的书源")

    resp = await http_client.get(url, headers=source.headers or {})
    if resp["status"] != 200:
        return error("FETCH_FAILED", f"源站请求失败: HTTP {resp['status']}")

    is_json = response_is_json(resp)
    rules = source.ruleBookInfo.model_dump()
    info = RuleEngine.apply_rules(resp["body"], rules, is_json=is_json, base_url=url)

    # 解析 tocUrl 为绝对地址
    if isinstance(info, dict) and info.get("tocUrl"):
        info["tocUrl"] = resolve_relative_url(url, info["tocUrl"])
    elif isinstance(info, dict) and getattr(source.ruleToc, "chapterList", ""):
        info["tocUrl"] = url
    if isinstance(info, dict) and info.get("coverUrl"):
        info["coverUrl"] = resolve_relative_url(url, info["coverUrl"])
    if isinstance(info, dict):
        info["sourceId"] = source.id
        info["sourceName"] = source.bookSourceName

    await cache.set_book(url_hash, info)
    return success(data=_proxify_book_info(info, get_public_origin(request)))


@router.get("/toc")
async def get_toc(
    request: Request,
    url: str = Query(..., description="源站目录页URL"),
    source_id: str | None = Query(None, alias="sourceId", description="限定子书源ID"),
):
    """章节目录：从源站获取章节列表。"""
    source_hint = source_id or _source_id_from_url(url)
    url_hash = hashlib.md5(f"{_TOC_CACHE_VERSION}:{source_hint}:{url}".encode()).hexdigest()
    cached = await cache.get_toc(url_hash)
    if cached is not None:
        return success(data=_proxify_toc_chapters(cached, get_public_origin(request), source_id=source_id))

    source = _find_source_by_url(url, source_id)
    if not source:
        return error("NOT_FOUND", "未找到匹配的书源")

    chapters, failed_status = await _collect_toc_chapters(source, url)
    if failed_status is not None:
        return error("FETCH_FAILED", f"源站请求失败: HTTP {failed_status}")

    chapters = Aggregator.aggregate_toc_results(chapters)

    if chapters:
        await cache.set_toc(url_hash, chapters)
    return success(data=_proxify_toc_chapters(chapters, get_public_origin(request), source_id=source.id))


@router.get("/content")
async def get_content(
    url: str = Query(..., description="源站章节页URL"),
    source_id: str | None = Query(None, alias="sourceId", description="限定子书源ID"),
):
    """章节正文：从源站获取正文内容。"""
    source = _find_source_by_url(url, source_id)
    if not source:
        return error("NOT_FOUND", "未找到匹配的书源")

    content, failed_status = await _collect_content_pages(source, url)
    if failed_status is not None:
        logger.info(
            "正文获取失败 source=%s url=%s status=%s",
            _source_log_label(source),
            url,
            failed_status,
        )
        return error("FETCH_FAILED", f"源站请求失败: HTTP {failed_status}")
    logger.info(
        "正文获取完成 source=%s url=%s len=%d",
        _source_log_label(source),
        url,
        len(content),
    )
    return success(data={"content": content})


@router.get("/health")
async def health():
    """服务存活检查。"""
    return success(data={"status": "ok"})


async def _collect_toc_chapters(source, start_url: str) -> tuple[list[dict], int | None]:
    """Collect toc chapters, following ``ruleToc.nextTocUrl`` when present."""
    chapters: list[dict] = []
    current_url = start_url
    seen: set[str] = set()
    rules = source.ruleToc.model_dump()

    for _ in range(_MAX_TOC_PAGES):
        if not current_url or current_url in seen:
            break
        seen.add(current_url)

        resp = await http_client.get(current_url, headers=source.headers or {})
        if resp["status"] != 200:
            return chapters, resp["status"] if not chapters else None

        extracted = RuleEngine.apply_rules(
            resp["body"],
            rules,
            is_json=response_is_json(resp),
            base_url=current_url,
        )
        page_chapters = extracted.get("chapterList", []) if isinstance(extracted, dict) else []
        if isinstance(page_chapters, dict):
            page_chapters = [page_chapters]
        chapters.extend(_normalize_toc_chapters(page_chapters, current_url))

        next_url = str(extracted.get("nextTocUrl") or "").strip() if isinstance(extracted, dict) else ""
        if not next_url:
            break
        current_url = resolve_relative_url(current_url, next_url)

    return chapters, None


async def _collect_content_pages(source, start_url: str) -> tuple[str, int | None]:
    """Collect chapter content, following ``ruleContent.nextContentUrl`` when present."""
    parts: list[str] = []
    current_url = start_url
    seen: set[str] = set()
    rules = source.ruleContent.model_dump()
    follow_next_content = _should_follow_next_content_url(rules.get("nextContentUrl"))

    for _ in range(_MAX_CONTENT_PAGES):
        if not current_url or current_url in seen:
            break
        seen.add(current_url)

        fetch_url = _preferred_content_url(current_url)
        resp = await http_client.get(fetch_url, headers=source.headers or {})
        if resp["status"] != 200:
            return "\n".join(parts), resp["status"] if not parts else None

        extracted = RuleEngine.apply_rules(
            resp["body"],
            rules,
            is_json=response_is_json(resp),
            base_url=fetch_url,
        )
        content = _content_value_to_text(extracted.get("content", "") if isinstance(extracted, dict) else "")
        if not content:
            content = _content_fallback_text(resp["body"], fetch_url)
        elif _is_xsw_url(fetch_url):
            content = _clean_xsw_content_html(content)
        logger.info(
            "正文页提取 source=%s url=%s fetchUrl=%s status=%s len=%d",
            _source_log_label(source),
            current_url,
            fetch_url,
            resp.get("status"),
            len(content),
        )
        if content:
            parts.append(content)

        next_url = str(extracted.get("nextContentUrl") or "").strip() if isinstance(extracted, dict) else ""
        if not next_url or not follow_next_content:
            break
        current_url = resolve_relative_url(fetch_url, next_url)

    return "\n".join(parts), None


def _content_fallback_text(body: str, url: str) -> str:
    if not _is_xsw_url(url):
        return ""
    return _clean_xsw_content_html(
        RuleEngine.extract(body, "#nr1@html")
        or RuleEngine.extract(body, "@xsw-aes-content")
    )


def _preferred_content_url(url: str) -> str:
    return _xsw_www_to_mobile_chapter_url(url) or url


def _xsw_www_to_mobile_chapter_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.netloc.lower() != "www.xsw.tw":
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3 or parts[0] != "book" or not parts[1].isdigit() or not parts[2].endswith(".html"):
        return ""
    return f"{parsed.scheme or 'https'}://m.xsw.tw/{parts[1]}/{parts[2]}"


def _is_xsw_url(url: str) -> bool:
    host = urlparse(str(url or "")).netloc.lower()
    return host in {"www.xsw.tw", "m.xsw.tw"}


def _should_follow_next_content_url(rule) -> bool:
    text = str(rule or "").lower()
    chapter_markers = ("下一章", "下一回", "下一节", "next chapter")
    return bool(text.strip()) and not any(marker in text for marker in chapter_markers)


def _content_value_to_text(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _clean_xsw_content_html(value) -> str:
    text = _content_value_to_text(value)
    if not text:
        return ""
    replacements = (
        (r"<br\s*/?>", "\n"),
        (r"</p\s*>", "\n"),
        (r"<p[^>]*>", "\n"),
        (r"<[^>]+>", ""),
        (r"&nbsp;", " "),
        ("\xa0", " "),
        (r"(?<=[\u4e00-\u9fff0-9，。！？；：“”‘’、])[\xa0 ]+(?=[\u4e00-\u9fff0-9，。！？；：“”‘’、])", ""),
        (r"&amp;", "&"),
        (r"&lt;", "<"),
        (r"&gt;", ">"),
        (r"&#39;", "'"),
        (r"&quot;", '"'),
        (r"\r", ""),
        (r"[ \t]+\n", "\n"),
        (r"\n{3,}", "\n\n"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text.strip()


def _normalize_book_result_urls(book: dict, base_url: str) -> None:
    """Normalize common Legado detail URL aliases and media URLs in-place."""
    detail_url = str(book.get("noteUrl") or book.get("bookUrl") or "").strip()
    if detail_url:
        detail_url = resolve_relative_url(base_url, detail_url)
        book["noteUrl"] = detail_url
        book["bookUrl"] = detail_url

    toc_url = str(book.get("tocUrl") or "").strip()
    if toc_url:
        book["tocUrl"] = resolve_relative_url(base_url, toc_url)
    cover_url = str(book.get("coverUrl") or "").strip()
    if cover_url:
        book["coverUrl"] = resolve_relative_url(base_url, cover_url)


def _count_books(books) -> int:
    if isinstance(books, list):
        return len([book for book in books if isinstance(book, dict)])
    if isinstance(books, dict):
        return 1
    return 0


def _source_log_label(source) -> str:
    name = str(getattr(source, "bookSourceName", "") or "").strip()
    source_id = str(getattr(source, "id", "") or "").strip()
    if name and source_id:
        return f"{name}({source_id})"
    return name or source_id or "unknown"


def _source_summary(sources) -> str:
    labels = [_source_log_label(source) for source in sources or []]
    return "、".join(labels) if labels else "无"


def _log_search_source_results(keyword: str, page: int, merge: int, sources, results_by_source) -> None:
    source_by_id = {str(getattr(source, "id", "")): source for source in sources or []}
    counts: list[str] = []
    hits: list[str] = []
    total = 0

    for source_id, _weight, books in results_by_source or []:
        source = source_by_id.get(str(source_id))
        label = _source_log_label(source) if source else str(source_id or "unknown")
        count = _count_books(books)
        total += count
        counts.append(f"{label}={count}")
        if count > 0:
            hits.append(label)

    logger.info(
        "搜索源汇总 keyword=%r page=%s merge=%s hit_sources=%s total_by_source=%d counts=%s",
        keyword,
        page,
        merge,
        "、".join(hits) if hits else "无",
        total,
        "；".join(counts) if counts else "无",
    )


def _log_search_cache_hit(keyword: str, page: int, merge: int, books) -> None:
    counts: dict[str, int] = {}
    for book in books or []:
        if not isinstance(book, dict):
            continue
        labels = book.get("sourceNames")
        if isinstance(labels, list) and labels:
            source_names = [str(label).strip() for label in labels if str(label).strip()]
        else:
            source_names = [str(book.get("sourceName") or book.get("sourceId") or "unknown").strip()]
        for source_name in source_names:
            counts[source_name or "unknown"] = counts.get(source_name or "unknown", 0) + 1

    logger.info(
        "搜索命中缓存 keyword=%r page=%s merge=%s hit_sources=%s total=%d counts=%s",
        keyword,
        page,
        merge,
        "、".join(name for name, count in counts.items() if count > 0) or "无",
        _count_books(books),
        "；".join(f"{name}={count}" for name, count in counts.items()) or "无",
    )


def _source_has_explore(source) -> bool:
    rule_explore = getattr(source, "ruleExplore", None)
    return bool(getattr(source, "enabledExplore", False) and getattr(rule_explore, "bookList", ""))


def _source_search_enabled(source) -> bool:
    return bool(getattr(source, "enabledSearch", True))


def _filter_search_books(books, keyword: str) -> list[dict]:
    """Keep only search results whose title or author matches the keyword."""
    filtered: list[dict] = []
    for index, book in enumerate(books or []):
        if not isinstance(book, dict):
            continue
        if not str(book.get("name") or "").strip():
            continue
        score = _search_relevance_score(book, keyword)
        if score <= 0:
            continue
        item = dict(book)
        item["_searchScore"] = score
        item["_searchOrder"] = index
        filtered.append(item)
    return filtered


def _search_relevance_score(book: dict, keyword: str) -> float:
    """Score title/author relevance for strict global search filtering."""
    title_keyword = normalize_title(keyword)
    author_keyword = normalize_author(keyword)
    if not title_keyword and not author_keyword:
        return 1.0

    name = str(book.get("name") or "")
    author = str(book.get("author") or "")
    title_score = _field_relevance_score(
        normalize_title(name),
        title_keyword,
        exact_score=100,
        contains_score=80,
        similar_score=70,
        threshold=_TITLE_SIMILARITY_THRESHOLD,
    )
    author_score = _field_relevance_score(
        normalize_author(author),
        author_keyword,
        exact_score=90,
        contains_score=60,
        similar_score=50,
        threshold=_AUTHOR_SIMILARITY_THRESHOLD,
    )
    return max(title_score, author_score)


def _field_relevance_score(
    value: str,
    keyword: str,
    exact_score: int,
    contains_score: int,
    similar_score: int,
    threshold: float,
) -> float:
    if not value or not keyword:
        return 0.0
    if value == keyword:
        return float(exact_score)
    if keyword in value or value in keyword:
        shorter = min(len(value), len(keyword))
        longer = max(len(value), len(keyword))
        coverage = shorter / longer if longer else 0
        return contains_score + coverage

    ratio = similarity(value, keyword)
    if ratio >= threshold:
        return similar_score + ratio
    return 0.0


def _first_explore_url(source) -> str:
    for _label, url in _iter_explore_entries(getattr(source, "exploreUrl", None)):
        return url
    return ""


def _iter_explore_entries(explore_url) -> list[tuple[str, str]]:
    values: list[str] = []
    if isinstance(explore_url, list):
        values = [str(item) for item in explore_url]
    elif isinstance(explore_url, str):
        values = [item.strip() for item in explore_url.splitlines() if item.strip()]

    entries: list[tuple[str, str]] = []
    for item in values:
        label, separator, url = item.partition("::")
        if separator:
            entries.append((label.strip(), url.strip()))
        else:
            entries.append(("", item.strip()))
    return [(label, url) for label, url in entries if url]


def _split_keyword_source(keyword: str) -> tuple[str, str | None]:
    """Support quick search syntax: title@source."""
    text = str(keyword or "").strip()
    at_index = max(text.rfind("@"), text.rfind("＠"))
    if at_index > 0 and at_index < len(text) - 1:
        return text[:at_index].strip(), text[at_index + 1:].strip()
    return text, None


def _select_sources(source_id: str | None = None, source_filter: str | None = None):
    """Select enabled child sources by ID/name filter."""
    if source_id:
        source = source_manager.get_source(source_id)
        return [source] if source and source.enabled else []

    sources = source_manager.get_enabled_sources()
    filter_text = str(source_filter or "").strip()
    if not filter_text or filter_text.lower() in {"all", "全部"}:
        return sources

    tokens = [token.strip() for token in filter_text.replace("，", ",").split(",") if token.strip()]
    if not tokens:
        return sources

    selected = []
    seen: set[str] = set()
    for src in sources:
        if any(_source_matches_filter(src, token) for token in tokens):
            if src.id not in seen:
                selected.append(src)
                seen.add(src.id)
    return selected


def _source_matches_filter(src, token: str) -> bool:
    token_lower = token.lower()
    return (
        token == src.id
        or token == src.bookSourceName
        or token_lower == src.id.lower()
        or token_lower == src.bookSourceName.lower()
    )


def _source_cache_scope(sources) -> str:
    ids = sorted(str(src.id) for src in sources if src)
    scope = ",".join(ids) if ids else "none"
    return f"{_SEARCH_CACHE_VERSION}:{scope}"


def _flatten_search_results(results_by_source: list[tuple[str, int, list[dict]]]) -> list[dict]:
    """Return per-source candidates without deduplication."""
    flattened: list[dict] = []
    for _source_id, _weight, books in sorted(results_by_source, key=lambda item: item[1], reverse=True):
        for book in books or []:
            if not isinstance(book, dict):
                continue
            if not str(book.get("name") or "").strip():
                continue
            item = dict(book)
            item["_sourceWeight"] = _weight
            item.setdefault("sourceCount", 1)
            flattened.append(item)
    flattened.sort(
        key=lambda item: (
            -float(item.get("_searchScore") or 0),
            -int(item.get("_sourceWeight") or 0),
            int(item.get("_searchOrder") or 0),
        )
    )
    for item in flattened:
        _strip_search_internal_fields(item)
    return flattened


def _strip_search_internal_fields(item: dict) -> None:
    item.pop("_searchScore", None)
    item.pop("_searchOrder", None)
    item.pop("_sourceWeight", None)


def _find_source_by_url(url: str, source_id: str | None = None):
    """根据 URL 匹配对应的书源（URL 包含源站基础URL即视为匹配）。"""
    if source_id:
        source = source_manager.get_source(source_id)
        if source and source.enabled:
            return source

    source_id = _source_id_from_url(url)
    if source_id:
        source = source_manager.get_source(source_id)
        if source and source.enabled:
            return source

    sources = source_manager.get_enabled_sources()
    # 精确匹配优先
    for src in sources:
        if url.startswith(src.bookSourceUrl):
            return src
    # 域名匹配兜底
    target_host = urlparse(url).netloc
    for src in sources:
        source_host = urlparse(src.bookSourceUrl).netloc
        if source_host == target_host or _same_mobile_www_site(source_host, target_host):
            return src
    return None


def _same_mobile_www_site(source_host: str, target_host: str) -> bool:
    """Treat m.example.com and www.example.com as the same source site."""
    if not source_host or not target_host:
        return False

    def normalize(host: str) -> str:
        host = host.lower()
        for prefix in ("www.", "m."):
            if host.startswith(prefix):
                return host[len(prefix):]
        return host

    return normalize(source_host) == normalize(target_host)


def _source_id_from_url(url: str) -> str:
    """Read an internal sourceId hint from a proxied source URL."""
    from urllib.parse import parse_qs, urlparse

    values = parse_qs(urlparse(url).query).get("sourceId", [])
    return values[0] if values else ""


def _normalize_toc_chapters(chapters: list[dict], base_url: str) -> list[dict]:
    """Normalize child-source toc fields to the public API's name/url contract."""
    normalized: list[dict] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        name = str(chapter.get("name") or chapter.get("chapterName") or "").strip()
        chapter_url = str(chapter.get("url") or chapter.get("chapterUrl") or "").strip()
        if chapter_url:
            chapter_url = resolve_relative_url(base_url, chapter_url)
            chapter_url = _xsw_www_to_mobile_chapter_url(chapter_url) or chapter_url
        normalized.append({"name": name, "url": chapter_url})
    return normalized


def _proxify_search_results(books: list[dict], public_origin: str) -> list[dict]:
    """Return search results whose detail URLs point back to the aggregator API."""
    proxied: list[dict] = []
    for book in books or []:
        if not isinstance(book, dict):
            continue
        item = dict(book)
        _strip_search_internal_fields(item)
        _decorate_source_label(item)
        source_id = str(item.get("sourceId") or "").strip()
        detail_url = str(item.get("noteUrl") or item.get("bookUrl") or "").strip()
        if detail_url:
            proxied_detail = _proxy_api_url(public_origin, "/api/book", detail_url, source_id=source_id)
            item["noteUrl"] = proxied_detail
            item["bookUrl"] = proxied_detail

        toc_url = str(item.get("tocUrl") or "").strip()
        if toc_url:
            item["tocUrl"] = _proxy_api_url(public_origin, "/api/toc", toc_url, source_id=source_id)

        proxied.append(item)
    return proxied


def _decorate_source_label(item: dict) -> None:
    """Expose child-source names in fields the reading app already renders."""
    source_label = _source_label_for_book(item)
    if not source_label:
        return

    item["sourceName"] = source_label
    _prepend_source_to_kind(item, source_label)
    _prepend_source_to_last_chapter(item, source_label)
    _prepend_source_to_intro(item, source_label)


def _prepend_source_to_kind(item: dict, source_label: str) -> None:
    kind = str(item.get("kind") or "").strip()
    if not kind:
        item["kind"] = source_label
        return
    item.setdefault("originalKind", kind)
    if source_label not in kind:
        item["kind"] = f"{source_label} · {kind}"


def _prepend_source_to_last_chapter(item: dict, source_label: str) -> None:
    last_chapter = str(item.get("lastChapter") or "").strip()
    if not last_chapter:
        item["lastChapter"] = source_label
        return
    item.setdefault("originalLastChapter", last_chapter)
    if source_label not in last_chapter:
        item["lastChapter"] = f"{source_label} {last_chapter}"


def _prepend_source_to_intro(item: dict, source_label: str) -> None:
    intro = str(item.get("intro") or "").strip()
    source_line = f"数据来源：{source_label}"
    if not intro:
        item["intro"] = source_line
        return
    item.setdefault("originalIntro", intro)
    if source_line not in intro:
        item["intro"] = f"{source_line}\n\n{intro}"


def _source_label_for_book(item: dict) -> str:
    source_names = item.get("sourceNames")
    if isinstance(source_names, list):
        names = [str(name).strip() for name in source_names if str(name).strip()]
        if names:
            return "、".join(dict.fromkeys(names))

    source_name = str(item.get("sourceName") or "").strip()
    if source_name:
        return source_name

    source_id = str(item.get("sourceId") or "").strip()
    if source_id:
        source = source_manager.get_source(source_id)
        if source:
            return source.bookSourceName

    detail_url = str(item.get("noteUrl") or item.get("bookUrl") or "").strip()
    source_url = _unproxy_source_url(detail_url, "/api/book")
    source = _find_source_by_url(source_url) if source_url else None
    return source.bookSourceName if source else ""


def _unproxy_source_url(url: str, api_path: str) -> str:
    parsed = urlparse(url)
    if parsed.path != api_path:
        return url
    values = parse_qs(parsed.query).get("url", [])
    return values[0] if values else url


def _proxify_book_info(info: dict, public_origin: str) -> dict:
    """Return book info whose toc URL points back to the aggregator API."""
    if not isinstance(info, dict):
        return info
    item = dict(info)
    _decorate_source_label(item)
    source_id = str(item.get("sourceId") or "").strip()
    toc_url = str(item.get("tocUrl") or "").strip()
    if toc_url:
        item["tocUrl"] = _proxy_api_url(public_origin, "/api/toc", toc_url, source_id=source_id)
    return item


def _proxify_toc_chapters(
    chapters: list[dict],
    public_origin: str,
    source_id: str | None = None,
) -> list[dict]:
    """Return chapters whose content URLs point back to the aggregator API."""
    proxied: list[dict] = []
    for chapter in chapters or []:
        if not isinstance(chapter, dict):
            continue
        item = dict(chapter)
        item_source_id = str(item.get("sourceId") or source_id or "").strip()
        chapter_url = str(item.get("url") or item.get("chapterUrl") or "").strip()
        if chapter_url:
            proxied_content = _proxy_api_url(
                public_origin,
                "/api/content",
                chapter_url,
                source_id=item_source_id,
            )
            item["url"] = proxied_content
            item["chapterUrl"] = proxied_content
        proxied.append(item)
    return proxied


def _proxy_api_url(
    public_origin: str,
    api_path: str,
    source_url: str,
    source_id: str | None = None,
) -> str:
    """Build a public API URL while avoiding double-proxying cached values."""
    source_url = str(source_url or "").strip()
    if not source_url:
        return ""
    if _is_proxy_api_url(source_url, api_path):
        if source_id and "sourceId=" not in source_url:
            separator = "&" if urlparse(source_url).query else "?"
            return f"{source_url}{separator}{urlencode({'sourceId': source_id})}"
        return source_url
    params = {"url": source_url}
    if source_id:
        params["sourceId"] = source_id
    return f"{public_origin.rstrip('/')}{api_path}?{urlencode(params)}"


def _is_proxy_api_url(url: str, api_path: str) -> bool:
    parsed = urlparse(url)
    return parsed.path == api_path and bool(parse_qs(parsed.query).get("url"))
