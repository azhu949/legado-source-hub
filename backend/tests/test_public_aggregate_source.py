"""Public aggregate source compatibility tests."""

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.api.public as public_api
from app.api.public import (
    _proxy_api_url,
    _proxify_book_info,
    _proxify_search_results,
    _proxify_toc_chapters,
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
            headers={},
            ruleSearch=_RuleSet(),
        ),
        SimpleNamespace(
            id="src-b",
            bookSourceName="源B",
            bookSourceUrl="https://b.example",
            weight=200,
            enabled=True,
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
                }
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
                }
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
