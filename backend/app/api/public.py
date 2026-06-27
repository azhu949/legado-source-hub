"""对外开放 API：供阅读 APP 调用的聚合接口。"""

import asyncio
import hashlib
import logging
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import APIRouter, Query, Request

from app.core.aggregator import Aggregator
from app.core.cache import cache
from app.core.legado import build_search_request, execute_request, response_is_json
from app.core.http_client import http_client
from app.core.rule_engine import RuleEngine
from app.core.source_manager import source_manager
from app.models.responses import success, error
from app.utils.helpers import resolve_relative_url
from app.utils.public_url import get_public_origin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["public"])


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
    if not sources:
        return success(data=[])

    source_scope = _source_cache_scope(sources)
    cached = await cache.get_search(keyword, page, source_scope=source_scope, merge=merge)
    if cached is not None:
        return success(data=_proxify_search_results(cached, get_public_origin(request)))

    # 并发搜索
    semaphore = asyncio.Semaphore(15)

    async def _search_one(src):
        async with semaphore:
            request = await build_search_request(src, keyword, page)
            if not request:
                return src.id, src.weight, []
            headers = src.headers or {}
            resp = await execute_request(request, source_headers=headers)
            if resp["status"] != 200 or not resp["body"]:
                return src.id, src.weight, []
            is_json = response_is_json(resp)
            try:
                rules = src.ruleSearch.model_dump()
                extracted = RuleEngine.apply_rules(resp["body"], rules, is_json=is_json)
                books = extracted.get("bookList", []) if isinstance(extracted, dict) else []
                # 补充 noteUrl 为绝对地址
                for book in books:
                    book["sourceId"] = src.id
                    book["sourceName"] = src.bookSourceName
                    if book.get("noteUrl"):
                        book["noteUrl"] = resolve_relative_url(src.bookSourceUrl, book["noteUrl"])
                    if book.get("coverUrl"):
                        book["coverUrl"] = resolve_relative_url(src.bookSourceUrl, book["coverUrl"])
                return src.id, src.weight, books
            except Exception as e:  # noqa: BLE001
                logger.debug("书源 %s 搜索提取失败: %s", src.bookSourceName, e)
                return src.id, src.weight, []

    tasks = [_search_one(src) for src in sources]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    books = (
        Aggregator.aggregate_search_results(results)
        if merge == 1
        else _flatten_search_results(results)
    )

    # 写缓存
    await cache.set_search(keyword, page, books, source_scope=source_scope, merge=merge)
    return success(data=_proxify_search_results(books, get_public_origin(request)))


@router.get("/book")
async def get_book_info(
    request: Request,
    url: str = Query(..., description="源站书籍页URL"),
    source_id: str | None = Query(None, alias="sourceId", description="限定子书源ID"),
):
    """书籍详情：从对应源站获取详情信息。"""
    source_hint = source_id or _source_id_from_url(url)
    url_hash = hashlib.md5(f"{source_hint}:{url}".encode()).hexdigest()
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

    is_json = "json" in resp.get("headers", {}).get("Content-Type", "").lower()
    rules = source.ruleBookInfo.model_dump()
    info = RuleEngine.apply_rules(resp["body"], rules, is_json=is_json)

    # 解析 tocUrl 为绝对地址
    if isinstance(info, dict) and info.get("tocUrl"):
        info["tocUrl"] = resolve_relative_url(url, info["tocUrl"])
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
    url_hash = hashlib.md5(f"{source_hint}:{url}".encode()).hexdigest()
    cached = await cache.get_toc(url_hash)
    if cached is not None:
        return success(data=_proxify_toc_chapters(cached, get_public_origin(request), source_id=source_id))

    source = _find_source_by_url(url, source_id)
    if not source:
        return error("NOT_FOUND", "未找到匹配的书源")

    resp = await http_client.get(url, headers=source.headers or {})
    if resp["status"] != 200:
        return error("FETCH_FAILED", f"源站请求失败: HTTP {resp['status']}")

    is_json = "json" in resp.get("headers", {}).get("Content-Type", "").lower()
    rules = source.ruleToc.model_dump()
    extracted = RuleEngine.apply_rules(resp["body"], rules, is_json=is_json)
    chapters = extracted.get("chapterList", []) if isinstance(extracted, dict) else []

    chapters = _normalize_toc_chapters(chapters, url)
    chapters = Aggregator.aggregate_toc_results(chapters)

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

    resp = await http_client.get(url, headers=source.headers or {})
    if resp["status"] != 200:
        return error("FETCH_FAILED", f"源站请求失败: HTTP {resp['status']}")

    is_json = "json" in resp.get("headers", {}).get("Content-Type", "").lower()
    rules = source.ruleContent.model_dump()
    extracted = RuleEngine.apply_rules(resp["body"], rules, is_json=is_json)
    content = extracted.get("content", "") if isinstance(extracted, dict) else ""
    return success(data={"content": content})


@router.get("/health")
async def health():
    """服务存活检查。"""
    return success(data={"status": "ok"})


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
    return ",".join(ids) if ids else "none"


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
            item.setdefault("sourceCount", 1)
            flattened.append(item)
    return flattened


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
        normalized.append({"name": name, "url": chapter_url})
    return normalized


def _proxify_search_results(books: list[dict], public_origin: str) -> list[dict]:
    """Return search results whose detail URLs point back to the aggregator API."""
    proxied: list[dict] = []
    for book in books or []:
        if not isinstance(book, dict):
            continue
        item = dict(book)
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
