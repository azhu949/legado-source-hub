"""Health checker behavior tests."""

import asyncio
from types import SimpleNamespace

from app.core import health_checker as health_module
from app.core.health_checker import HealthChecker
from app.models.source import BookSource


def test_health_check_tries_multiple_keywords(monkeypatch):
    source = BookSource(
        bookSourceName="测试源",
        bookSourceUrl="https://source.example",
        searchUrl="/search?q={{key}}",
        ruleSearch={
            "bookList": ".item",
            "name": "a@text",
            "author": ".author@text",
            "noteUrl": "a@href",
        },
    )
    requested_keywords: list[str] = []

    async def fake_build_search_request(_source, keyword, _page):
        requested_keywords.append(keyword)
        return SimpleNamespace(url=f"https://source.example/search?q={keyword}")

    async def fake_execute_request(request, source_headers=None):  # noqa: ARG001
        body = (
            "<html><body></body></html>"
            if "无结果关键词" in request.url
            else "<html><body><div class='item'><a href='/book/1'>凡人修仙传</a>"
            "<span class='author'>忘语</span></div></body></html>"
        )
        return {
            "status": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": body,
            "elapsed_ms": 12,
        }

    monkeypatch.setattr(health_module, "build_search_request", fake_build_search_request)
    monkeypatch.setattr(health_module, "execute_request", fake_execute_request)
    monkeypatch.setattr(health_module, "TEST_KEYWORDS", ("无结果关键词", "凡人修仙传"))

    result = asyncio.run(HealthChecker().check_source(source))

    assert result["status"] == "healthy"
    assert "凡人修仙传" in result["message"]
    assert requested_keywords[:2] == ["无结果关键词", "凡人修仙传"]
