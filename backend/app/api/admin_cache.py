"""缓存管理路由。"""

from fastapi import APIRouter, Depends, Request

from app.core.auth import get_current_user
from app.core.cache import cache
from app.models.database import add_log
from app.models.responses import success

router = APIRouter(prefix="/api/admin/cache", tags=["cache"])

_CACHE_GROUPS = (
    {"key": "search", "label": "搜索缓存", "pattern": "search:*"},
    {"key": "book", "label": "详情缓存", "pattern": "book:*"},
    {"key": "toc", "label": "目录缓存", "pattern": "toc:*"},
)


def _get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _cache_group_counts() -> list[dict]:
    groups = []
    for group in _CACHE_GROUPS:
        count = await cache.count_pattern(group["pattern"])
        groups.append({**group, "count": count})
    return groups


@router.get("")
async def get_cache_status(_user=Depends(get_current_user)):
    """获取缓存状态与各类缓存数量。"""
    groups = await _cache_group_counts()
    return success(
        data={
            "available": cache.available,
            "total": sum(group["count"] for group in groups),
            "groups": groups,
        }
    )


@router.post("/clear")
async def clear_all_cache(request: Request, user=Depends(get_current_user)):
    """清除全部业务缓存。"""
    cleared_groups = []
    for group in _CACHE_GROUPS:
        cleared = await cache.delete_pattern(group["pattern"])
        cleared_groups.append({**group, "cleared": cleared})

    total = sum(group["cleared"] for group in cleared_groups)
    username = str((user or {}).get("username") or "admin")
    detail = "清除全部缓存：" + "，".join(
        f"{group['label']} {group['cleared']} 条" for group in cleared_groups
    )
    add_log("cache", None, detail, _get_client_ip(request), username)

    return success(
        data={
            "available": cache.available,
            "totalCleared": total,
            "groups": cleared_groups,
        },
        message="缓存已清除",
    )
