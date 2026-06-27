"""书源管理 CRUD 路由。"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from app.core.auth import get_current_user
from app.core.cache import cache
from app.core.source_manager import source_manager
from app.models.database import add_log
from app.models.responses import success, error, paginate
from app.models.source import (
    BookSourceCreate,
    BookSourceUpdate,
    ImportSourceRequest,
    ImportUrlRequest,
    ToggleSourceRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/sources", tags=["sources"])


def _get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("")
async def list_sources(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    _user=Depends(get_current_user),
):
    """书源列表（分页 + 过滤）。"""
    result = source_manager.list_sources(
        search=search, status=status, page=page, page_size=pageSize
    )
    return paginate(result["items"], result["total"], result["page"], result["pageSize"])


@router.get("/export")
async def export_sources(_user=Depends(get_current_user)):
    """导出全部书源为 JSON。"""
    data = source_manager.export_sources()
    return success(data=data)


@router.get("/{source_id}")
async def get_source(source_id: str, _user=Depends(get_current_user)):
    """书源详情。"""
    source = source_manager.get_source(source_id)
    if not source:
        return error("NOT_FOUND", "书源不存在")
    return success(data=source.model_dump())


@router.post("")
async def create_source(
    req: BookSourceCreate,
    request: Request,
    _user=Depends(get_current_user),
):
    """新增书源。"""
    source = source_manager.create_source(req.model_dump())
    add_log("create", source.bookSourceName, f"新增书源 {source.bookSourceUrl}", _get_client_ip(request))
    # 失效缓存
    await cache.delete_pattern("search:*")
    return success(data=source.model_dump(), message="书源创建成功")


@router.put("/{source_id}")
async def update_source(
    source_id: str,
    req: BookSourceUpdate,
    request: Request,
    _user=Depends(get_current_user),
):
    """更新书源。"""
    source = source_manager.update_source(source_id, req.model_dump())
    if not source:
        return error("NOT_FOUND", "书源不存在")
    add_log("update", source.bookSourceName, f"更新书源配置", _get_client_ip(request))
    await cache.delete_pattern("search:*")
    await cache.delete_pattern("book:*")
    await cache.delete_pattern("toc:*")
    return success(data=source.model_dump(), message="书源更新成功")


@router.delete("/{source_id}")
async def delete_source(
    source_id: str, request: Request, _user=Depends(get_current_user)
):
    """删除书源。"""
    source = source_manager.get_source(source_id)
    if not source:
        return error("NOT_FOUND", "书源不存在")
    name = source.bookSourceName
    source_manager.delete_source(source_id)
    add_log("delete", name, f"删除书源 {name}", _get_client_ip(request))
    await cache.delete_pattern("search:*")
    await cache.delete_pattern("book:*")
    await cache.delete_pattern("toc:*")
    return success(message="书源删除成功")


@router.patch("/{source_id}/toggle")
async def toggle_source(
    source_id: str,
    req: ToggleSourceRequest,
    request: Request,
    _user=Depends(get_current_user),
):
    """启用/禁用书源。"""
    source = source_manager.toggle_source(source_id, req.enabled)
    if not source:
        return error("NOT_FOUND", "书源不存在")
    action = "启用" if req.enabled else "禁用"
    add_log("toggle", source.bookSourceName, f"{action}书源", _get_client_ip(request))
    await cache.delete_pattern("search:*")
    return success(data=source.model_dump(), message=f"已{action}书源")


@router.post("/import")
async def import_sources(
    req: ImportSourceRequest,
    request: Request,
    _user=Depends(get_current_user),
):
    """批量导入书源。"""
    result = source_manager.import_sources(req.sources, req.conflictStrategy)
    add_log(
        "import",
        None,
        f"批量导入: 成功{result['success']} 跳过{result['skipped']} 失败{result['failed']}",
        _get_client_ip(request),
    )
    await cache.delete_pattern("search:*")
    return success(data=result, message="导入完成")


@router.post("/import-url")
async def import_from_url(
    req: ImportUrlRequest,
    request: Request,
    _user=Depends(get_current_user),
):
    """从远程 URL 导入书源。"""
    from app.core.http_client import http_client

    resp = await http_client.get(req.url)
    if resp["status"] != 200 or not resp["body"]:
        return error("FETCH_FAILED", f"远程地址获取失败: HTTP {resp['status']}")

    import json

    try:
        data = json.loads(resp["body"])
    except json.JSONDecodeError:
        return error("PARSE_ERROR", "远程内容不是有效的 JSON")

    raw_list = data if isinstance(data, list) else [data]
    result = source_manager.import_sources(raw_list, req.conflictStrategy)
    add_log(
        "import",
        None,
        f"URL导入: 成功{result['success']} 跳过{result['skipped']} 失败{result['failed']}",
        _get_client_ip(request),
    )
    await cache.delete_pattern("search:*")
    return success(data=result, message="导入完成")
