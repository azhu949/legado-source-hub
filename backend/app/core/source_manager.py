"""书源管理器：负责书源 JSON 文件的加载、增删改查与热重载。"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.config import get_settings
from app.core.legado import normalize_rule_aliases, parse_headers
from app.models.source import BookSource

logger = logging.getLogger(__name__)
_SYSTEM_FIELDS = {"id", "createdAt", "updatedAt"}


class SourceManager:
    """书源文件管理器（单例）。"""

    _instance: Optional["SourceManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.settings = get_settings()
            self._cache: dict[str, BookSource] = {}  # id -> BookSource
            self._loaded = False
            self._initialized = True

    # ---------------- 加载 ----------------

    def load_all(self, force: bool = False) -> dict[str, BookSource]:
        """加载所有书源到内存缓存。"""
        if self._loaded and not force:
            return self._cache

        self._cache.clear()
        sources_dir: Path = self.settings.SOURCES_DIR
        for path in sources_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                source = BookSource(**data)
                self._cache[source.id] = source
            except Exception as e:  # noqa: BLE001
                logger.warning("加载书源文件失败 %s: %s", path, e)
        self._loaded = True
        logger.info("已加载 %d 个书源", len(self._cache))
        return self._cache

    def reload(self) -> dict[str, BookSource]:
        """热重载。"""
        return self.load_all(force=True)

    # ---------------- 查询 ----------------

    def list_sources(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询书源列表（分页 + 过滤）。"""
        if not self._loaded:
            self.load_all()

        sources = list(self._cache.values())

        # 过滤
        if search:
            kw = search.lower()
            sources = [
                s for s in sources
                if kw in s.bookSourceName.lower() or kw in s.bookSourceUrl.lower()
            ]
        if status == "enabled":
            sources = [s for s in sources if s.enabled]
        elif status == "disabled":
            sources = [s for s in sources if not s.enabled]

        # 排序：权重降序、名称升序
        sources.sort(key=lambda s: (-s.weight, s.bookSourceName))

        total = len(sources)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = sources[start:end]

        return {
            "items": [s.model_dump() for s in page_items],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def get_source(self, source_id: str) -> Optional[BookSource]:
        """获取单个书源。"""
        if not self._loaded:
            self.load_all()
        return self._cache.get(source_id)

    def get_enabled_sources(self) -> list[BookSource]:
        """获取所有启用的书源。"""
        if not self._loaded:
            self.load_all()
        return [s for s in self._cache.values() if s.enabled]

    def get_all_sources(self) -> list[BookSource]:
        """获取所有书源。"""
        if not self._loaded:
            self.load_all()
        return list(self._cache.values())

    # ---------------- 写操作 ----------------

    def create_source(self, data: dict) -> BookSource:
        """新增书源。"""
        if not self._loaded:
            self.load_all()
        data = self._strip_system_fields(data)
        source = BookSource(**data)
        self._save_to_file(source)
        self._cache[source.id] = source
        logger.info("新增书源: %s (%s)", source.bookSourceName, source.id)
        return source

    def update_source(self, source_id: str, data: dict) -> Optional[BookSource]:
        """更新书源。"""
        if not self._loaded:
            self.load_all()
        existing = self._cache.get(source_id)
        if not existing:
            return None

        merged = existing.model_dump()
        merged.update(data)

        # 保留系统字段
        merged["id"] = source_id
        merged["createdAt"] = existing.createdAt
        merged["updatedAt"] = datetime.now(timezone.utc).isoformat()

        source = BookSource(**merged)
        self._save_to_file(source)
        self._cache[source.id] = source
        logger.info("更新书源: %s (%s)", source.bookSourceName, source.id)
        return source

    def delete_source(self, source_id: str) -> bool:
        """删除书源。"""
        if not self._loaded:
            self.load_all()
        if source_id not in self._cache:
            return False
        path = self._source_file_path(source_id)
        if path.exists():
            path.unlink()
        name = self._cache[source_id].bookSourceName
        del self._cache[source_id]
        logger.info("删除书源: %s (%s)", name, source_id)
        return True

    def toggle_source(self, source_id: str, enabled: bool) -> Optional[BookSource]:
        """启用/禁用书源。"""
        if not self._loaded:
            self.load_all()
        existing = self._cache.get(source_id)
        if not existing:
            return None
        existing.enabled = enabled
        existing.updatedAt = datetime.now(timezone.utc).isoformat()
        self._save_to_file(existing)
        return existing

    # ---------------- 导入/导出 ----------------

    def import_sources(
        self, raw_list: list[dict], conflict_strategy: str = "skip"
    ) -> dict:
        """批量导入书源。

        Args:
            raw_list: 书源原始字典列表。
            conflict_strategy: skip(跳过同名) / overwrite(覆盖同名) / new(始终新建)

        Returns:
            {"success": int, "skipped": int, "failed": int, "errors": [...]}
        """
        if not self._loaded:
            self.load_all()

        success = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        for idx, raw in enumerate(raw_list):
            try:
                # 标准化字段名：兼容不同来源的书源 JSON
                normalized = self._normalize_import(raw)
                name = normalized.get("bookSourceName", "")

                # 冲突检测（按名称）
                existing = self._find_by_name(name) if name else None

                if existing and conflict_strategy == "skip":
                    skipped += 1
                    continue
                elif existing and conflict_strategy == "overwrite":
                    self.update_source(existing.id, normalized)
                    success += 1
                    continue
                # new 或无冲突：新建
                if "id" in normalized:
                    normalized.pop("id")  # 让系统生成新 id
                self.create_source(normalized)
                success += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f"第 {idx + 1} 条导入失败: {e}")
                logger.warning("导入书源失败 idx=%d err=%s", idx, e)

        return {"success": success, "skipped": skipped, "failed": failed, "errors": errors}

    def export_sources(self) -> list[dict]:
        """导出全部书源。"""
        if not self._loaded:
            self.load_all()
        return [s.model_dump() for s in self._cache.values()]

    # ---------------- 内部方法 ----------------

    def _save_to_file(self, source: BookSource) -> None:
        """将书源保存为 JSON 文件。"""
        path = self._source_file_path(source.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(source.model_dump(), f, ensure_ascii=False, indent=2)

    def _source_file_path(self, source_id: str) -> Path:
        """Return a storage path guaranteed to stay inside SOURCES_DIR."""
        filename = f"{source_id}.json"
        path = self.settings.SOURCES_DIR / filename
        base = self.settings.SOURCES_DIR.resolve()
        resolved = path.resolve()
        if Path(filename).name != filename or resolved.parent != base:
            raise ValueError("非法书源ID")
        return path

    def _strip_system_fields(self, data: dict) -> dict:
        """Drop fields owned by storage rather than user-provided source config."""
        return {key: value for key, value in dict(data).items() if key not in _SYSTEM_FIELDS}

    def _find_by_name(self, name: str) -> Optional[BookSource]:
        """按名称查找书源。"""
        for s in self._cache.values():
            if s.bookSourceName == name:
                return s
        return None

    def _normalize_import(self, raw: dict) -> dict:
        """标准化导入的书源数据，补全缺失字段。"""
        # 确保必要字段存在
        if not raw.get("bookSourceName"):
            raise ValueError("书源名称不能为空")
        if not raw.get("bookSourceUrl"):
            raise ValueError("书源URL不能为空")

        normalized = dict(raw)
        normalized.update(
            {
                "bookSourceName": str(raw.get("bookSourceName", "")).strip(),
                "bookSourceGroup": raw.get("bookSourceGroup", "未分组") or "未分组",
                "bookSourceUrl": str(raw.get("bookSourceUrl", "")).strip(),
                "enabled": raw.get("enabled", True) if isinstance(raw.get("enabled"), bool) else True,
                "weight": int(raw.get("weight", 100) or 100),
                "searchUrl": raw.get("searchUrl", ""),
                "ruleSearch": normalize_rule_aliases(raw.get("ruleSearch") or {}),
                "ruleBookInfo": raw.get("ruleBookInfo") or {},
                "ruleToc": raw.get("ruleToc") or {},
                "ruleContent": raw.get("ruleContent") or {},
                "ruleExplore": normalize_rule_aliases(raw.get("ruleExplore") or {}),
                "headers": parse_headers(raw.get("headers") if "headers" in raw else raw.get("header")),
            }
        )
        return normalized


# 全局单例
source_manager = SourceManager()
