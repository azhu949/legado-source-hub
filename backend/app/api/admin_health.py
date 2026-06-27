"""健康检查 & 统计路由。"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth import get_current_user
from app.core.health_checker import health_checker
from app.models.database import (
    get_health_overview,
    get_health_trend,
    query_health_records,
)
from app.models.responses import success, paginate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/health", tags=["health"])


@router.get("/overview")
async def health_overview(_user=Depends(get_current_user)):
    """健康概览。"""
    overview = get_health_overview()
    return success(data=overview)


@router.get("/records")
async def health_records(
    sourceId: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    _user=Depends(get_current_user),
):
    """健康检查记录列表。"""
    result = query_health_records(source_id=sourceId, page=page, page_size=pageSize)
    return paginate(result["items"], result["total"], result["page"], result["pageSize"])


@router.get("/trend")
async def health_trend(_user=Depends(get_current_user)):
    """近 24 小时延迟趋势数据。"""
    trend = get_health_trend()
    return success(data=trend)


@router.post("/check-now")
async def check_now(_user=Depends(get_current_user)):
    """手动触发一次全量健康检查。"""
    results = await health_checker.check_all()
    return success(data=results, message=f"健康检查完成，共检查 {len(results)} 个书源")
