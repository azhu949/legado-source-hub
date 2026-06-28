"""Legado compatibility helpers.

This module is the boundary for Reading/Legado-specific behavior.  The long
term goal is to grow this into a real Legado runtime instead of scattering
small compatibility branches through API handlers.
"""

from __future__ import annotations

import json
import logging
import re
from base64 import b64encode
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urljoin

logger = logging.getLogger(__name__)


@dataclass
class LegadoRequest:
    """HTTP request generated from a Legado URL rule."""

    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    retry: int | None = None
    options: dict[str, Any] = field(default_factory=dict)


def parse_headers(value: Any) -> dict[str, str] | None:
    """Normalize Legado ``header`` / local ``headers`` values."""
    if not value:
        return None
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items() if v is not None}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if v is not None}
    return None


def normalize_rule_aliases(rules: Any) -> Any:
    """Map common Legado rule field names onto the internal schema."""
    if not isinstance(rules, dict):
        return rules

    normalized = dict(rules)
    if "noteUrl" not in normalized and "bookUrl" in normalized:
        normalized["noteUrl"] = normalized["bookUrl"]
    return normalized


def normalize_source_dict(data: Any) -> Any:
    """Normalize imported or posted Legado source dictionaries."""
    if not isinstance(data, dict):
        return data

    normalized = dict(data)
    header_value = normalized.get("headers", normalized.get("header"))
    headers = parse_headers(header_value)
    if headers:
        normalized["headers"] = headers

    if "ruleSearch" in normalized:
        normalized["ruleSearch"] = _normalize_rule_object(normalized["ruleSearch"])
    if "ruleBookInfo" in normalized:
        normalized["ruleBookInfo"] = _normalize_rule_object(normalized["ruleBookInfo"])
    if "ruleToc" in normalized:
        normalized["ruleToc"] = _normalize_rule_object(normalized["ruleToc"])
    if "ruleContent" in normalized:
        normalized["ruleContent"] = _normalize_rule_object(normalized["ruleContent"])
    if "ruleExplore" in normalized:
        normalized["ruleExplore"] = _normalize_rule_object(normalized["ruleExplore"])

    return normalized


def _normalize_rule_object(rules: Any) -> Any:
    """Treat empty Legado rule arrays as blank rule objects."""
    if rules == []:
        return {}
    return normalize_rule_aliases(rules)


def build_template_url(template: str, keyword: str, page: int = 1, source_key: str = "") -> str:
    """Build a URL from simple Legado placeholders."""
    if not template:
        return ""

    context = {
        "key": keyword,
        "keyword": keyword,
        "page": str(page),
        "source.key": source_key,
        "source.getKey()": source_key,
    }

    def replace_double_braces(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        return _eval_template_expr(expr, context)

    url = re.sub(r"\{\{([^{}]+)\}\}", replace_double_braces, template)

    replacements = {
        "{{key}}": keyword,
        "{{keyword}}": keyword,
        "{key}": keyword,
        "{keyword}": keyword,
        "{{page}}": str(page),
        "{page}": str(page),
    }
    for needle, replacement in replacements.items():
        url = url.replace(needle, replacement)
    return url


def parse_request_spec(spec: str, base_url: str = "") -> LegadoRequest | None:
    """Parse ``url`` or ``url,{...request options...}`` style Legado specs."""
    if not spec:
        return None

    text = spec.strip()
    url_part = text
    options: dict[str, Any] = {}

    comma_index = _find_request_options_comma(text)
    if comma_index >= 0:
        url_part = text[:comma_index].strip()
        raw_options = text[comma_index + 1 :].strip()
        try:
            parsed = json.loads(raw_options)
            if isinstance(parsed, dict):
                options = parsed
        except json.JSONDecodeError:
            options = {}

    url = _absolute_url(base_url, url_part)
    if not url:
        return None

    options = _render_request_options(options, context={"key": "", "keyword": "", "page": ""})
    method = str(options.get("method", "GET")).upper()
    headers = parse_headers(options.get("headers") or options.get("header")) or {}
    body = options.get("body")
    if body is not None:
        body = _normalize_body(body)
    retry = _parse_int(options.get("retry"))

    request = LegadoRequest(url=url, method=method, headers=headers, body=body, retry=retry, options=options)
    _apply_request_option_js(request)
    return request


async def build_search_request(source: Any, keyword: str, page: int = 1) -> LegadoRequest | None:
    """Build a search request from a source's Legado ``searchUrl`` rule."""
    template = str(getattr(source, "searchUrl", "") or "").strip()
    base_url = str(getattr(source, "bookSourceUrl", "") or "").strip()
    if not template:
        return None

    if template.startswith("@js:"):
        return await _build_js_search_request(template[4:], source, keyword, page)

    spec = build_template_url(template, keyword, page, source_key=base_url)
    spec = _render_request_spec(spec, keyword, page, base_url)
    return parse_request_spec(spec, base_url=base_url)


async def execute_request(request: LegadoRequest, source_headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Execute a Legado request with the project HTTP client."""
    from app.core.http_client import http_client

    headers: dict[str, str] = {}
    if source_headers:
        headers.update(source_headers)
    headers.update(request.headers)

    if request.method == "POST":
        if request.body is not None and not _has_header(headers, "Content-Type"):
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        return await http_client.post(request.url, headers=headers, data=request.body, retries=request.retry)

    return await http_client.get(request.url, headers=headers, retries=request.retry)


def response_is_json(response: dict[str, Any]) -> bool:
    """Infer whether an HTTP response body should be parsed as JSON."""
    content_type = response.get("headers", {}).get("Content-Type", "")
    if "json" in str(content_type).lower():
        return True
    body = str(response.get("body", "") or "").lstrip()
    return body.startswith("{") or body.startswith("[")


def _render_request_spec(spec: str, keyword: str, page: int, source_key: str) -> str:
    context = {
        "key": keyword,
        "keyword": keyword,
        "page": str(page),
        "source.key": source_key,
        "source.getKey()": source_key,
    }
    return _render_text_templates(spec, context)


def _render_request_options(options: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
    rendered: dict[str, Any] = {}
    for key, value in options.items():
        if isinstance(value, str):
            rendered[key] = _render_text_templates(value, context)
        elif isinstance(value, dict):
            rendered[key] = {
                str(k): _render_text_templates(str(v), context) if isinstance(v, str) else v
                for k, v in value.items()
            }
        else:
            rendered[key] = value
    return rendered


def _render_text_templates(text: str, context: dict[str, str]) -> str:
    def replace_double_braces(match: re.Match[str]) -> str:
        return _eval_template_expr(match.group(1).strip(), context)

    text = re.sub(r"\{\{([^{}]+)\}\}", replace_double_braces, text)
    for key, value in context.items():
        if "." not in key and "(" not in key:
            text = text.replace("{" + key + "}", value)
    return text


def _eval_template_expr(expr: str, context: dict[str, str]) -> str:
    expr = expr.strip()
    if not expr:
        return ""
    if expr in context:
        return context[expr]
    if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
        return expr[1:-1]

    function_match = re.fullmatch(r"(?:java\.)?(base64Encode|encodeURI|encodeURIComponent)\((.*?)\)", expr)
    if function_match:
        fn = function_match.group(1)
        value = _eval_template_expr(function_match.group(2), context)
        if fn == "base64Encode":
            return b64encode(value.encode("utf-8")).decode("ascii")
        if fn == "encodeURI":
            return quote(value, safe="/?:@&=+$,#")
        return quote(value, safe="")

    # Small numeric expression support for common page arithmetic.
    if re.fullmatch(r"[\d\s+\-*/%().]+", expr.replace("page", str(context.get("page", "0")))):
        try:
            numeric_expr = expr.replace("page", str(context.get("page", "0")))
            value = eval(numeric_expr, {"__builtins__": {}}, {})  # noqa: S307 - limited numeric expression
            return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
        except Exception:
            return ""

    plus_parts = _split_js_concat(expr)
    if len(plus_parts) > 1:
        return "".join(_eval_template_expr(part, context) for part in plus_parts)

    return context.get(expr, "")


def _normalize_body(body: Any) -> Any:
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False)
    return str(body)


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _apply_request_option_js(request: LegadoRequest) -> None:
    script = request.options.get("js")
    if not isinstance(script, str) or not script.strip():
        return

    for match in re.finditer(
        r"(?:java\.)?headerMap\.put\(\s*([\"'])(.*?)\1\s*,\s*([\"'])(.*?)\3\s*\)",
        script,
        flags=re.S,
    ):
        request.headers[match.group(2)] = match.group(4)

    url_assignment = re.search(r"(?:java\.)?url\s*=\s*(.*?);", script, flags=re.S)
    if url_assignment:
        rendered = _eval_option_js_expr(url_assignment.group(1), request)
        if rendered:
            request.url = rendered

    body_assignment = re.search(r"(?:java\.)?body\s*=\s*(.*?);", script, flags=re.S)
    if body_assignment:
        request.body = _eval_option_js_expr(body_assignment.group(1), request)
        if request.method == "GET":
            request.method = "POST"

    method_assignment = re.search(r"(?:java\.)?method\s*=\s*([\"'])(.*?)\1", script, flags=re.S)
    if method_assignment:
        request.method = method_assignment.group(2).upper()


def _eval_option_js_expr(expr: str, request: LegadoRequest) -> str:
    parts = _split_js_concat(expr)
    rendered: list[str] = []
    for part in parts:
        token = part.strip()
        if token in {"java.url", "url"}:
            rendered.append(request.url)
        elif token in {"java.body", "body"}:
            rendered.append("" if request.body is None else str(request.body))
        elif len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'", "`"}:
            rendered.append(token[1:-1])
    return "".join(rendered)


async def _build_js_search_request(script: str, source: Any, keyword: str, page: int) -> LegadoRequest | None:
    """Execute a small, explicit subset of Legado searchUrl JavaScript.

    This intentionally handles the common anti-bot pattern used by sources that
    first call ``java.ajax(source.key + "/user/search.html?q=" + key)`` and
    then POST the extracted ``var name = "value";`` variables to an API.
    It is not a replacement for the full JS runtime; it is the first executable
    branch in that direction.
    """
    source_key = str(getattr(source, "bookSourceUrl", "") or "").rstrip("/")
    try:
        from app.core.legado_js import execute_search_script

        js_result = await execute_search_script(
            script,
            source_key=source_key,
            keyword=keyword,
            page=page,
            headers=getattr(source, "headers", None) or {},
        )
        if js_result:
            request = parse_request_spec(js_result, base_url=source_key)
            if request:
                await _apply_search_ajax_headers(request, source_key, keyword)
                return request
    except Exception as e:  # noqa: BLE001
        logger.debug("Legado JS runtime failed, falling back: %s", e)

    expression_request = await _build_js_expression_request(script, source_key, keyword, page)
    if expression_request:
        return expression_request

    context: dict[str, str] = {"key": keyword, "page": str(page)}

    ajax_body = ""
    ajax_expr = _find_call_argument(script, "java.ajax")
    if ajax_expr:
        ajax_url = _eval_string_expression(ajax_expr, context, source_key)
        if ajax_url:
            from app.core.http_client import http_client

            resp = await http_client.get(ajax_url, headers=getattr(source, "headers", None) or {})
            if resp.get("status") != 200 or not resp.get("body"):
                logger.debug(
                    "Legado JS fallback ajax failed url=%s status=%s err=%s",
                    ajax_url,
                    resp.get("status"),
                    resp.get("error"),
                )
                return None
            ajax_body = str(resp.get("body", "") or "")
            context.update(_extract_js_var_strings(ajax_body))

    context.update(_extract_js_var_strings(script))

    url = _extract_assigned_source_url(script, "url", source_key)
    if not url:
        return None

    body_template = _extract_template_property(script, "body")
    body = _render_template_literal(body_template, context) if body_template is not None else None
    method = _extract_string_property(script, "method") or ("POST" if body is not None else "GET")

    request = LegadoRequest(url=url, method=method.upper(), body=body)
    await _apply_search_ajax_headers(request, source_key, keyword)
    return request


async def _build_js_expression_request(
    script: str, source_key: str, keyword: str, page: int
) -> LegadoRequest | None:
    """Handle simple ``@js: 'url,' + JSON.stringify({...})`` search rules."""
    expression = script.strip().rstrip(";")
    if expression.startswith("return "):
        expression = expression[len("return ") :].strip()

    match = re.fullmatch(r"(.+?)\+\s*JSON\.stringify\(\s*\{(.*)\}\s*\)\s*", expression, flags=re.S)
    if not match:
        return None

    context = {"key": keyword, "keyword": keyword, "page": str(page)}
    prefix = _eval_string_expression(match.group(1), context, source_key)
    if not prefix:
        return None

    options = _parse_js_object_literal(match.group(2), context, source_key)
    if options is None:
        return None

    spec = prefix + json.dumps(options, ensure_ascii=False, separators=(",", ":"))
    request = parse_request_spec(spec, base_url=source_key)
    if request:
        await _apply_search_ajax_headers(request, source_key, keyword)
    return request


async def _apply_search_ajax_headers(request: LegadoRequest, source_key: str, keyword: str) -> None:
    """Add browser-like headers used by mobile search API endpoints."""
    if request.method.upper() != "POST" or not source_key:
        return

    from app.core.http_client import http_client

    referer = f"{source_key.rstrip('/')}/user/search.html?q={quote(keyword, safe='')}"
    defaults = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": source_key.rstrip("/"),
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
    }
    for key, value in defaults.items():
        if not _has_header(request.headers, key):
            request.headers[key] = value

    if not _has_header(request.headers, "Cookie"):
        cookie_header = await http_client.get_domain_cookie_header(source_key)
        if cookie_header:
            request.headers["Cookie"] = cookie_header


def _absolute_url(base_url: str, url: str) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if not base_url:
        return url
    return urljoin(base_url.rstrip("/") + "/", url)


def _find_request_options_comma(text: str) -> int:
    in_string: str | None = None
    escape = False
    for index, char in enumerate(text):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if in_string:
            if char == in_string:
                in_string = None
            continue
        if char in {'"', "'", "`"}:
            in_string = char
            continue
        if char == "," and text[index + 1 :].lstrip().startswith("{"):
            return index
    return -1


def _has_header(headers: dict[str, str], name: str) -> bool:
    lowered = name.lower()
    return any(key.lower() == lowered for key in headers)


def _find_call_argument(script: str, function_name: str) -> str | None:
    marker = f"{function_name}("
    start = script.find(marker)
    if start < 0:
        return None
    index = start + len(marker)
    depth = 1
    in_string: str | None = None
    escape = False
    while index < len(script):
        char = script[index]
        if escape:
            escape = False
        elif char == "\\":
            escape = True
        elif in_string:
            if char == in_string:
                in_string = None
        elif char in {'"', "'", "`"}:
            in_string = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return script[start + len(marker) : index].strip()
        index += 1
    return None


def _eval_string_expression(expr: str, context: dict[str, str], source_key: str) -> str:
    parts = _split_js_concat(expr)
    rendered: list[str] = []
    for part in parts:
        token = part.strip()
        if token in {"source.key", "source.getKey()"}:
            rendered.append(source_key)
        elif token in context:
            rendered.append(context[token])
        elif function_match := re.fullmatch(
            r"(?:java\.)?(base64Encode|encodeURI|encodeURIComponent)\((.*?)\)", token
        ):
            fn = function_match.group(1)
            value = _eval_string_expression(function_match.group(2), context, source_key)
            if fn == "base64Encode":
                rendered.append(b64encode(value.encode("utf-8")).decode("ascii"))
            elif fn == "encodeURI":
                rendered.append(quote(value, safe="/?:@&=+$,#"))
            else:
                rendered.append(quote(value, safe=""))
        elif len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'", "`"}:
            rendered.append(_render_template_literal(token[1:-1], context))
        else:
            rendered.append("")
    return "".join(rendered)


def _parse_js_object_literal(
    body: str, context: dict[str, str], source_key: str
) -> dict[str, str] | None:
    result: dict[str, str] = {}
    for item in _split_top_level_commas(body):
        if ":" not in item:
            return None
        key_expr, value_expr = item.split(":", 1)
        key = key_expr.strip().strip("\"'")
        if not key:
            return None
        result[key] = _eval_string_expression(value_expr, context, source_key)
    return result


def _split_top_level_commas(expr: str) -> list[str]:
    parts: list[str] = []
    start = 0
    in_string: str | None = None
    escape = False
    depth = 0
    for index, char in enumerate(expr):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if in_string:
            if char == in_string:
                in_string = None
            continue
        if char in {'"', "'", "`"}:
            in_string = char
            continue
        if char in "([{":
            depth += 1
            continue
        if char in ")]}":
            depth = max(0, depth - 1)
            continue
        if char == "," and depth == 0:
            parts.append(expr[start:index].strip())
            start = index + 1
    parts.append(expr[start:].strip())
    return [part for part in parts if part]


def _split_js_concat(expr: str) -> list[str]:
    parts: list[str] = []
    start = 0
    in_string: str | None = None
    escape = False
    for index, char in enumerate(expr):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if in_string:
            if char == in_string:
                in_string = None
            continue
        if char in {'"', "'", "`"}:
            in_string = char
            continue
        if char == "+":
            parts.append(expr[start:index])
            start = index + 1
    parts.append(expr[start:])
    return parts


def _extract_js_var_strings(text: str) -> dict[str, str]:
    return {
        name: value
        for name, value in re.findall(r"\b(?:var|let|const)?\s*([A-Za-z_$][\w$]*)\s*=\s*\"([^\"]*)\";", text)
    }


def _extract_assigned_source_url(script: str, name: str, source_key: str) -> str:
    pattern = rf"\b{name}\s*=\s*(source\.key\s*\+\s*([\"'])(.*?)\2)\s*;"
    match = re.search(pattern, script, flags=re.S)
    if not match:
        return ""
    return source_key + match.group(3)


def _extract_template_property(script: str, prop: str) -> str | None:
    match = re.search(rf"[\"']{re.escape(prop)}[\"']\s*:\s*`([^`]*)`", script, flags=re.S)
    return match.group(1) if match else None


def _extract_string_property(script: str, prop: str) -> str | None:
    match = re.search(rf"[\"']{re.escape(prop)}[\"']\s*:\s*([\"'])(.*?)\1", script, flags=re.S)
    return match.group(2) if match else None


def _render_template_literal(template: str, context: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        return context.get(match.group(1), "")

    return re.sub(r"\$\{([A-Za-z_$][\w$]*)\}", repl, template)
