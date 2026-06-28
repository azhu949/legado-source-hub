"""Public aggregate source compatibility tests."""

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_api
import app.api.public as public_api
from app.api.public import (
    _filter_search_books,
    _proxy_api_url,
    _proxify_book_info,
    _proxify_search_results,
    _proxify_toc_chapters,
    _search_relevance_score,
)
from app.core.rule_engine import RuleEngine
from app.main import app


def test_generated_aggregate_source_uses_public_origin_and_item_rules(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "http://public.example:8080")
    client = TestClient(app)

    response = client.get("/api/aggregate_source.json")

    assert response.status_code == 200
    sources = response.json()
    assert isinstance(sources, list)
    assert len(sources) == 1
    source = sources[0]
    assert source["bookSourceName"] == "📚 聚合书源·Pro"
    assert source["bookSourceUrl"] == "http://public.example:8080"
    assert source["bookSourceComment"]
    assert source["bookUrlPattern"]
    assert source["searchUrl"].startswith("<js>")
    assert "merge=${merge}" in source["searchUrl"]
    assert "aggSetSearchSource" in source["jsLib"]
    assert "搜索来源" in source["loginUi"]
    assert source["ruleSearch"]["bookList"] == "$.data[*]"
    assert source["ruleSearch"]["name"] == "$.name"
    assert source["ruleSearch"]["noteUrl"] == "$.noteUrl"
    assert source["ruleBookInfo"]["kind"] == "$.data.kind"
    assert source["ruleBookInfo"]["lastChapter"] == "$.data.lastChapter"
    assert source["ruleToc"]["chapterName"] == "$.name"
    assert source["ruleToc"]["chapterUrl"] == "$.url"


def test_generated_aggregate_source_exposes_child_explore_urls(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "http://public.example:8080")
    monkeypatch.setattr(
        main_api.source_manager,
        "get_enabled_sources",
        lambda: [
            SimpleNamespace(
                id="src-explore",
                bookSourceName="山雨阅读",
                enabledExplore=True,
                exploreUrl=["玄幻::https://www.shanyuread.com/mufen/cat/xuanhuan/p1_info.html"],
                ruleExplore=SimpleNamespace(bookList="#list .row"),
            )
        ],
    )
    client = TestClient(app)

    source = client.get("/api/aggregate_source.json").json()[0]

    assert source["enabledExplore"] is True
    assert source["ruleExplore"]["bookList"] == "$.data.books[*]"
    assert source["ruleExplore"]["nextUrl"] == "$.data.nextUrl"
    assert source["exploreUrl"] == [
        "山雨阅读/玄幻::"
        "http://public.example:8080/api/explore?"
        "url=https%3A%2F%2Fwww.shanyuread.com%2Fmufen%2Fcat%2Fxuanhuan%2Fp1_info.html"
        "&sourceId=src-explore"
    ]


def test_generated_aggregate_search_rules_extract_proxy_urls(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "http://public.example:8080")
    client = TestClient(app)
    source = client.get("/api/aggregate_source.json").json()[0]
    payload = {
        "success": True,
        "data": [
            {
                "name": "测试书",
                "author": "作者",
                "noteUrl": "http://public.example:8080/api/book?url=https%3A%2F%2Fsource.example%2Fbook%2F1",
                "bookUrl": "http://public.example:8080/api/book?url=https%3A%2F%2Fsource.example%2Fbook%2F1",
            }
        ],
    }

    result = RuleEngine.apply_rules(json.dumps(payload, ensure_ascii=False), source["ruleSearch"], is_json=True)

    assert result["bookList"][0]["name"] == "测试书"
    assert result["bookList"][0]["author"] == "作者"
    assert result["bookList"][0]["noteUrl"].startswith("http://public.example:8080/api/book?url=")


def test_public_search_results_render_child_source_in_kind():
    origin = "http://public.example:8080"

    search_results = _proxify_search_results(
        [
            {
                "name": "测试书",
                "kind": "玄幻",
                "sourceName": "台灣小說網",
                "noteUrl": "https://source.example/book/1",
            }
        ],
        origin,
    )

    assert search_results[0]["sourceName"] == "台灣小說網"
    assert search_results[0]["originalKind"] == "玄幻"
    assert search_results[0]["kind"] == "台灣小說網 · 玄幻"
    assert search_results[0]["intro"].startswith("数据来源：台灣小說網")


def test_public_search_results_render_multiple_child_sources_in_kind():
    origin = "http://public.example:8080"

    search_results = _proxify_search_results(
        [
            {
                "name": "测试书",
                "kind": "",
                "sourceNames": ["101看书", "免费小说"],
                "noteUrl": "https://source.example/book/1",
            }
        ],
        origin,
    )

    assert search_results[0]["sourceName"] == "101看书、免费小说"
    assert search_results[0]["kind"] == "101看书、免费小说"


def test_public_proxy_urls_keep_selected_source_id():
    origin = "http://public.example:8080"

    search_results = _proxify_search_results(
        [{"name": "测试书", "sourceId": "src-a", "noteUrl": "https://source.example/book/1"}],
        origin,
    )
    assert search_results[0]["noteUrl"] == (
        "http://public.example:8080/api/book?"
        "url=https%3A%2F%2Fsource.example%2Fbook%2F1&sourceId=src-a"
    )

    book_info = _proxify_book_info({"sourceId": "src-a", "tocUrl": "https://source.example/book/1/"}, origin)
    assert book_info["tocUrl"] == (
        "http://public.example:8080/api/toc?"
        "url=https%3A%2F%2Fsource.example%2Fbook%2F1%2F&sourceId=src-a"
    )

    chapters = _proxify_toc_chapters(
        [{"name": "第一章", "url": "https://source.example/book/1/1.html"}],
        origin,
        source_id="src-a",
    )
    assert chapters[0]["url"] == (
        "http://public.example:8080/api/content?"
        "url=https%3A%2F%2Fsource.example%2Fbook%2F1%2F1.html&sourceId=src-a"
    )


def test_public_proxy_url_helpers_keep_cache_host_neutral():
    origin = "http://public.example:8080"

    search_results = _proxify_search_results(
        [{"name": "测试书", "noteUrl": "https://source.example/book/1"}],
        origin,
    )
    assert search_results[0]["noteUrl"] == (
        "http://public.example:8080/api/book?url=https%3A%2F%2Fsource.example%2Fbook%2F1"
    )
    assert search_results[0]["bookUrl"] == search_results[0]["noteUrl"]

    book_info = _proxify_book_info({"tocUrl": "https://source.example/book/1/"}, origin)
    assert book_info["tocUrl"] == (
        "http://public.example:8080/api/toc?url=https%3A%2F%2Fsource.example%2Fbook%2F1%2F"
    )

    chapters = _proxify_toc_chapters([{"name": "第一章", "url": "https://source.example/book/1/1.html"}], origin)
    assert chapters[0]["url"] == (
        "http://public.example:8080/api/content?url=https%3A%2F%2Fsource.example%2Fbook%2F1%2F1.html"
    )
    assert chapters[0]["chapterUrl"] == chapters[0]["url"]

    already_proxy = "http://public.example:8080/api/book?url=https%3A%2F%2Fsource.example%2Fbook%2F1"
    assert _proxy_api_url(origin, "/api/book", already_proxy) == already_proxy


def test_search_relevance_filters_by_title_and_author_only():
    books = [
        {"name": "斗破苍穹", "author": "天蚕土豆"},
        {"name": "遮天", "author": "辰东"},
        {"name": "凡人修仙传", "author": "忘语", "intro": "辰东也推荐过"},
        {"name": "完美世界", "author": "辰东"},
        {"name": "", "author": "辰东"},
    ]

    title_results = _filter_search_books(books, "斗破")
    author_results = _filter_search_books(books, "辰东")
    empty_keyword_results = _filter_search_books(books, "")

    assert [item["name"] for item in title_results] == ["斗破苍穹"]
    assert [item["name"] for item in author_results] == ["遮天", "完美世界"]
    assert [item["name"] for item in empty_keyword_results] == ["斗破苍穹", "遮天", "凡人修仙传", "完美世界"]
    assert _search_relevance_score({"name": "凡人修仙传", "author": "忘语"}, "斗破苍穹") == 0
    assert _search_relevance_score({"name": "辰东", "author": "别人"}, "辰东") > _search_relevance_score(
        {"name": "遮天", "author": "辰东"},
        "辰东",
    )


def test_search_relevance_matches_traditional_text_with_simplified_keyword():
    books = [
        {"name": "鬥破蒼穹", "author": "天蠶土豆"},
        {"name": "凡人修仙傳", "author": "忘語"},
        {"name": "遮天", "author": "辰東"},
        {"name": "无关书", "author": "路人", "intro": "辰東推荐"},
    ]

    assert [item["name"] for item in _filter_search_books(books, "斗破")] == ["鬥破蒼穹"]
    assert [item["name"] for item in _filter_search_books(books, "凡人修仙传")] == ["凡人修仙傳"]
    assert [item["name"] for item in _filter_search_books(books, "辰东")] == ["遮天"]
    assert _search_relevance_score({"name": "无关书", "author": "路人", "intro": "辰東推荐"}, "辰东") == 0


def _install_fake_source(monkeypatch, source):
    monkeypatch.setattr(public_api.source_manager, "get_source", lambda source_id: source if source_id == source.id else None)
    monkeypatch.setattr(public_api.source_manager, "get_enabled_sources", lambda: [source])


def _install_empty_public_cache(monkeypatch):
    async def fake_get(*args, **kwargs):
        return None

    async def fake_set(*args, **kwargs):
        return None

    monkeypatch.setattr(public_api.cache, "get_book", fake_get)
    monkeypatch.setattr(public_api.cache, "set_book", fake_set)
    monkeypatch.setattr(public_api.cache, "get_toc", fake_get)
    monkeypatch.setattr(public_api.cache, "set_toc", fake_set)


def test_public_book_falls_back_to_detail_url_as_toc_url(monkeypatch):
    class BookInfoRule:
        def model_dump(self):
            return {"name": "#info h1", "author": "#info .author", "tocUrl": ""}

    source = SimpleNamespace(
        id="src-detail-toc",
        bookSourceName="同页目录源",
        bookSourceUrl="https://source.example",
        enabled=True,
        headers={},
        ruleBookInfo=BookInfoRule(),
        ruleToc=SimpleNamespace(chapterList="#chapterlist dd a"),
    )
    _install_fake_source(monkeypatch, source)
    _install_empty_public_cache(monkeypatch)

    async def fake_get(url, headers=None):
        return {
            "status": 200,
            "headers": {"Content-Type": "text/html"},
            "body": '<div id="info"><h1>测试书</h1><span class="author">作者</span></div><dl id="chapterlist"></dl>',
        }

    monkeypatch.setattr(public_api.http_client, "get", fake_get)
    client = TestClient(app)

    response = client.get("/api/book?url=https%3A%2F%2Fsource.example%2Fbook%2F1&sourceId=src-detail-toc")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "测试书"
    assert data["tocUrl"] == (
        "http://testserver/api/toc?"
        "url=https%3A%2F%2Fsource.example%2Fbook%2F1&sourceId=src-detail-toc"
    )


def test_public_toc_follows_next_toc_url_and_current_item_attrs(monkeypatch):
    class TocRule:
        chapterList = "#chapterlist dd a"

        def model_dump(self):
            return {
                "chapterList": "#chapterlist dd a",
                "chapterName": "text",
                "chapterUrl": "href",
                "nextTocUrl": ".listpage .right a@href",
            }

    source = SimpleNamespace(
        id="src-paged-toc",
        bookSourceName="分页目录源",
        bookSourceUrl="https://source.example",
        enabled=True,
        headers={},
        ruleToc=TocRule(),
    )
    _install_fake_source(monkeypatch, source)
    _install_empty_public_cache(monkeypatch)
    bodies = {
        "https://source.example/book/1": (
            '<dl id="chapterlist"><dd><a href="/book/1/c1.html">第一章</a></dd></dl>'
            '<div class="listpage"><span class="right"><a href="/book/1/p2.html">下一页</a></span></div>'
        ),
        "https://source.example/book/1/p2.html": (
            '<dl id="chapterlist"><dd><a href="/book/1/c2.html">第二章</a></dd></dl>'
        ),
    }

    async def fake_get(url, headers=None):
        return {"status": 200, "headers": {"Content-Type": "text/html"}, "body": bodies[url]}

    monkeypatch.setattr(public_api.http_client, "get", fake_get)
    client = TestClient(app)

    response = client.get("/api/toc?url=https%3A%2F%2Fsource.example%2Fbook%2F1&sourceId=src-paged-toc")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["name"] for item in data] == ["第一章", "第二章"]
    assert data[0]["url"] == (
        "http://testserver/api/content?"
        "url=https%3A%2F%2Fsource.example%2Fbook%2F1%2Fc1.html&sourceId=src-paged-toc"
    )


def test_public_content_follows_next_content_url_and_filters(monkeypatch):
    class ContentRule:
        def model_dump(self):
            return {
                "content": "#chapter@html",
                "contentFilter": ["<script.*?</script>"],
                "nextContentUrl": "a.next@href",
            }

    source = SimpleNamespace(
        id="src-paged-content",
        bookSourceName="分页正文源",
        bookSourceUrl="https://source.example",
        enabled=True,
        headers={},
        ruleContent=ContentRule(),
    )
    _install_fake_source(monkeypatch, source)
    bodies = {
        "https://source.example/book/1/c1.html": (
            '<div id="chapter">第一段<script>bad()</script></div><a class="next" href="/book/1/c1_2.html">下一页</a>'
        ),
        "https://source.example/book/1/c1_2.html": '<div id="chapter">第二段</div>',
    }

    async def fake_get(url, headers=None):
        return {"status": 200, "headers": {"Content-Type": "text/html"}, "body": bodies[url]}

    monkeypatch.setattr(public_api.http_client, "get", fake_get)
    client = TestClient(app)

    response = client.get(
        "/api/content?url=https%3A%2F%2Fsource.example%2Fbook%2F1%2Fc1.html&sourceId=src-paged-content"
    )

    assert response.status_code == 200
    assert response.json()["data"]["content"] == "第一段\n第二段"


def test_public_content_does_not_concatenate_next_chapter(monkeypatch):
    class ContentRule:
        def model_dump(self):
            return {
                "content": "#chapter@html",
                "nextContentUrl": "a:contains('下一章')@href",
            }

    source = SimpleNamespace(
        id="src-next-chapter",
        bookSourceName="下一章源",
        bookSourceUrl="https://source.example",
        enabled=True,
        headers={},
        ruleContent=ContentRule(),
    )
    _install_fake_source(monkeypatch, source)
    calls = []

    async def fake_get(url, headers=None):
        calls.append(url)
        return {
            "status": 200,
            "headers": {"Content-Type": "text/html"},
            "body": '<div id="chapter">本章正文</div><a href="/book/1/c2.html">下一章</a>',
        }

    monkeypatch.setattr(public_api.http_client, "get", fake_get)
    client = TestClient(app)

    response = client.get(
        "/api/content?url=https%3A%2F%2Fsource.example%2Fbook%2F1%2Fc1.html&sourceId=src-next-chapter"
    )

    assert response.status_code == 200
    assert response.json()["data"]["content"] == "本章正文"
    assert calls == ["https://source.example/book/1/c1.html"]


def test_public_explore_extracts_books_and_next_url(monkeypatch):
    class ExploreRule:
        bookList = "#list .row"

        def model_dump(self):
            return {
                "bookList": "#list .row",
                "name": ".name@text",
                "author": ".author@text",
                "bookUrl": ".name@href",
                "nextUrl": ".listpage .right a@href",
            }

    source = SimpleNamespace(
        id="src-explore-api",
        bookSourceName="分类源",
        bookSourceUrl="https://source.example",
        enabled=True,
        enabledExplore=True,
        exploreUrl=["玄幻::https://source.example/cat/p1.html"],
        headers={},
        ruleExplore=ExploreRule(),
    )
    _install_fake_source(monkeypatch, source)

    async def fake_get(url, headers=None):
        assert url == "https://source.example/cat/p1.html"
        return {
            "status": 200,
            "headers": {"Content-Type": "text/html"},
            "body": (
                '<div id="list"><div class="row"><a class="name" href="/book/1">测试书</a>'
                '<span class="author">作者</span></div></div>'
                '<div class="listpage"><span class="right"><a href="/cat/p2.html">下一页</a></span></div>'
            ),
        }

    monkeypatch.setattr(public_api.http_client, "get", fake_get)
    client = TestClient(app)

    response = client.get(
        "/api/explore?url=https%3A%2F%2Fsource.example%2Fcat%2Fp1.html&sourceId=src-explore-api"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["books"][0]["name"] == "测试书"
    assert data["books"][0]["bookUrl"] == (
        "http://testserver/api/book?url=https%3A%2F%2Fsource.example%2Fbook%2F1&sourceId=src-explore-api"
    )
    assert data["nextUrl"] == (
        "http://testserver/api/explore?"
        "url=https%3A%2F%2Fsource.example%2Fcat%2Fp2.html&sourceId=src-explore-api"
    )


class _RuleSet:
    def model_dump(self):
        return {
            "bookList": "$.books[*]",
            "name": "$.name",
            "author": "$.author",
            "kind": "$.kind",
            "lastChapter": "$.lastChapter",
            "intro": "$.intro",
            "coverUrl": "$.coverUrl",
            "noteUrl": "$.noteUrl",
        }


def _fake_sources():
    return [
        SimpleNamespace(
            id="src-a",
            bookSourceName="源A",
            bookSourceUrl="https://a.example",
            weight=100,
            enabled=True,
            enabledSearch=True,
            headers={},
            ruleSearch=_RuleSet(),
        ),
        SimpleNamespace(
            id="src-b",
            bookSourceName="源B",
            bookSourceUrl="https://b.example",
            weight=200,
            enabled=True,
            enabledSearch=True,
            headers={},
            ruleSearch=_RuleSet(),
        ),
    ]


def _install_fake_public_search(monkeypatch):
    sources = _fake_sources()
    by_id = {source.id: source for source in sources}
    payloads = {
        "src-a": {
            "books": [
                {
                    "name": "同书",
                    "author": "作者",
                    "kind": "类型A",
                    "lastChapter": "A最新",
                    "intro": "A简介",
                    "noteUrl": "/book/1",
                },
                {
                    "name": "遮天",
                    "author": "辰东",
                    "intro": "作者匹配",
                    "noteUrl": "/book/zt",
                },
                {
                    "name": "辰东",
                    "author": "传记作者",
                    "intro": "书名精确匹配",
                    "noteUrl": "/book/exact-title",
                },
                {
                    "name": "凡人修仙传",
                    "author": "忘语",
                    "intro": "简介提到同书，但书名作者都不匹配",
                    "noteUrl": "/book/noise-a",
                },
            ]
        },
        "src-b": {
            "books": [
                {
                    "name": "同书",
                    "author": "作者",
                    "kind": "类型B",
                    "lastChapter": "B最新",
                    "intro": "B简介",
                    "noteUrl": "/book/1",
                },
                {
                    "name": "完美世界",
                    "author": "辰东",
                    "intro": "作者匹配",
                    "noteUrl": "/book/wmsj",
                },
                {
                    "name": "鬥破蒼穹",
                    "author": "天蠶土豆",
                    "intro": "繁体书名和作者",
                    "noteUrl": "/book/dpcq",
                },
                {
                    "name": "无关书",
                    "author": "路人",
                    "intro": "简介提到辰东，但书名作者都不匹配",
                    "noteUrl": "/book/noise-b",
                },
            ]
        },
    }

    monkeypatch.setattr(public_api.source_manager, "get_enabled_sources", lambda: sources)
    monkeypatch.setattr(public_api.source_manager, "get_source", lambda source_id: by_id.get(source_id))

    async def fake_build_search_request(src, keyword, page):
        return SimpleNamespace(url=src.id)

    async def fake_execute_request(request, source_headers=None):
        return {
            "status": 200,
            "body": json.dumps(payloads[request.url], ensure_ascii=False),
            "headers": {"Content-Type": "application/json"},
        }

    async def fake_get_search(*args, **kwargs):
        return None

    async def fake_set_search(*args, **kwargs):
        return None

    monkeypatch.setattr(public_api, "build_search_request", fake_build_search_request)
    monkeypatch.setattr(public_api, "execute_request", fake_execute_request)
    monkeypatch.setattr(public_api.cache, "get_search", fake_get_search)
    monkeypatch.setattr(public_api.cache, "set_search", fake_set_search)
    return sources


def test_public_search_defaults_to_per_source_candidates(monkeypatch):
    _install_fake_public_search(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/search?keyword=同书&page=1")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2
    assert [item["sourceName"] for item in data] == ["源B", "源A"]
    assert data[0]["sourceCount"] == 1
    assert data[0]["kind"] == "源B · 类型B"
    assert data[0]["lastChapter"] == "源B B最新"
    assert data[0]["intro"].startswith("数据来源：源B")


def test_public_search_merge_one_deduplicates(monkeypatch):
    _install_fake_public_search(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/search?keyword=同书&page=1&merge=1")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["sourceCount"] == 2
    assert data[0]["sourceName"] == "源B、源A"


def test_public_search_filters_by_source_name_and_id(monkeypatch):
    _install_fake_public_search(monkeypatch)
    client = TestClient(app)

    by_name = client.get("/api/search?keyword=同书&page=1&source=源A").json()["data"]
    by_id = client.get("/api/search?keyword=同书&page=1&sourceId=src-b").json()["data"]
    by_quick_keyword = client.get("/api/search?keyword=同书@源A&page=1").json()["data"]

    assert [item["sourceName"] for item in by_name] == ["源A"]
    assert [item["sourceName"] for item in by_id] == ["源B"]
    assert [item["sourceName"] for item in by_quick_keyword] == ["源A"]


def test_public_search_filters_irrelevant_books_and_sorts_by_relevance(monkeypatch):
    _install_fake_public_search(monkeypatch)
    client = TestClient(app)

    title_results = client.get("/api/search?keyword=同书&page=1").json()["data"]
    author_results = client.get("/api/search?keyword=辰东&page=1").json()["data"]

    assert [item["name"] for item in title_results] == ["同书", "同书"]
    assert [item["name"] for item in author_results] == ["辰东", "完美世界", "遮天"]
    assert all("无关" not in item["name"] for item in author_results)
    assert all("_searchScore" not in item and "_searchOrder" not in item for item in author_results)


def test_public_search_matches_traditional_results_with_simplified_keyword(monkeypatch):
    _install_fake_public_search(monkeypatch)
    client = TestClient(app)

    title_results = client.get("/api/search?keyword=斗破&page=1").json()["data"]
    author_results = client.get("/api/search?keyword=天蚕土豆&page=1").json()["data"]

    assert [item["name"] for item in title_results] == ["鬥破蒼穹"]
    assert [item["name"] for item in author_results] == ["鬥破蒼穹"]


def test_public_search_merge_filters_before_deduplication(monkeypatch):
    _install_fake_public_search(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/search?keyword=辰东&page=1&merge=1")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["name"] for item in data] == ["辰东", "完美世界", "遮天"]
    assert all("无关" not in item["name"] and item["name"] != "凡人修仙传" for item in data)


def test_public_search_skips_enabled_search_false_sources(monkeypatch):
    sources = _install_fake_public_search(monkeypatch)
    sources[0].enabledSearch = False
    client = TestClient(app)

    by_disabled_source = client.get("/api/search?keyword=同书&page=1&source=源A").json()["data"]
    all_sources = client.get("/api/search?keyword=同书&page=1").json()["data"]

    assert by_disabled_source == []
    assert [item["sourceName"] for item in all_sources] == ["源B"]
