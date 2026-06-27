"""源健康检查器：定时探测子书源可用性。"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.core.legado import build_search_request, execute_request, response_is_json
from app.core.rule_engine import RuleEngine
from app.core.source_manager import source_manager
from app.models.database import add_health_record

logger = logging.getLogger(__name__)

# 健康检查测试关键词
TEST_KEYWORD = "测试"


class HealthChecker:
    """书源健康检查器。"""

    _instance: Optional["HealthChecker"] = None
    _task: Optional[asyncio.Task] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.settings = get_settings()
            self._initialized = True

    async def check_source(self, source) -> dict:
        """检查单个书源的可用性。

        Args:
            source: BookSource 对象。

        Returns:
            {"status": "healthy"/"unhealthy", "latency_ms": int, "message": str}
        """
        request = await build_search_request(source, TEST_KEYWORD, 1)
        if not request:
            return {
                "status": "unhealthy",
                "latency_ms": None,
                "message": "缺少搜索URL模板",
            }

        headers = source.headers or {}
        result = await execute_request(request, source_headers=headers)

        status = "unhealthy"
        message = ""
        latency = result.get("elapsed_ms")

        if result.get("status") == 0:
            message = result.get("error", "请求失败")
        elif result["status"] >= 400:
            message = f"HTTP {result['status']}"
        else:
            # 检查规则是否仍能提取到数据
            body = result.get("body", "")
            is_json = response_is_json(result)
            if body:
                try:
                    rule_search = source.ruleSearch
                    if rule_search and rule_search.bookList:
                        extracted = RuleEngine.apply_rules(
                            body,
                            {"bookList": rule_search.bookList},
                            is_json=is_json,
                        )
                        books = extracted.get("bookList", []) if isinstance(extracted, dict) else []
                        if books:
                            status = "healthy"
                            message = f"成功提取 {len(books)} 条结果"
                        else:
                            message = "规则未能提取到数据"
                    else:
                        # 无规则，仅检查 HTTP 可达性
                        status = "healthy"
                        message = "HTTP 可达"
                except Exception as e:  # noqa: BLE001
                    message = f"规则解析异常: {e}"
            else:
                message = "响应体为空"

        return {"status": status, "latency_ms": latency, "message": message}

    async def check_all(self) -> list[dict]:
        """对所有启用的书源执行健康检查。

        Returns:
            [{"id": ..., "bookSourceName": ..., "status": ..., "latency_ms": ..., "message": ...}, ...]
        """
        sources = source_manager.get_enabled_sources()
        logger.info("开始健康检查，共 %d 个启用书源", len(sources))

        # 并发检查，限制并发数
        semaphore = asyncio.Semaphore(10)
        results: list[dict] = []

        async def _check_one(src):
            async with semaphore:
                res = await self.check_source(src)
                # 写入数据库
                add_health_record(
                    source_id=src.id,
                    source_name=src.bookSourceName,
                    status=res["status"],
                    latency_ms=res["latency_ms"],
                    message=res["message"],
                )
                return {
                    "id": src.id,
                    "bookSourceName": src.bookSourceName,
                    "status": res["status"],
                    "latency_ms": res["latency_ms"],
                    "message": res["message"],
                    "last_check": datetime.now(timezone.utc).isoformat(),
                }

        tasks = [_check_one(src) for src in sources]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        logger.info("健康检查完成")
        return results

    def start_periodic(self) -> None:
        """启动定时健康检查任务。"""
        if self._task and not self._task.done():
            return

        async def _run():
            while True:
                try:
                    await self.check_all()
                except Exception as e:  # noqa: BLE001
                    logger.error("定时健康检查异常: %s", e)
                interval = self.settings.HEALTH_CHECK_INTERVAL * 60
                await asyncio.sleep(interval)

        self._task = asyncio.create_task(_run())
        logger.info(
            "定时健康检查已启动，间隔 %d 分钟", self.settings.HEALTH_CHECK_INTERVAL
        )

    def stop_periodic(self) -> None:
        """停止定时任务。"""
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
            logger.info("定时健康检查已停止")


# 全局单例
health_checker = HealthChecker()
