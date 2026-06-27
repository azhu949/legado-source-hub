"""统一响应模型。"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应结构。"""

    success: bool = True
    data: Optional[T] = None
    message: str = "ok"


class ErrorResponse(BaseModel):
    """错误响应结构。"""

    success: bool = False
    error: dict


class PaginatedData(BaseModel, Generic[T]):
    """分页数据结构。"""

    items: list[T]
    total: int
    page: int
    pageSize: int


def success(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应。"""
    return {"success": True, "data": data, "message": message}


def error(code: str, message: str) -> dict:
    """构造错误响应。"""
    return {"success": False, "error": {"code": code, "message": message}}


def paginate(items: list, total: int, page: int, page_size: int) -> dict:
    """构造分页响应。"""
    return {
        "success": True,
        "data": {"items": items, "total": total, "page": page, "pageSize": page_size},
    }
