"""工具函数：指纹生成、文本归一化等。"""

import hashlib
import re
from difflib import SequenceMatcher

# 常见标点与空白清洗
_PUNCT_RE = re.compile(r"[\s\u3000\[\]【】（）()《》<>「」""''\"',.!！？?、:：;；]+")
# 书名常见后缀（如 (全本)、（精校））
_SUFFIX_RE = re.compile(r"[（(].*?[)）]\s*$")


def normalize_title(title: str) -> str:
    """归一化书名：去标点/空白、去括号后缀、转小写。"""
    if not title:
        return ""
    text = _SUFFIX_RE.sub("", title)
    text = _PUNCT_RE.sub("", text)
    return text.lower().strip()


def normalize_author(author: str) -> str:
    """归一化作者名。"""
    if not author:
        return ""
    text = _PUNCT_RE.sub("", author)
    return text.lower().strip()


def book_fingerprint(name: str, author: str) -> str:
    """生成书籍指纹：md5(归一化书名[:20]|归一化作者[:10])。"""
    n = normalize_title(name)[:20]
    a = normalize_author(author)[:10]
    raw = f"{n}|{a}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度。"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def is_same_book(name1: str, author1: str, name2: str, author2: str) -> bool:
    """判断是否同一本书：指纹相同或相似度达标。"""
    if book_fingerprint(name1, author1) == book_fingerprint(name2, author2):
        return True
    title_sim = similarity(normalize_title(name1), normalize_title(name2))
    author_sim = similarity(normalize_author(author1), normalize_author(author2))
    return title_sim > 0.9 and author_sim > 0.8


def build_search_url(template: str, keyword: str, page: int = 1) -> str:
    """构造搜索URL，替换占位符。"""
    from app.core.legado import build_template_url

    return build_template_url(template, keyword, page)


def resolve_relative_url(base: str, url: str) -> str:
    """将相对URL解析为绝对URL。"""
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if not base:
        return url
    # 去掉 base 末尾的路径
    if url.startswith("//"):
        if base.startswith("https://"):
            return "https:" + url
        return "http:" + url
    if url.startswith("/"):
        # 绝对路径
        idx = base.find("://")
        if idx > 0:
            slash = base.find("/", idx + 3)
            host = base[:slash] if slash > 0 else base
            return host + url
    # 相对路径
    idx = base.rfind("/")
    if idx > 8:  # base 中有路径分隔
        return base[: idx + 1] + url
    return base.rstrip("/") + "/" + url


def clean_text(text: str) -> str:
    """清理提取文本中的多余空白。"""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()
