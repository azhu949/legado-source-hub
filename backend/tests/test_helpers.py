"""工具函数单元测试。"""

from app.utils.helpers import (
    book_fingerprint,
    normalize_author,
    is_same_book,
    normalize_title,
    build_search_url,
    resolve_relative_url,
)
from app.api.public import _normalize_toc_chapters, _same_mobile_www_site, _source_id_from_url


def test_book_fingerprint_consistent():
    fp1 = book_fingerprint("斗破苍穹", "天蚕土豆")
    fp2 = book_fingerprint("斗破苍穹", "天蚕土豆")
    assert fp1 == fp2


def test_book_fingerprint_different():
    fp1 = book_fingerprint("斗破苍穹", "天蚕土豆")
    fp2 = book_fingerprint("武动乾坤", "天蚕土豆")
    assert fp1 != fp2


def test_is_same_book_exact():
    assert is_same_book("斗破苍穹", "天蚕土豆", "斗破苍穹", "天蚕土豆")


def test_is_same_book_similar():
    assert is_same_book("斗破苍穹", "天蚕土豆", "斗破苍穹 ", " 天蚕土豆")


def test_is_same_book_different():
    assert not is_same_book("斗破苍穹", "天蚕土豆", "斗罗大陆", "唐家三少")


def test_normalize_title():
    assert normalize_title("《斗破苍穹》") == "斗破苍穹"
    assert normalize_title(" 斗破苍穹 ") == "斗破苍穹"
    assert normalize_title("斗破苍穹(全本)") == "斗破苍穹"


def test_normalize_chinese_variants():
    assert normalize_title("《鬥破蒼穹》") == normalize_title("斗破苍穹")
    assert normalize_title("凡人修仙傳") == normalize_title("凡人修仙传")
    assert normalize_author("辰東") == normalize_author("辰东")


def test_build_search_url():
    url = build_search_url("https://example.com/search?q={{key}}&p={{page}}", "小说", 2)
    assert url == "https://example.com/search?q=小说&p=2"


def test_resolve_relative_url_absolute():
    assert resolve_relative_url("https://a.com", "https://b.com/x") == "https://b.com/x"


def test_resolve_relative_url_root():
    assert resolve_relative_url("https://a.com/book/1", "/chapter/1") == "https://a.com/chapter/1"


def test_resolve_relative_url_relative():
    result = resolve_relative_url("https://a.com/book/", "1.html")
    assert result == "https://a.com/book/1.html"


def test_resolve_relative_url_accepts_non_string_url():
    result = resolve_relative_url("https://a.com/book/", 416)
    assert result == "https://a.com/book/416"


def test_same_mobile_www_site():
    assert _same_mobile_www_site("m.xsw.tw", "www.xsw.tw")
    assert _same_mobile_www_site("www.xsw.tw", "m.xsw.tw")
    assert not _same_mobile_www_site("m.xsw.tw", "api.xsw.tw")


def test_source_id_from_url():
    assert _source_id_from_url("https://www.xsw.tw/book/1/?sourceId=abc") == "abc"
    assert _source_id_from_url("https://www.xsw.tw/book/1/") == ""


def test_normalize_toc_chapters():
    chapters = _normalize_toc_chapters(
        [{"chapterName": "第一章", "chapterUrl": "/book/1/1.html"}],
        "https://example.com/book/1/",
    )
    assert chapters == [{"name": "第一章", "url": "https://example.com/book/1/1.html"}]


def test_normalize_toc_chapters_prefers_xsw_mobile_chapter_url():
    chapters = _normalize_toc_chapters(
        [{"chapterName": "第一章", "chapterUrl": "/book/1630904/255350744.html"}],
        "https://www.xsw.tw/book/1630904/",
    )
    assert chapters == [{"name": "第一章", "url": "https://m.xsw.tw/1630904/255350744.html"}]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
