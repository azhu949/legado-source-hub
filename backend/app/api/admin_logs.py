"""操作日志 & 统计路由。"""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.auth import get_current_user
from app.core.cache import cache
from app.core.source_manager import source_manager
from app.models.database import get_recent_logs, query_logs
from app.models.responses import success, paginate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["logs-stats"])


# ---------------- 统计 ----------------


@router.get("/stats")
async def get_stats(_user=Depends(get_current_user)):
    """仪表盘统计数据。"""
    sources = source_manager.get_all_sources()
    total = len(sources)
    enabled = sum(1 for s in sources if s.enabled)
    disabled = total - enabled

    overview = get_recent_health_overview()
    today_search = await cache.get_today_search_count()

    return success(
        data={
            "totalSources": total,
            "enabledSources": enabled,
            "disabledSources": disabled,
            "todaySearchCount": today_search,
            "unhealthySources": overview.get("unhealthy", 0),
            "avgLatencyMs": overview.get("avg_latency_ms", 0),
            "lastCheck": overview.get("last_check"),
        }
    )


def get_recent_health_overview() -> dict:
    """获取健康概览（避免循环依赖）。"""
    from app.models.database import get_health_overview

    return get_health_overview()


# ---------------- 日志 ----------------


@router.get("/logs")
async def get_logs(
    type: Optional[str] = Query(None, description="操作类型"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    _user=Depends(get_current_user),
):
    """操作日志列表。"""
    result = query_logs(
        op_type=type, start=start, end=end, page=page, page_size=pageSize
    )
    return paginate(result["items"], result["total"], result["page"], result["pageSize"])


@router.get("/logs/export")
async def export_logs(
    type: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    _user=Depends(get_current_user),
):
    """导出操作日志为 CSV。"""
    result = query_logs(
        op_type=type, start=start, end=end, page=1, page_size=100000
    )

    output = io.StringIO()
    output.write("\ufeff")  # BOM for Excel
    writer = csv.writer(output)
    writer.writerow(["时间", "操作类型", "目标书源", "详情", "IP", "操作人"])
    for row in result["items"]:
        writer.writerow(
            [
                row.get("timestamp", ""),
                row.get("op_type", ""),
                row.get("target_source", ""),
                row.get("detail", ""),
                row.get("ip", ""),
                row.get("operator", ""),
            ]
        )

    output.seek(0)
    filename = f"logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/recent-logs")
async def get_recent_logs_api(
    limit: int = Query(20, ge=1, le=100),
    _user=Depends(get_current_user),
):
    """最近操作日志（仪表盘用）。"""
    logs = get_recent_logs(limit)
    return success(data=logs)
