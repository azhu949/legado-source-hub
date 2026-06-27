"""Redis 缓存层：降低重复请求，提升响应速度。"""

import json
import logging
from typing import Any, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class Cache:
    """Redis 缓存封装，支持降级（Redis 不可用时跳过缓存）。"""

    _instance: Optional["Cache"] = None
    _redis = None
    _available: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.settings = get_settings()
            self._initialized = False

    async def connect(self) -> None:
        """初始化 Redis 连接。"""
        if self._initialized:
            return
        self._initialized = True
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self.settings.REDIS_URL, decode_responses=True
            )
            await self._redis.ping()
            self._available = True
            logger.info("Redis 缓存层已连接")
        except Exception as e:  # noqa: BLE001
            logger.warning("Redis 连接失败，缓存层降级运行: %s", e)
            self._available = False
            self._redis = None

    async def close(self) -> None:
        """关闭连接。"""
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    async def get(self, key: str) -> Optional[Any]:
        """读取缓存。"""
        if not self.available or not self._redis:
            return None
        try:
            val = await self._redis.get(key)
            if val is None:
                return None
            return json.loads(val)
        except Exception as e:  # noqa: BLE001
            logger.debug("缓存读取失败 key=%s err=%s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """写入缓存。"""
        if not self.available or not self._redis:
            return
        try:
            await self._redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            logger.debug("缓存写入失败 key=%s err=%s", key, e)

    async def delete(self, key: str) -> None:
        """删除缓存。"""
        if not self.available or not self._redis:
            return
        try:
            await self._redis.delete(key)
        except Exception as e:  # noqa: BLE001
            logger.debug("缓存删除失败 key=%s err=%s", key, e)

    async def delete_pattern(self, pattern: str) -> None:
        """按模式删除缓存（书源更新时失效相关缓存）。"""
        if not self.available or not self._redis:
            return
        try:
            async for key in self._redis.scan_iter(match=pattern, count=100):
                await self._redis.delete(key)
        except Exception as e:  # noqa: BLE001
            logger.debug("缓存批量删除失败 pattern=%s err=%s", pattern, e)

    async def incr(self, key: str, ttl: int = 86400) -> int:
        """自增计数（用于搜索量统计）。"""
        if not self.available or not self._redis:
            return 0
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, ttl)
            return count
        except Exception as e:  # noqa: BLE001
            logger.debug("计数失败 key=%s err=%s", key, e)
            return 0

    # ---------------- 业务快捷方法 ----------------

    async def get_search(
        self,
        keyword: str,
        page: int,
        source_scope: str | None = None,
        merge: int = 0,
    ) -> Optional[list]:
        """获取搜索结果缓存。"""
        scope = source_scope or "all"
        return await self.get(f"search:{scope}:merge{merge}:{keyword}:{page}")

    async def set_search(
        self,
        keyword: str,
        page: int,
        results: list,
        source_scope: str | None = None,
        merge: int = 0,
    ) -> None:
        scope = source_scope or "all"
        await self.set(f"search:{scope}:merge{merge}:{keyword}:{page}", results, self.settings.CACHE_TTL_SEARCH)

    async def get_book(self, url_hash: str) -> Optional[dict]:
        return await self.get(f"book:{url_hash}")

    async def set_book(self, url_hash: str, book: dict) -> None:
        await self.set(f"book:{url_hash}", book, self.settings.CACHE_TTL_BOOK)

    async def get_toc(self, url_hash: str) -> Optional[list]:
        return await self.get(f"toc:{url_hash}")

    async def set_toc(self, url_hash: str, chapters: list) -> None:
        await self.set(f"toc:{url_hash}", chapters, self.settings.CACHE_TTL_TOC)

    async def get_today_search_count(self) -> int:
        """获取今日搜索量。"""
        if not self.available or not self._redis:
            return 0
        try:
            from datetime import datetime

            key = f"stats:search:{datetime.utcnow().strftime('%Y%m%d')}"
            val = await self._redis.get(key)
            return int(val) if val else 0
        except Exception:  # noqa: BLE001
            return 0

    async def incr_search_count(self) -> None:
        """增加搜索计数。"""
        from datetime import datetime

        key = f"stats:search:{datetime.utcnow().strftime('%Y%m%d')}"
        await self.incr(key)


# 全局单例
cache = Cache()
