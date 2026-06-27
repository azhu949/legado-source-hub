"""Public URL helpers used by generated Legado sources and public APIs."""

import os
from urllib.parse import urlparse

from fastapi import Request

from app.config import get_settings


def strip_public_url(value: str | None) -> str:
    """Normalize an externally visible origin."""
    url = (value or "").strip().rstrip("/")
    if url and "://" not in url:
        url = f"http://{url}"
    return url


def is_loopback_url(value: str) -> bool:
    """Return true when a configured URL is only useful from the local machine/container."""
    hostname = (urlparse(value).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def public_origin_from_request(request: Request) -> str:
    """Infer the external origin from proxy-aware request headers."""
    settings = get_settings()
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    proto = proto.split(",", 1)[0].strip() or "http"
    host = (host or request.url.netloc).split(",", 1)[0].strip()
    if not host:
        return f"http://{settings.HOST}:{settings.PORT}"
    return f"{proto}://{host}".rstrip("/")


def get_public_origin(request: Request) -> str:
    """Use PUBLIC_URL when it is public; otherwise derive the origin from the request."""
    configured = strip_public_url(os.environ.get("PUBLIC_URL") or os.environ.get("BOOK_SOURCE_URL"))
    if configured and not is_loopback_url(configured):
        return configured
    return public_origin_from_request(request)
