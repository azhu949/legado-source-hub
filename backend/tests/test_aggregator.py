"""聚合器单元测试。"""

from app.core.aggregator import Aggregator


def test_aggregate_dedup_by_fingerprint():
    """相同书名+作者应去重。"""
    results = [
        ("src-a", 100, [{"name": "斗破苍穹", "author": "天蚕土豆", "intro": "简介A", "sourceName": "源A"}]),
        ("src-b", 200, [{"name": "斗破苍穹", "author": "天蚕土豆", "intro": "", "sourceName": "源B"}]),
    ]
    aggregated = Aggregator.aggregate_search_results(results)
    assert len(aggregated) == 1
    # 字段应被合并（补充了简介）
    assert aggregated[0]["intro"] == "简介A"
    assert aggregated[0]["sourceCount"] == 2
    assert aggregated[0]["sourceNames"] == ["源B", "源A"]
    assert aggregated[0]["sourceName"] == "源B、源A"


def test_aggregate_sort_by_weight():
    """结果应按权重降序排列。"""
    results = [
        ("src-a", 100, [{"name": "书A", "author": "作者A"}]),
        ("src-b", 300, [{"name": "书B", "author": "作者B"}]),
        ("src-c", 200, [{"name": "书C", "author": "作者C"}]),
    ]
    aggregated = Aggregator.aggregate_search_results(results)
    assert aggregated[0]["name"] == "书B"
    assert aggregated[1]["name"] == "书C"
    assert aggregated[2]["name"] == "书A"


def test_aggregate_different_books():
    """不同书应保留。"""
    results = [
        ("src-a", 100, [{"name": "书A", "author": "作者A", "sourceName": "源A"}]),
        ("src-b", 200, [{"name": "书B", "author": "作者B", "sourceName": "源B"}]),
    ]
    aggregated = Aggregator.aggregate_search_results(results)
    assert len(aggregated) == 2
    assert aggregated[0]["sourceName"] == "源B"
    assert aggregated[1]["sourceName"] == "源A"


def test_aggregate_merge_fields():
    """应合并补充缺失字段。"""
    results = [
        ("src-a", 100, [{"name": "书A", "author": "作者A", "coverUrl": "http://a.com/cover.jpg", "intro": ""}]),
        ("src-b", 200, [{"name": "书A", "author": "作者A", "coverUrl": "", "intro": "这是简介"}]),
    ]
    aggregated = Aggregator.aggregate_search_results(results)
    assert len(aggregated) == 1
    assert aggregated[0]["coverUrl"] == "http://a.com/cover.jpg"
    assert aggregated[0]["intro"] == "这是简介"


def test_aggregate_empty():
    aggregated = Aggregator.aggregate_search_results([])
    assert aggregated == []


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
