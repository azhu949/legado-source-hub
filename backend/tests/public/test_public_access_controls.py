"""Public access-key tests without real source domains."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.public as public_api
import app.core.public_access as access_api
import app.main as main_api
from app.api.public import _proxify_book_info, _proxify_search_results
from app.core.auth import create_access_token
from app.main import app


@pytest.fixture(autouse=True)
def reset_public_access_overrides():
    app.dependency_overrides.pop(public_api.require_public_access, None)
    app.dependency_overrides.pop(main_api.public_access_for_source_export, None)
    yield
    app.dependency_overrides.pop(public_api.require_public_access, None)
    app.dependency_overrides.pop(main_api.public_access_for_source_export, None)


def _install_fake_access_user(monkeypatch, access_key="secret-token"):
    monkeypatch.setattr(
        access_api,
        "get_enabled_access_user_by_key",
        lambda value: {"id": "user-a", "access_key": value} if value == access_key else None,
    )
    monkeypatch.setattr(access_api, "record_access_user_usage", lambda value: None)


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


def test_generated_aggregate_source_requires_user_access_key(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "http://public.example:8080")
    monkeypatch.setattr(main_api.source_manager, "get_enabled_sources", lambda: [])
    _install_fake_access_user(monkeypatch)
    client = TestClient(app)

    denied = client.get("/api/aggregate_source.json")
    by_key = client.get("/api/aggregate_source.json?accessKey=secret-token")
    by_admin = client.get(
        "/api/aggregate_source.json",
        headers={"Authorization": f"Bearer {create_access_token('admin')}"},
    )

    assert denied.status_code == 401
    assert by_key.status_code == 200
    assert by_admin.status_code == 200
    assert by_key.headers["X-Aggregate-Source-Url"] == (
        "http://public.example:8080/api/aggregate_source.json?accessKey=secret-token"
    )
    assert "accessKey=secret-token" in by_key.json()[0]["searchUrl"]


def test_public_search_requires_user_access_key(monkeypatch):
    _install_fake_access_user(monkeypatch)
    _install_fake_public_search(monkeypatch)
    client = TestClient(app)

    denied = client.get("/api/search?keyword=同书&page=1")
    allowed = client.get("/api/search?keyword=同书&page=1&accessKey=secret-token")

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["data"][0]["bookUrl"].endswith("&sourceId=src-b&accessKey=secret-token")


def test_public_search_stays_closed_without_enabled_users(monkeypatch):
    monkeypatch.setattr(access_api, "get_enabled_access_user_by_key", lambda value: None)
    monkeypatch.setattr(access_api, "record_access_user_usage", lambda value: None)
    _install_fake_public_search(monkeypatch)
    client = TestClient(app)

    response = client.get("/api/search?keyword=同书&page=1")

    assert response.status_code == 401


def test_public_proxy_urls_carry_access_key():
    origin = "http://public.example:8080"

    search_results = _proxify_search_results(
        [{"name": "测试书", "sourceId": "src-a", "noteUrl": "https://source.example/book/1"}],
        origin,
        access_key="secret-token",
    )
    assert search_results[0]["noteUrl"] == (
        "http://public.example:8080/api/book?"
        "url=https%3A%2F%2Fsource.example%2Fbook%2F1&sourceId=src-a&accessKey=secret-token"
    )

    book_info = _proxify_book_info(
        {"sourceId": "src-a", "tocUrl": "https://source.example/book/1/"},
        origin,
        access_key="secret-token",
    )
    assert book_info["tocUrl"].endswith("&sourceId=src-a&accessKey=secret-token")
