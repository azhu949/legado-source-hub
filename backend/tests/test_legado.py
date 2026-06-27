"""Legado compatibility helper tests."""

import asyncio
import shutil
from types import SimpleNamespace

import pytest

from app.core.legado import build_template_url, normalize_source_dict, parse_request_spec
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
        }
    )
    assert normalized["headers"] == {"Referer": "https://example.com"}
    assert normalized["ruleSearch"]["noteUrl"] == "$.url"


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
