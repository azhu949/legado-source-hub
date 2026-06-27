"""HTTP 客户端封装：基于 aiohttp，支持移动端 UA、超时重试、编码处理、Cookie 持久化。"""

import asyncio
import logging
import ssl
from typing import Any, Optional
from urllib.parse import urlparse

import aiohttp

from app.config import get_settings

logger = logging.getLogger(__name__)


class HttpClient:
    """异步 HTTP 客户端单例。"""

    _instance: Optional["HttpClient"] = None
    _session: Optional[aiohttp.ClientSession] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.settings = get_settings()
        if not hasattr(self, "_tls12_compat"):
            self._tls12_compat = False

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取/创建 aiohttp 会话。"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.settings.HTTP_TIMEOUT)
            connector = self._create_connector()
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={"User-Agent": self.settings.HTTP_USER_AGENT},
                trust_env=True,
            )
        return self._session

    def _create_connector(self) -> aiohttp.TCPConnector:
        if not self._tls12_compat:
            return aiohttp.TCPConnector(limit=100, limit_per_host=20, ssl=False)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        return aiohttp.TCPConnector(limit=100, limit_per_host=20, ssl=context)

    async def _enable_tls12_compat(self) -> bool:
        if self._tls12_compat:
            return False
        self._tls12_compat = True
        await self.close()
        logger.info("HTTP 客户端已切换到 TLS 1.2 兼容模式")
        return True

    async def close(self) -> None:
        """关闭会话。"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def clear_cookies_for_url(self, url: str) -> None:
        """清理指定站点的 Cookie，用于兼容 Legado 的 cookie.removeCookie。"""
        if self._session is None or self._session.closed:
            return

        host = urlparse(url).hostname
        if not host:
            return

        jar = self._session.cookie_jar
        if hasattr(jar, "clear_domain"):
            jar.clear_domain(host)
            return

        jar.clear(lambda morsel: morsel["domain"] == host or morsel["domain"].endswith(f".{host}"))

    async def get_domain_cookie_header(self, url: str) -> str:
        """获取同域 Cookie 字符串，忽略 Path 以兼容部分 Legado 源。"""
        if self._session is None or self._session.closed:
            return ""

        session = self._session
        host = urlparse(url).hostname
        if not host:
            return ""

        cookies: list[str] = []
        for morsel in session.cookie_jar:
            domain = str(morsel["domain"] or host).lstrip(".")
            if host == domain or host.endswith(f".{domain}"):
                cookies.append(f"{morsel.key}={morsel.value}")
        return "; ".join(cookies)

    async def get(
        self,
        url: str,
        headers: Optional[dict] = None,
        retries: Optional[int] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """发起 GET 请求。

        Returns:
            {"status": int, "headers": dict, "body": str, "elapsed_ms": int, "url": str}
        """
        return await self._request("GET", url, headers=headers, retries=retries, **kwargs)

    async def post(
        self,
        url: str,
        headers: Optional[dict] = None,
        data: Any = None,
        json_data: Any = None,
        retries: Optional[int] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """发起 POST 请求。"""
        return await self._request(
            "POST",
            url,
            headers=headers,
            data=data,
            json_data=json_data,
            retries=retries,
            **kwargs,
        )

    async def _request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        data: Any = None,
        json_data: Any = None,
        retries: Optional[int] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """统一请求处理（含重试）。"""
        max_retries = retries if retries is not None else self.settings.HTTP_RETRIES
        last_error: Optional[Exception] = None

        merged_headers = {}
        if headers:
            merged_headers.update(headers)

        attempt = 0
        while attempt <= max_retries:
            session = await self._get_session()
            import time

            start = time.monotonic()
            try:
                async with session.request(
                    method,
                    url,
                    headers=merged_headers or None,
                    data=data,
                    json=json_data,
                    allow_redirects=True,
                    **kwargs,
                ) as resp:
                    raw = await resp.read()
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    body = self._decode_body(raw, resp)
                    return {
                        "status": resp.status,
                        "headers": dict(resp.headers),
                        "body": body,
                        "elapsed_ms": elapsed_ms,
                        "url": str(resp.url),
                    }
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                elapsed_ms = int((time.monotonic() - start) * 1000)
                if self._should_retry_with_tls12(e) and await self._enable_tls12_compat():
                    continue

                logger.warning(
                    "HTTP 请求失败 attempt=%d/%d url=%s err=%s",
                    attempt + 1,
                    max_retries + 1,
                    url,
                    e,
                )
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                attempt += 1
                continue

        # 全部重试失败
        return {
            "status": 0,
            "headers": {},
            "body": "",
            "elapsed_ms": 0,
            "url": url,
            "error": str(last_error) if last_error else "unknown error",
        }

    @staticmethod
    def _should_retry_with_tls12(error: Exception) -> bool:
        message = str(error).lower()
        return "sslv3_alert_bad_record_mac" in message or "bad record mac" in message

    @staticmethod
    def _decode_body(raw: bytes, resp: aiohttp.ClientResponse) -> str:
        """解码响应体，处理编码。"""
        if not raw:
            return ""
        head = raw[:4096].decode("ascii", errors="ignore")
        import re

        meta_match = re.search(r'charset\s*=\s*["\']?([\w-]+)', head, re.IGNORECASE)
        candidates = [
            resp.charset,
            meta_match.group(1) if meta_match else None,
            "utf-8",
            "gb18030",
            "big5",
        ]

        best_text = ""
        best_score: int | None = None
        seen: set[str] = set()

        for charset in candidates:
            if not charset:
                continue
            charset = str(charset).strip().lower()
            if not charset or charset in seen:
                continue
            seen.add(charset)
            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                pass
            else:
                score = text.count("\ufffd")
                if best_score is None or score < best_score:
                    best_text = text
                    best_score = score
                    if score == 0:
                        return text

        return best_text or raw.decode("utf-8", errors="replace")


# 全局单例
http_client = HttpClient()
