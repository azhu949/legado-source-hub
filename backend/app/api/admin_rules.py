"""规则测试路由。"""

import logging
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.http_client import http_client
from app.core.legado import build_search_request, build_template_url, execute_request, response_is_json
from app.core.rule_engine import RuleEngine
from app.core.source_manager import source_manager
from app.models.responses import success, error
from app.models.source import TestRuleRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/rules", tags=["rules"])
DEFAULT_TEST_KEYWORD = "斗破苍穹"


@router.post("/test")
async def test_rule(req: TestRuleRequest, _user=Depends(get_current_user)):
    """对指定 URL 执行规则提取并返回结果。

    若提供 sourceId，则使用该书源的规则与请求头。
    """
    headers = {}
    rules = req.rules

    source = None
    if req.sourceId:
        source = source_manager.get_source(req.sourceId)
        if source:
            headers = source.headers or {}
            if not rules:
                rules = {
                    "ruleSearch": source.ruleSearch.model_dump(),
                    "ruleBookInfo": source.ruleBookInfo.model_dump(),
                    "ruleToc": source.ruleToc.model_dump(),
                    "ruleContent": source.ruleContent.model_dump(),
                }

    if not req.testUrl and not source:
        return error("VALIDATION_ERROR", "测试URL不能为空")

    # 发起请求
    if req.testUrl:
        source_key = source.bookSourceUrl if source else ""
        test_url = build_template_url(req.testUrl, DEFAULT_TEST_KEYWORD, 1, source_key=source_key)
        test_url = _normalize_test_url(test_url)
        resp = await http_client.get(test_url, headers=headers, retries=0)
    else:
        request = await build_search_request(source, DEFAULT_TEST_KEYWORD, 1)
        if not request:
            return error("VALIDATION_ERROR", "书源缺少可测试的搜索URL")
        resp = await execute_request(request, source_headers=headers)

    if resp["status"] == 0:
        return error("FETCH_FAILED", resp.get("error", "请求失败"))

    body = resp["body"]
    is_json = req.isJson or response_is_json(resp)

    # 提取结果
    extracted: dict = {}
    if rules:
        for section, section_rules in rules.items():
            if not isinstance(section_rules, dict):
                continue
            result = RuleEngine.apply_rules(body, section_rules, is_json=is_json)
            extracted[section] = result

    return success(
        data={
            "http": {
                "status": resp["status"],
                "headers": dict(resp["headers"]),
                "elapsed_ms": resp["elapsed_ms"],
                "url": resp["url"],
            },
            "raw": body[:50000],  # 限制返回大小
            "extracted": extracted,
            "isJson": is_json,
        }
    )


def _normalize_test_url(url: str) -> str:
    """Map known unreachable mobile test endpoints to reachable desktop endpoints."""
    parsed = urlparse(url)
    if (
        parsed.netloc.lower() == "m.xsw.tw"
        and parsed.path == "/modules/article/wap_search.php"
    ):
        return urlunparse(
            (
                parsed.scheme or "https",
                "www.xsw.tw",
                "/modules/article/search.php",
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    return url
