"""Access-key protection for public reading-app APIs."""

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import decode_token, security
from app.models.database import (
    get_enabled_access_user_by_key,
    record_access_user_usage,
)

PUBLIC_ACCESS_PARAM = "accessKey"
PUBLIC_ACCESS_HEADER = "X-Aggregate-Key"


def public_access_enabled() -> bool:
    return True


def _request_access_key(request: Request) -> str:
    return (
        request.query_params.get(PUBLIC_ACCESS_PARAM)
        or request.headers.get(PUBLIC_ACCESS_HEADER)
        or ""
    ).strip()


def _validate_access_key(value: str, record_usage: bool = False) -> str:
    user = get_enabled_access_user_by_key(value)
    if user:
        if record_usage:
            record_access_user_usage(value)
        return value
    return ""


async def require_public_access(request: Request) -> str:
    """Require a valid enabled-user access key for public reading endpoints."""
    value = _request_access_key(request)
    access_key = _validate_access_key(value, record_usage=True)
    if access_key:
        return access_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="聚合访问口令无效或缺失",
    )


async def public_access_for_source_export(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Allow source export by a valid user key or admin bearer token.

    Admin access without an accessKey is allowed for previewing the source JSON,
    but per-user import URLs should include accessKey so downstream calls work.
    """
    request_key = _request_access_key(request)
    valid_key = _validate_access_key(request_key, record_usage=True)
    if valid_key:
        return valid_key

    if credentials and credentials.scheme.lower() == "bearer":
        payload = decode_token(credentials.credentials)
        if payload and payload.get("sub"):
            return ""

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="聚合访问口令无效或缺失",
    )


def with_public_access_key(url: str, access_key: str = "") -> str:
    """Append or replace the public access key query parameter on a URL."""
    if not access_key:
        return url
    return with_query_params(url, {PUBLIC_ACCESS_PARAM: access_key})


def with_query_params(url: str, params: dict[str, str]) -> str:
    additions = {key: value for key, value in params.items() if value}
    if not additions:
        return url

    parsed = urlparse(url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in additions
    ]
    query_items.extend(additions.items())
    return urlunparse(parsed._replace(query=urlencode(query_items)))
