"""Reading-app access user management routes."""

from fastapi import APIRouter, Depends, Request

from app.core.auth import get_current_user
from app.models.access_user import AccessUserCreate, AccessUserUpdate
from app.models.database import (
    add_log,
    create_access_user,
    delete_access_user,
    get_access_user,
    list_access_users,
    rotate_access_user_key,
    update_access_user,
)
from app.models.responses import error, success

router = APIRouter(prefix="/api/admin/users", tags=["users"])


def _get_client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("")
async def list_users(_user=Depends(get_current_user)):
    """List reading-app access users."""
    return success(data=list_access_users())


@router.post("")
async def create_user(
    req: AccessUserCreate,
    request: Request,
    _user=Depends(get_current_user),
):
    """Create a reading-app access user."""
    user = create_access_user(req.name, req.note)
    add_log("user_create", user["name"], "新增访问用户", _get_client_ip(request))
    return success(data=user, message="访问用户创建成功")


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    req: AccessUserUpdate,
    request: Request,
    _user=Depends(get_current_user),
):
    """Update access user profile or enabled state."""
    existing = get_access_user(user_id)
    if not existing:
        return error("NOT_FOUND", "访问用户不存在")

    user = update_access_user(
        user_id,
        name=req.name,
        note=req.note,
        enabled=req.enabled,
    )
    action = "更新访问用户"
    if req.enabled is not None and req.enabled != existing["enabled"]:
        action = "启用访问用户" if req.enabled else "禁用访问用户"
    add_log("user_update", user["name"], action, _get_client_ip(request))
    return success(data=user, message="访问用户更新成功")


@router.post("/{user_id}/rotate-key")
async def rotate_user_key(
    user_id: str,
    request: Request,
    _user=Depends(get_current_user),
):
    """Rotate one user's access key."""
    user = rotate_access_user_key(user_id)
    if not user:
        return error("NOT_FOUND", "访问用户不存在")
    add_log("user_rotate_key", user["name"], "重置访问口令", _get_client_ip(request))
    return success(data=user, message="访问口令已重置")


@router.delete("/{user_id}")
async def remove_user(
    user_id: str,
    request: Request,
    _user=Depends(get_current_user),
):
    """Delete an access user."""
    user = get_access_user(user_id)
    if not user:
        return error("NOT_FOUND", "访问用户不存在")
    delete_access_user(user_id)
    add_log("user_delete", user["name"], "删除访问用户", _get_client_ip(request))
    return success(message="访问用户已删除")
