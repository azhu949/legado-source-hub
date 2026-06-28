"""规则引擎单元测试。"""

import json

import pytest

from app.core.rule_engine import RuleEngine


# ---------------- JsonPath ----------------


def test_jsonpath_simple():
    data = {"store": {"book": [{"title": "书A"}, {"title": "书B"}]}}
    content = json.dumps(data)
    result = RuleEngine.extract(content, "$.store.book[*].title", is_json=True)
    assert result == ["书A", "书B"]


def test_jsonpath_single():
    data = {"data": {"name": "测试书名"}}
    content = json.dumps(data)
    result = RuleEngine.extract(content, "$.data.name", is_json=True)
    assert result == "测试书名"


def test_jsonpath_no_match():
    data = {"data": {"name": "x"}}
    content = json.dumps(data)
    result = RuleEngine.extract(content, "$.data.notexist", is_json=True)
    assert result is None


# ---------------- XPath ----------------


def test_xpath_text():
    html = '<div><span class="title">书名</span></div>'
    result = RuleEngine.extract(html, '//span[@class="title"]/text()')
    assert result == "书名"


def test_xpath_list():
    html = '<ul><li>第一章</li><li>第二章</li></ul>'
    result = RuleEngine.extract(html, '//ul/li/text()')
    assert result == ["第一章", "第二章"]


# ---------------- CSS ----------------


def test_css_select():
    html = '<div class="item"><a href="/book/1">书A</a></div>'
    result = RuleEngine.extract(html, '@css:.item a')
    assert "书A" in str(result)


# ---------------- 正则 ----------------


def test_regex_extract():
    html = "<title>我的书名</title>"
    result = RuleEngine.extract(html, "@regex:<title>(.*?)</title>")
    assert result == "我的书名"


def test_xsw_aes_content_rule():
    html = """
    <script>
    var encrypted = "NkCCQiLcD+X8RjPozfEWcxW/h8DqthY45cGfVuNzRx0=";
    var key = "e10adc3949ba59abbe56e057f20f883e";
    var iv  = "c33367701511b4f6020ec61ded352059";
    </script>
    """

    result = RuleEngine.extract(html, "@xsw-aes-content")

    assert result == "&nbsp;&nbsp;正文<br>下一行"


def test_content_filter_preserves_newline_replacement():
    html = "<div id='chapter'>第一段<br/>第二段&nbsp;&nbsp;尾</div>"
    result = RuleEngine.apply_rules(
        html,
        {
            "content": "#chapter@html",
            "contentFilter": [
                r"<br\s*/?>##" + "\n",
                "&nbsp;## ",
                "\xa0## ",
            ],
        },
    )

    assert result["content"] == "第一段\n第二段  尾"


def test_content_filter_can_remove_spaces_between_cjk_chars():
    result = RuleEngine.apply_rules(
        "<div id='chapter'>警 察 局 。 2 1</div>",
        {
            "content": "#chapter@html",
            "contentFilter": [
                r"(?<=[\u4e00-\u9fff0-9，。！？；：“”‘’、])[\u00a0 ]+(?=[\u4e00-\u9fff0-9，。！？；：“”‘’、])##",
            ],
        },
    )

    assert result["content"] == "警察局。21"


# ---------------- apply_rules ----------------


def test_apply_rules_search_list():
    data = {
        "data": [
            {"name": "书A", "author": "作者A"},
            {"name": "书B", "author": "作者B"},
        ]
    }
    content = json.dumps(data)
    rules = {
        "bookList": "$.data[*]",
        "name": "$.name",
        "author": "$.author",
    }
    result = RuleEngine.apply_rules(content, rules, is_json=True)
    assert "bookList" in result
    assert len(result["bookList"]) == 2
    assert result["bookList"][0]["name"] == "书A"


def test_json_prefix_rule():
    content = json.dumps({"data": {"name": "带前缀"}})
    assert RuleEngine.extract(content, "@json:$.data.name", is_json=False) == "带前缀"


def test_apply_rules_search_list_with_legado_js_suffix():
    data = {
        "data": {
            "search": [
                {
                    "book_name": "岁月书",
                    "author": "作者",
                    "book_list_url": "/book/1/",
                }
            ]
        }
    }
    content = json.dumps(data)
    rules = {
        "bookList": '<js>result.replace(/<!--gg-->/, "")</js>\n$.data.search[*]@js:\nresult',
        "name": "$.book_name",
        "author": "$.author",
        "noteUrl": "$.book_list_url",
    }
    result = RuleEngine.apply_rules(content, rules, is_json=True)
    assert result["bookList"][0]["name"] == "岁月书"
    assert result["bookList"][0]["noteUrl"] == "/book/1/"


def test_apply_rules_json_list_renders_template_fields():
    data = {
        "data": {
            "items": [
                {
                    "articleid": 416,
                    "articlename": "风水之王",
                    "author": "紫梦游龙",
                }
            ]
        }
    }

    result = RuleEngine.apply_rules(
        json.dumps(data, ensure_ascii=False),
        {
            "bookList": "$.data.items[*]",
            "name": "$.articlename",
            "author": "$.author",
            "bookUrl": "https://novel.cooks.tw/api/novel/detail/{{$.articleid}}?lang=zh-CN",
        },
        is_json=True,
    )

    assert result["bookList"][0]["name"] == "风水之王"
    assert result["bookList"][0]["bookUrl"] == "https://novel.cooks.tw/api/novel/detail/416?lang=zh-CN"


def test_apply_rules_handles_cooks_inline_js_book_info():
    data = {"code": 200, "data": {"articleid": 416, "articlename": "风水之王"}}
    result = RuleEngine.apply_rules(
        json.dumps(data, ensure_ascii=False),
        {
            "coverUrl": "$.data.articleid\n<js>Cover(result)</js>",
            "tocUrl": (
                "<js>var j=J(result);var d=j.data||j;var id=d.articleid||'';"
                "Base()+'/api/chapter/list/'+id+'?lang=zh-CN'</js>"
            ),
        },
        is_json=True,
        base_url="https://novel.cooks.tw/api/novel/detail/416?lang=zh-CN",
    )

    assert result["coverUrl"] == "https://pic.cooks.tw/0/416/416s.jpg"
    assert result["tocUrl"] == "https://novel.cooks.tw/api/chapter/list/416?lang=zh-CN"


def test_apply_rules_json_list_handles_or_rules_and_cooks_chapter_url_js():
    data = {
        "code": 200,
        "data": [{"chapterid": 4553, "chaptername": "第1章 妖胎"}],
    }

    result = RuleEngine.apply_rules(
        json.dumps(data, ensure_ascii=False),
        {
            "chapterList": (
                "$.data[*]||$.data.items[*]||$.data.list[*]||$.data.chapterlist[*]"
                "||$.data.chapterList[*]||$.data.chapters[*]"
            ),
            "chapterName": "$.chaptername||$.chapter_name||$.chapterName||$.title||$.name",
            "chapterUrl": (
                "$.chapterid\n<js>var aid='';try{aid=cache.getFromMemory('articleid')||'';}"
                "catch(e){}if(!aid){var m=String(baseUrl||'').match(/list\\/(\\d+)/);"
                "if(m)aid=m[1];}Base()+'/api/chapter/content/'+aid+'/'+result+'?lang=zh-CN'</js>"
            ),
        },
        is_json=True,
        base_url="https://novel.cooks.tw/api/chapter/list/416?lang=zh-CN",
    )

    assert result["chapterList"] == [
        {
            "chapterName": "第1章 妖胎",
            "chapterUrl": "https://novel.cooks.tw/api/chapter/content/416/4553?lang=zh-CN",
        }
    ]


def test_css_selector_attr():
    html = '<meta property="og:image" content="/cover.jpg"><a href="/book/1">书名</a>'
    assert RuleEngine.extract(html, '[property="og:image"]@content') == "/cover.jpg"
    assert RuleEngine.extract(html, "a@text") == "书名"
    assert RuleEngine.extract(html, "a@href") == "/book/1"


def test_selector_attr_with_legado_index_suffix():
    html = '<div class="author">作者：甲</div><div class="author">作者：乙</div>'
    assert RuleEngine.extract(html, "div.author.1@text") == "作者：乙"


def test_compound_rule_join():
    html = """
    <meta property="og:novel:status" content="连载">
    <meta property="og:novel:category" content="玄幻">
    """
    result = RuleEngine.extract(
        html,
        '[property="og:novel:status"]@content&&[property="og:novel:category"]@content',
    )
    assert result == "连载 玄幻"


def test_apply_rules_html_list_preserves_child_node():
    html = '<ul class="chapter"><li><a href="/1.html">第一章</a></li><li><a href="/2.html">第二章</a></li></ul>'
    result = RuleEngine.apply_rules(
        html,
        {
            "chapterList": "ul.chapter > li",
            "chapterName": "a@text",
            "chapterUrl": "a@href",
        },
    )
    assert result["chapterList"][0]["chapterName"] == "第一章"
    assert result["chapterList"][1]["chapterUrl"] == "/2.html"


def test_plain_css_selector_is_not_treated_as_regex_first():
    html = '<div class="item">书A</div><div class="item">书B</div>'
    assert RuleEngine.extract(html, ".item") == ["书A", "书B"]


def test_default_jsoup_rule_subset():
    html = '<div class="book"><a href="/book/1">书A</a></div>'
    assert RuleEngine.extract(html, "class.book@tag.a.0@href") == "/book/1"
    assert RuleEngine.extract(html, "class.book@tag.a.0@text") == "书A"


def test_or_operator_uses_first_non_empty_result():
    html = '<div class="title">书名</div>'
    assert RuleEngine.extract(html, ".missing@text||.title@text") == "书名"


def test_interleave_operator():
    html = '<div class="a">A1</div><div class="a">A2</div><div class="b">B1</div><div class="b">B2</div>'
    assert RuleEngine.extract(html, ".a%%.b") == ["A1", "B1", "A2", "B2"]


def test_regex_replacement_rule():
    html = '<div class="intro">简介：  很长   </div>'
    assert RuleEngine.extract(html, ".intro@text##\\s+##") == "简介：很长"


def test_regex_replacement_rule_defaults_to_empty_replacement():
    html = '<div class="author">作者：天蚕土豆</div>'
    assert RuleEngine.extract(html, "div.author.0@text##作者：") == "天蚕土豆"


def test_regex_replacement_all_rule():
    assert RuleEngine.extract("a1b2", "all##\\d##") == "ab"


def test_apply_rules_empty():
    result = RuleEngine.apply_rules("", {})
    assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
