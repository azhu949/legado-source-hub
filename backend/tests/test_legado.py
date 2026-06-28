"""Legado compatibility helper tests."""

import asyncio
import json
import shutil
from types import SimpleNamespace

import pytest

from app.core.legado import build_template_url, normalize_source_dict, parse_request_spec
from app.core.rule_engine import RuleEngine
from app.core.source_manager import SourceManager
from app.models.source import BookSource


def test_normalize_header_and_book_url_alias():
    raw = {
        "bookSourceName": "岁月小说",
        "bookSourceUrl": "https://m.zzhhwy.com",
        "header": '{"User-Agent":"Mobile UA"}',
        "ruleSearch": {
            "bookList": "$.data.search[*]",
            "bookUrl": "$.book_list_url",
        },
    }

    source = BookSource(**raw)
    assert source.headers == {"User-Agent": "Mobile UA"}
    assert source.ruleSearch.noteUrl == "$.book_list_url"


def test_normalize_source_dict_accepts_headers_aliases():
    normalized = normalize_source_dict(
        {
            "headers": '{"Referer":"https://example.com"}',
            "ruleSearch": {"bookUrl": "$.url"},
            "ruleExplore": {"bookUrl": ".name@href"},
        }
    )
    assert normalized["headers"] == {"Referer": "https://example.com"}
    assert normalized["ruleSearch"]["noteUrl"] == "$.url"
    assert normalized["ruleExplore"]["noteUrl"] == ".name@href"


def test_book_source_accepts_empty_rule_array_as_blank_rule_object():
    source = BookSource(
        bookSourceName="番茄小说源",
        bookSourceUrl="https://novel.cooks.tw",
        ruleExplore=[],
    )

    assert source.ruleExplore.bookList == ""


def test_book_source_preserves_common_legado_explore_and_filter_fields():
    raw = {
        "bookSourceName": "山雨阅读",
        "bookSourceUrl": "https://www.shanyuread.com",
        "bookSourceComment": "html版",
        "enabledExplore": True,
        "exploreUrl": ["玄幻::https://www.shanyuread.com/mufen/cat/xuanhuan/p1_info.html"],
        "ruleBookInfo": {
            "author": "#info p:nth-of-type(1)",
            "authorFilter": ["作者:", ""],
        },
        "ruleToc": {
            "chapterList": "#chapterlist dd a",
            "chapterName": "text",
            "chapterUrl": "href",
            "nextTocUrl": ".listpage .right a@href",
        },
        "ruleContent": {
            "content": "#chapter@html",
            "contentFilter": ["<script.*?</script>"],
            "nextContentUrl": "a:contains('下一章')@href",
        },
        "ruleExplore": {
            "bookList": "#list .row",
            "bookUrl": ".info .name@href",
            "nextUrl": ".listpage .right a@href",
        },
    }

    source = BookSource(**raw)
    dumped = source.model_dump()

    assert dumped["bookSourceComment"] == "html版"
    assert dumped["enabledExplore"] is True
    assert dumped["exploreUrl"] == raw["exploreUrl"]
    assert dumped["ruleBookInfo"]["authorFilter"] == ["作者:", ""]
    assert source.ruleToc.nextTocUrl == ".listpage .right a@href"
    assert source.ruleContent.contentFilter == ["<script.*?</script>"]
    assert source.ruleExplore.noteUrl == ".info .name@href"


def test_import_normalization_keeps_common_legado_fields():
    raw = {
        "bookSourceName": "山雨阅读",
        "bookSourceUrl": "https://www.shanyuread.com",
        "bookSourceComment": "html版",
        "enabledExplore": True,
        "exploreUrl": ["玄幻::https://www.shanyuread.com/mufen/cat/xuanhuan/p1_info.html"],
        "header": '{"User-Agent":"Mobile UA"}',
        "ruleExplore": {
            "bookList": "#list .row",
            "bookUrl": ".info .name@href",
        },
        "ruleContent": {
            "content": "#chapter@html",
            "contentFilter": ["<script.*?</script>"],
        },
    }

    normalized = SourceManager()._normalize_import(raw)

    assert normalized["bookSourceComment"] == "html版"
    assert normalized["enabledExplore"] is True
    assert normalized["exploreUrl"] == raw["exploreUrl"]
    assert normalized["headers"] == {"User-Agent": "Mobile UA"}
    assert normalized["ruleExplore"]["noteUrl"] == ".info .name@href"
    assert normalized["ruleContent"]["contentFilter"] == ["<script.*?</script>"]


def test_create_source_ignores_user_supplied_system_fields(monkeypatch, tmp_path):
    manager = SourceManager()
    monkeypatch.setattr(manager, "_loaded", True)
    monkeypatch.setattr(manager, "_cache", {})
    monkeypatch.setattr(manager.settings, "SOURCES_DIR", tmp_path)

    source = manager.create_source(
        {
            "id": "../evil",
            "createdAt": "bad-created",
            "updatedAt": "bad-updated",
            "bookSourceName": "安全测试源",
            "bookSourceUrl": "https://safe.example",
        }
    )
    stored_files = list(tmp_path.glob("*.json"))
    assert len(stored_files) == 1
    stored = json.loads(stored_files[0].read_text(encoding="utf-8"))

    assert source.id != "../evil"
    assert source.createdAt != "bad-created"
    assert source.updatedAt != "bad-updated"
    assert stored["id"] == source.id
    assert not (tmp_path.parent / "evil.json").exists()
    with pytest.raises(ValueError):
        manager._source_file_path("../evil")


def test_rule_engine_supports_current_item_attrs_filters_and_page_rules():
    html = """
    <div id="info"><p>作者: 测试作者 著</p></div>
    <dl id="chapterlist">
      <dd><a href="/c1.html">第一章</a></dd>
      <dd><a href="/c2.html">第二章</a></dd>
    </dl>
    <div class="listpage"><span class="right"><a href="/p2.html">下一页</a></span></div>
    <div id="chapter">正文<script>bad()</script><div id="p-cache">广告</div></div>
    """

    toc = RuleEngine.apply_rules(
        html,
        {
            "chapterList": "#chapterlist dd a",
            "chapterName": "text",
            "chapterUrl": "href",
            "nextTocUrl": ".listpage .right a@href",
        },
    )
    info = RuleEngine.apply_rules(
        html,
        {"author": "#info p:nth-of-type(1)", "authorFilter": [r"作者:\s*(.*?)\s*著", r"\1"]},
    )
    content = RuleEngine.apply_rules(
        html,
        {
            "content": "#chapter@html",
            "contentFilter": ["<script.*?</script>", '<div id="p-cache.*?</div>'],
        },
    )

    assert toc["chapterList"] == [
        {"chapterName": "第一章", "chapterUrl": "/c1.html"},
        {"chapterName": "第二章", "chapterUrl": "/c2.html"},
    ]
    assert toc["nextTocUrl"] == "/p2.html"
    assert info["author"] == "测试作者"
    assert "bad()" not in content["content"]
    assert "广告" not in content["content"]


def test_parse_request_spec_post_body():
    request = parse_request_spec(
        'https://example.com/api/search,{"method":"POST","body":"q=测试","headers":{"X-Test":"1"}}'
    )
    assert request is not None
    assert request.url == "https://example.com/api/search"
    assert request.method == "POST"
    assert request.body == "q=测试"
    assert request.headers == {"X-Test": "1"}


def test_parse_request_spec_with_retry_and_option_js():
    request = parse_request_spec(
        'https://example.com/api,{"retry":1,"js":"java.headerMap.put(\\"X-Sign\\",\\"abc\\");java.url=java.url+\\"?ok=1\\";java.method=\\"POST\\";java.body=\\"q=1\\";"}'
    )
    assert request is not None
    assert request.url == "https://example.com/api?ok=1"
    assert request.method == "POST"
    assert request.body == "q=1"
    assert request.retry == 1
    assert request.headers == {"X-Sign": "abc"}


def test_parse_request_spec_relative_url():
    request = parse_request_spec('/api/search?q=测试', base_url="https://example.com")
    assert request is not None
    assert request.url == "https://example.com/api/search?q=测试"


def test_build_template_url_expressions():
    url = build_template_url(
        "https://example.com/s?q={{encodeURIComponent(key)}}&p={{page+1}}&b={{java.base64Encode(key)}}",
        "斗 破",
        2,
    )
    assert url == "https://example.com/s?q=%E6%96%97%20%E7%A0%B4&p=3&b=5paXIOegtA=="


def test_build_js_search_request_posts_extracted_ajax_vars(monkeypatch):
    from app.core.http_client import http_client
    from app.core.legado import build_search_request

    async def fake_get(url, headers=None):
        assert url == "https://m.zzhhwy.com/user/search.html?q=斗破"
        return {
            "status": 200,
            "headers": {},
            "body": 'var vw = "v1";var sign = "s1";',
        }

    monkeypatch.setattr(http_client, "get", fake_get)

    source = SimpleNamespace(
        bookSourceUrl="https://m.zzhhwy.com",
        headers=None,
        searchUrl='''@js:
url = source.key+"/api/search";
rr = java.ajax(source.key+"/user/search.html?q="+key);
bd = {
 "body": `q=${key}&vw=${vw}&sign=${sign}`,
 "method": "POST"
}
url + "," + JSON.stringify(bd);''',
    )

    request = asyncio.run(build_search_request(source, "斗破", 1))
    assert request is not None
    assert request.url == "https://m.zzhhwy.com/api/search"
    assert request.method == "POST"
    assert request.body == "q=斗破&vw=v1&sign=s1"


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js runtime is not available")
def test_node_js_runtime_handles_general_search_script():
    from app.core.legado import build_search_request

    source = SimpleNamespace(
        bookSourceUrl="https://example.com",
        headers=None,
        searchUrl='''@js:
const path = ["api", "search"].join("/");
const bd = {
  body: "q=" + java.encodeURIComponent(key),
  method: "POST"
};
source.key + "/" + path + "," + JSON.stringify(bd);''',
    )

    request = asyncio.run(build_search_request(source, "斗破 苍穹", 1))
    assert request is not None
    assert request.url == "https://example.com/api/search"
    assert request.method == "POST"
    assert request.body == "q=%E6%96%97%E7%A0%B4%20%E8%8B%8D%E7%A9%B9"


def test_js_expression_search_request_without_node_runtime(monkeypatch):
    import app.core.legado_js as legado_js
    from app.core.legado import build_search_request

    async def fake_execute_search_script(*args, **kwargs):
        return None

    monkeypatch.setattr(legado_js, "execute_search_script", fake_execute_search_script)

    source = SimpleNamespace(
        bookSourceUrl="https://101kanshu.net",
        headers=None,
        searchUrl="@js:'/101search/,'+JSON.stringify({method:'POST',body:'searchkey='+encodeURIComponent(key)})",
    )

    request = asyncio.run(build_search_request(source, "斗破苍穹", 1))
    assert request is not None
    assert request.url == "https://101kanshu.net/101search/"
    assert request.method == "POST"
    assert request.body == "searchkey=%E6%96%97%E7%A0%B4%E8%8B%8D%E7%A9%B9"
