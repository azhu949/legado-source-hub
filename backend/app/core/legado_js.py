"""JavaScript runtime bridge for Legado rules."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from typing import Any

from app.core.http_client import http_client

logger = logging.getLogger(__name__)

NODE_RUNNER = r"""
const fs = require("fs");
const vm = require("vm");

function toResultString(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try { return JSON.stringify(value); } catch { return String(value); }
}

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const ajaxCalls = [];
const ajaxResponses = input.ajaxResponses || {};
const sourceKey = String(input.sourceKey || "");
const variables = {};

const source = {
  key: sourceKey,
  getKey() { return sourceKey; },
  getVariable(name) { return variables[String(name)] || ""; },
  putVariable(name, value) { variables[String(name)] = String(value ?? ""); },
};

const java = {
  ajax(value) {
    const url = String(value ?? "");
    ajaxCalls.push(url);
    return ajaxResponses[url] || "";
  },
  base64Encode(value) {
    return Buffer.from(String(value ?? ""), "utf8").toString("base64");
  },
  encodeURI(value) { return encodeURI(String(value ?? "")); },
  encodeURIComponent(value) { return encodeURIComponent(String(value ?? "")); },
  longToast() {},
  toast() {},
  log() {},
};

const cookie = {
  removeCookie() {},
  getCookie() { return ""; },
  setCookie() {},
};

const context = vm.createContext({
  key: input.key || "",
  page: input.page || 1,
  source,
  java,
  cookie,
  JSON,
  Math,
  String,
  Number,
  Boolean,
  Array,
  Object,
  RegExp,
  Date,
  parseInt,
  parseFloat,
  isNaN,
  encodeURI,
  encodeURIComponent,
  decodeURI,
  decodeURIComponent,
  console: { log() {} },
});

try {
  let result = vm.runInContext(input.script || "", context, { timeout: input.timeoutMs || 1000 });
  if ((result === undefined || result === null || result === "") && context.result !== undefined) {
    result = context.result;
  }
  if ((result === undefined || result === null || result === "") && context.url && context.bd) {
    result = String(context.url) + "," + JSON.stringify(context.bd);
  }
  if ((result === undefined || result === null || result === "") && context.url) {
    result = context.url;
  }
  process.stdout.write(JSON.stringify({ ok: true, result: toResultString(result), ajaxCalls }));
} catch (error) {
  process.stdout.write(JSON.stringify({
    ok: false,
    error: error && error.stack ? String(error.stack) : String(error),
    ajaxCalls,
  }));
}
"""


async def execute_search_script(
    script: str,
    *,
    source_key: str,
    keyword: str,
    page: int = 1,
    headers: dict[str, str] | None = None,
    timeout_ms: int = 1200,
) -> str | None:
    """Execute a Legado searchUrl ``@js:`` script and return its string result."""
    if not shutil.which("node"):
        return None

    if "removeCookie" in script:
        await http_client.clear_cookies_for_url(source_key)

    ajax_responses: dict[str, str] = {}
    last_result: str | None = None

    for _ in range(3):
        output = await _run_node_script(
            script,
            source_key=source_key,
            keyword=keyword,
            page=page,
            ajax_responses=ajax_responses,
            timeout_ms=timeout_ms,
        )
        if not output:
            return None

        ajax_calls = [url for url in output.get("ajaxCalls", []) if isinstance(url, str) and url]
        missing_calls = [url for url in ajax_calls if url not in ajax_responses]
        last_result = str(output.get("result") or "")

        if missing_calls:
            for url in missing_calls:
                resp = await http_client.get(url, headers=headers or {}, retries=0)
                if resp.get("status") != 200 or not resp.get("body"):
                    logger.debug(
                        "Legado JS ajax failed url=%s status=%s err=%s",
                        url,
                        resp.get("status"),
                        resp.get("error"),
                    )
                    return None
                ajax_responses[url] = str(resp.get("body", "") or "")
            continue

        if output.get("ok"):
            return last_result

        logger.debug("Legado JS 执行失败: %s", output.get("error"))
        return None

    return last_result


async def _run_node_script(
    script: str,
    *,
    source_key: str,
    keyword: str,
    page: int,
    ajax_responses: dict[str, str],
    timeout_ms: int,
) -> dict[str, Any] | None:
    payload = {
        "script": script,
        "sourceKey": source_key,
        "key": keyword,
        "page": page,
        "ajaxResponses": ajax_responses,
        "timeoutMs": timeout_ms,
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            "node",
            "-e",
            NODE_RUNNER,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
            timeout=(timeout_ms / 1000) + 1,
        )
    except (OSError, asyncio.TimeoutError) as e:
        logger.debug("Legado JS runner unavailable: %s", e)
        return None

    if stderr:
        logger.debug("Legado JS stderr: %s", stderr.decode("utf-8", errors="replace"))
    if not stdout:
        return None

    try:
        return json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as e:
        logger.debug("Legado JS output parse failed: %s", e)
        return None
