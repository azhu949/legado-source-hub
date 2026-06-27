"""结果聚合器：多源搜索结果去重、合并、排序。"""

import logging
from typing import Any

from app.utils.helpers import (
    book_fingerprint,
    is_same_book,
    normalize_author,
    normalize_title,
)

logger = logging.getLogger(__name__)


class Aggregator:
    """搜索结果聚合器。"""

    @staticmethod
    def aggregate_search_results(
        results_by_source: list[tuple[str, int, list[dict]]],
    ) -> list[dict]:
        """聚合多个书源的搜索结果。

        Args:
            results_by_source: [(source_id, weight, [book_dict, ...]), ...]
                每个 book_dict 至少含 name, author 字段。

        Returns:
            去重、合并、排序后的书籍列表。
        """
        # 按权重降序排列各源，保证高权重源的结果优先进入聚合
        sorted_sources = sorted(results_by_source, key=lambda x: x[1], reverse=True)

        aggregated: list[dict] = []  # 已聚合的书籍
        fingerprints: list[str] = []  # 对应的指纹

        for source_id, weight, books in sorted_sources:
            if not books:
                continue
            for book in books:
                name = str(book.get("name", "")).strip()
                author = str(book.get("author", "")).strip()
                source_name = str(book.get("sourceName") or book.get("bookSourceName") or source_id).strip()
                if not name:
                    continue

                fp = book_fingerprint(name, author)
                matched_idx = Aggregator._find_match(aggregated, fingerprints, name, author, fp)

                if matched_idx is not None:
                    # 合并字段
                    Aggregator._merge_book(aggregated[matched_idx], book, weight, source_id)
                else:
                    # 新书
                    entry = dict(book)
                    entry["name"] = entry.get("name", name) or name
                    entry["author"] = entry.get("author", author) or author
                    entry["_weight"] = weight
                    entry["_sources"] = [source_id]
                    entry["_sourceNames"] = [source_name] if source_name else []
                    entry["_fingerprint"] = fp
                    aggregated.append(entry)
                    fingerprints.append(fp)

        # 按权重降序排序
        aggregated.sort(key=lambda x: x.get("_weight", 0), reverse=True)

        # 移除内部字段
        for book in aggregated:
            book.pop("_weight", None)
            book.pop("_fingerprint", None)
            # 保留 _sources 作为多源标记（前端可展示），重命名为 sources
            sources = book.pop("_sources", [])
            source_names = book.pop("_sourceNames", [])
            if sources:
                book["sourceCount"] = len(sources)
            if source_names:
                book["sourceName"] = source_names[0] if len(source_names) == 1 else "、".join(source_names)
                book["sourceNames"] = source_names

        return aggregated

    @staticmethod
    def _find_match(
        aggregated: list[dict],
        fingerprints: list[str],
        name: str,
        author: str,
        fp: str,
    ) -> int | None:
        """在已聚合列表中查找匹配项索引。"""
        # 先用指纹精确匹配
        for i, existing_fp in enumerate(fingerprints):
            if existing_fp == fp:
                return i
        # 再用相似度匹配
        for i, book in enumerate(aggregated):
            if is_same_book(
                name,
                author,
                str(book.get("name", "")),
                str(book.get("author", "")),
            ):
                # 更新指纹为合并后的
                fingerprints[i] = fp
                return i
        return None

    @staticmethod
    def _merge_book(existing: dict, new_book: dict, weight: int, source_id: str) -> None:
        """合并两本书的字段：补充缺失字段。"""
        # 记录来源
        sources: list = existing.get("_sources", [])
        if source_id not in sources:
            sources.append(source_id)
        existing["_sources"] = sources
        source_name = str(new_book.get("sourceName") or new_book.get("bookSourceName") or source_id).strip()
        source_names: list = existing.get("_sourceNames", [])
        if source_name and source_name not in source_names:
            source_names.append(source_name)
        existing["_sourceNames"] = source_names

        # 更新权重为最大值
        existing["_weight"] = max(existing.get("_weight", 0), weight)

        # 补充缺失字段
        merge_fields = [
            "intro", "coverUrl", "kind", "lastChapter", "wordCount",
            "noteUrl", "tocUrl",
        ]
        for field in merge_fields:
            if not existing.get(field) and new_book.get(field):
                existing[field] = new_book[field]

        # 名称/作者取更完整的
        new_name = str(new_book.get("name", "")).strip()
        if len(new_name) > len(str(existing.get("name", ""))):
            existing["name"] = new_name
        new_author = str(new_book.get("author", "")).strip()
        if len(new_author) > len(str(existing.get("author", ""))):
            existing["author"] = new_author

    @staticmethod
    def aggregate_toc_results(chapters: list[dict]) -> list[dict]:
        """聚合目录结果：去重章节、保持顺序。"""
        seen_urls: set[str] = set()
        seen_names: set[str] = set()
        result: list[dict] = []
        for ch in chapters:
            url = str(ch.get("url", "")).strip()
            name = str(ch.get("name", "")).strip()
            if not name:
                continue
            # URL 去重
            if url and url in seen_urls:
                continue
            # 章节名去重（避免不同源重复章节）
            norm_name = normalize_title(name)
            if norm_name in seen_names:
                continue
            if url:
                seen_urls.add(url)
            seen_names.add(norm_name)
            result.append({"name": name, "url": url})
        return result
