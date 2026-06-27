"""规则测试接口辅助逻辑测试。"""

from app.api.admin_rules import _normalize_test_url
from app.core.legado import build_template_url


def test_normalize_xsw_mobile_search_test_url():
    template = "https://m.xsw.tw/modules/article/wap_search.php?searchkey={{encodeURIComponent(key)}}"
    url = build_template_url(template, "斗破苍穹", 1)

    assert _normalize_test_url(url) == (
        "https://www.xsw.tw/modules/article/search.php?"
        "searchkey=%E6%96%97%E7%A0%B4%E8%8B%8D%E7%A9%B9"
    )


def test_normalize_test_url_keeps_other_urls():
    url = "https://example.com/search?q=abc"

    assert _normalize_test_url(url) == url
