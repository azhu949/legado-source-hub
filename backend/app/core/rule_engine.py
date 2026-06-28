"""规则引擎：解析执行 Legado 书源提取规则。

支持四种规则类型：JsonPath / XPath / CSS 选择器 / 正则。
判断逻辑：
  - 当 is_json=True 时直接解析 JSON 并使用 JsonPath。
  - 否则按优先级：若规则以 $ 或 $. 开头尝试 JsonPath；
    以 // 或 / 开头尝试 XPath；@css: 前缀走 CSS；@regex: 走正则；
    其余按通用正则/简单选择器兜底。
"""

import base64
import json
import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from lxml import etree
from jsonpath_ng.ext import parse as jsonpath_parse

logger = logging.getLogger(__name__)

# Legado 规则前缀约定
_CSS_PREFIX = "@css:"
_XPATH_PREFIX = "@xpath:"
_REGEX_PREFIX = "@regex:"
_JSON_PREFIX = "@json:"
_JSONPATH_PREFIX = "$"
_XSW_AES_CONTENT_RULE = "@xsw-aes-content"
_FILTER_SUFFIX = "Filter"
_JS_UNHANDLED = object()
_SIMPLE_JSONPATH_UNHANDLED = object()
_META_RULE_KEYS = {"init"}
_LIST_PAGE_RULE_KEYS = {
    "bookList": {"nextUrl"},
    "chapterList": {"nextTocUrl"},
}


class RuleEngine:
    """规则提取引擎。"""

    # ---------------- 公共入口 ----------------

    @staticmethod
    def extract(
        content: str,
        rule: str,
        is_json: bool = False,
        base_url: str = "",
    ) -> Any:
        """根据单条规则从内容中提取数据。

        Args:
            content: 原始内容字符串（HTML 或 JSON 文本）。
            rule: 提取规则。
            is_json: 内容是否为 JSON。

        Returns:
            提取结果：字符串、列表或 None。
        """
        if not rule or not content:
            return None

        try:
            rule = str(rule).strip()
            if "##" in rule:
                return RuleEngine._apply_regex_replacement(content, rule, is_json, base_url)
            for operator in ("||", "%%", "&&"):
                parts = RuleEngine._split_rule_operator(rule, operator)
                if len(parts) > 1:
                    return RuleEngine._apply_operator_rules(content, parts, operator, is_json, base_url)

            js_result = RuleEngine._apply_inline_js_rule(content, rule, is_json, base_url)
            if js_result is not _JS_UNHANDLED:
                return js_result

            rule = RuleEngine._strip_legado_scripts(rule)
            if not rule:
                return None

            if is_json:
                return RuleEngine._extract_json(content, rule)

            # 复合规则：规则1$$规则2 依次应用
            if "$$" in rule:
                return RuleEngine._apply_compound(content, rule, is_json, base_url)

            return RuleEngine._extract_html(content, rule)
        except Exception as e:  # noqa: BLE001
            logger.debug("规则提取失败 rule=%r err=%s", rule, e)
            return None

    @staticmethod
    def apply_rules(
        content: str,
        rules: dict,
        is_json: bool = False,
        base_url: str = "",
    ) -> dict:
        """对一组规则批量提取，返回字段字典。

        Args:
            content: 原始内容。
            rules: 规则字典，如 {"name": "$.title", "author": "//span"}。
            is_json: 内容是否为 JSON。

        Returns:
            {"name": "...", "author": "...", ...}，提取失败的字段为空字符串/列表。
        """
        if not rules:
            return {}

        # 对于列表类规则（bookList / chapterList），需要先提取列表再逐项应用子规则
        list_key = "bookList" if "bookList" in rules else (
            "chapterList" if "chapterList" in rules else None
        )

        if list_key:
            return RuleEngine._apply_list_rules(content, rules, list_key, is_json, base_url)

        # 普通字段提取
        result: dict[str, Any] = {}
        for field, rule in rules.items():
            if not rule or RuleEngine._is_non_extract_rule(field):
                continue
            val = RuleEngine.extract(content, rule, is_json, base_url)
            result[field] = RuleEngine._normalize_value(val)
        return RuleEngine._apply_field_filters(result, rules)

    # ---------------- JSON / JsonPath ----------------

    @staticmethod
    def _extract_json(content: str, rule: str) -> Any:
        """从 JSON 内容中按 JsonPath 提取。"""
        rule = RuleEngine._strip_legado_scripts(rule)
        rule = rule.removeprefix(_JSON_PREFIX)
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None
        return RuleEngine._jsonpath_query(data, rule)

    @staticmethod
    def _jsonpath_query(data: Any, rule: str) -> Any:
        """对已解析的 JSON 数据执行 JsonPath 查询。"""
        rule = RuleEngine._strip_legado_scripts(str(rule))
        rule = rule.removeprefix(_JSON_PREFIX)
        if "{{" in rule and "}}" in rule:
            return RuleEngine._render_json_template(data, rule)
        if not rule.startswith("$"):
            # 不是 JsonPath，尝试当作键名
            if isinstance(data, dict) and rule in data:
                return data[rule]
            return None
        simple_result = RuleEngine._simple_jsonpath_query(data, rule)
        if simple_result is not _SIMPLE_JSONPATH_UNHANDLED:
            return simple_result
        try:
            expr = jsonpath_parse(rule)
            matches = [m.value for m in expr.find(data)]
            if not matches:
                return None
            if len(matches) == 1:
                return matches[0]
            return matches
        except Exception as e:  # noqa: BLE001
            logger.debug("JsonPath 查询失败 rule=%r err=%s", rule, e)
            return None

    @staticmethod
    def _simple_jsonpath_query(data: Any, rule: str) -> Any:
        """Fast path for common JsonPath rules such as ``$.data[*]``."""
        rule = str(rule or "").strip()
        if rule == "$":
            return data
        if not re.fullmatch(r"\$(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[(?:\*|\d+)\])?)*", rule):
            return _SIMPLE_JSONPATH_UNHANDLED

        current: list[Any] = [data]
        for segment in re.finditer(r"\.([A-Za-z_][A-Za-z0-9_]*)(?:\[(\*|\d+)\])?", rule[1:]):
            key = segment.group(1)
            index = segment.group(2)
            next_values: list[Any] = []

            for item in current:
                if not isinstance(item, dict) or key not in item:
                    continue
                value = item[key]
                if index == "*":
                    if isinstance(value, list):
                        next_values.extend(value)
                    elif value is not None:
                        next_values.append(value)
                elif index is not None:
                    if isinstance(value, list):
                        position = int(index)
                        if 0 <= position < len(value):
                            next_values.append(value[position])
                elif value is not None:
                    next_values.append(value)

            current = next_values
            if not current:
                return None

        if not current:
            return None
        if len(current) == 1:
            return current[0]
        return current

    @staticmethod
    def _render_json_template(data: Any, template: str) -> str:
        """Render simple Legado JSON placeholders such as ``{{$.articleid}}``."""

        def replace(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            if not expr:
                return ""
            try:
                simple_result = RuleEngine._simple_jsonpath_query(data, expr)
                if simple_result is not _SIMPLE_JSONPATH_UNHANDLED:
                    matches = [] if simple_result is None else (
                        simple_result if isinstance(simple_result, list) else [simple_result]
                    )
                else:
                    parsed = jsonpath_parse(expr)
                    matches = [item.value for item in parsed.find(data)]
            except Exception as e:  # noqa: BLE001
                logger.debug("JSON 模板渲染失败 expr=%r err=%s", expr, e)
                return ""
            if not matches:
                return ""
            value = matches[0]
            if value is None:
                return ""
            return str(value)

        return re.sub(r"\{\{([^{}]+)\}\}", replace, str(template))

    # ---------------- HTML / XPath / CSS / Regex ----------------

    @staticmethod
    def _extract_html(content: str, rule: str) -> Any:
        """从 HTML 内容中提取（自动判断规则类型）。"""
        rule = RuleEngine._strip_legado_scripts(rule)
        if rule == _XSW_AES_CONTENT_RULE:
            return RuleEngine._extract_xsw_aes_content(content)
        if rule.startswith(_JSONPATH_PREFIX):
            # 可能内容虽非 json，但规则是 JsonPath（如部分接口返回 json 文本）
            return RuleEngine._extract_json(content, rule)
        if rule.startswith(_JSON_PREFIX):
            return RuleEngine._extract_json(content, rule[len(_JSON_PREFIX):])
        if rule.startswith(_XPATH_PREFIX) or rule.startswith("//") or rule.startswith("/"):
            return RuleEngine._extract_xpath(content, rule.removeprefix(_XPATH_PREFIX))
        if rule.startswith(_CSS_PREFIX):
            return RuleEngine._extract_css(content, rule[len(_CSS_PREFIX):])
        if rule.startswith(_REGEX_PREFIX):
            return RuleEngine._extract_regex(content, rule[len(_REGEX_PREFIX):])
        if RuleEngine._looks_like_default_rule(rule):
            return RuleEngine._extract_default_rule(content, rule)
        if RuleEngine._split_selector_attr(rule):
            return RuleEngine._extract_selector_attr(content, rule)
        if RuleEngine._looks_like_css_selector(rule):
            result = RuleEngine._extract_css(content, rule)
            if result is not None:
                return result
        # 兜底：尝试正则，再尝试 CSS 选择器
        result = RuleEngine._extract_regex(content, rule)
        if result is not None:
            return result
        return RuleEngine._extract_css(content, rule)

    @staticmethod
    def _extract_xpath(content: str, rule: str) -> Any:
        """使用 lxml 执行 XPath 提取。"""
        try:
            # 尝试 HTML 解析
            tree = etree.HTML(content)
            if tree is None:
                return None
            result = tree.xpath(rule)
            if not result:
                return None
            if isinstance(result, list):
                if len(result) == 1:
                    return RuleEngine._node_to_text(result[0])
                return [RuleEngine._node_to_text(item) for item in result]
            return RuleEngine._node_to_text(result)
        except etree.XPathError as e:
            logger.debug("XPath 解析失败 rule=%r err=%s", rule, e)
            return None

    @staticmethod
    def _extract_css(content: str, rule: str) -> Any:
        """使用 BeautifulSoup 执行 CSS 选择器提取。"""
        try:
            soup = BeautifulSoup(content, "lxml")
            rule = RuleEngine._normalize_css_selector(rule)
            elements = soup.select(rule)
            if not elements:
                return None
            if len(elements) == 1:
                return RuleEngine._soup_node_to_text(elements[0])
            return [RuleEngine._soup_node_to_text(el) for el in elements]
        except Exception as e:  # noqa: BLE001
            logger.debug("CSS 提取失败 rule=%r err=%s", rule, e)
            return None

    @staticmethod
    def _extract_regex(content: str, rule: str) -> Any:
        """使用正则表达式提取（支持捕获组）。"""
        try:
            matches = re.findall(rule, content)
            if not matches:
                return None
            # findall 返回组元组时取第一个组
            if isinstance(matches[0], tuple):
                matches = [m[0] if m[0] else (m[1] if len(m) > 1 else "") for m in matches]
            if len(matches) == 1:
                return matches[0]
            return matches
        except re.error as e:
            logger.debug("正则提取失败 rule=%r err=%s", rule, e)
            return None

    @staticmethod
    def _extract_xsw_aes_content(content: str) -> str | None:
        """Decrypt xsw.tw chapter content embedded in page JavaScript."""
        encrypted_match = re.search(r'var\s+encrypted\s*=\s*"([^"]+)"', content)
        key_match = re.search(r'var\s+key\s*=\s*"([0-9a-fA-F]+)"', content)
        iv_match = re.search(r'var\s+iv\s*=\s*"([0-9a-fA-F]+)"', content)
        if not (encrypted_match and key_match and iv_match):
            return None

        try:
            encrypted = base64.b64decode(encrypted_match.group(1))
            key = bytes.fromhex(key_match.group(1))
            iv = bytes.fromhex(iv_match.group(1))
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            decrypted = (decryptor.update(encrypted) + decryptor.finalize()).rstrip(b"\x00")
            return RuleEngine._decode_text_bytes(decrypted)
        except Exception as e:  # noqa: BLE001
            logger.debug("xsw.tw AES 正文解密失败: %s", e)
            return None

    @staticmethod
    def _decode_text_bytes(raw: bytes) -> str:
        best_text = ""
        best_score: int | None = None
        for charset in ("utf-8", "big5", "gb18030"):
            text = raw.decode(charset, errors="replace")
            score = text.count("\ufffd")
            if best_score is None or score < best_score:
                best_text = text
                best_score = score
                if score == 0:
                    break
        return best_text.strip()

    @staticmethod
    def _apply_compound(content: str, rule: str, is_json: bool, base_url: str = "") -> Any:
        """应用复合规则（规则1$$规则2）：前者结果作为后者输入。"""
        parts = rule.split("$$", 1)
        first_rule = parts[0].strip()
        second_rule = parts[1].strip()
        first_result = RuleEngine.extract(content, first_rule, is_json, base_url)
        if first_result is None:
            return None
        if isinstance(first_result, list):
            return [RuleEngine.extract(str(item), second_rule, is_json, base_url) for item in first_result]
        return RuleEngine.extract(str(first_result), second_rule, is_json, base_url)

    @staticmethod
    def _apply_list_rules(
        content: str,
        rules: dict,
        list_key: str,
        is_json: bool,
        base_url: str = "",
    ) -> dict:
        """处理包含列表规则的规则集（如 ruleSearch.bookList）。"""
        list_rule = RuleEngine._strip_legado_scripts(str(rules.get(list_key, "")))
        if not list_rule:
            return {}

        items = RuleEngine._extract_list_items(content, list_rule, is_json, base_url)
        if items is None:
            items = []

        if not isinstance(items, list):
            items = [items]

        page_rule_keys = _LIST_PAGE_RULE_KEYS.get(list_key, set())
        page_rules = {
            k: v for k, v in rules.items()
            if k in page_rule_keys and v and not RuleEngine._is_non_extract_rule(k)
        }
        # 子规则字段
        child_rules = {
            k: v for k, v in rules.items()
            if k != list_key and k not in page_rule_keys and not RuleEngine._is_non_extract_rule(k)
        }
        results: list[dict] = []

        for item in items:
            entry: dict[str, Any] = {}
            if is_json:
                item_content = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                for field, rule in child_rules.items():
                    if not rule:
                        continue
                    val = RuleEngine.extract(item_content, rule, is_json=True, base_url=base_url)
                    entry[field] = RuleEngine._normalize_value(val)
            else:
                # HTML 列表：对每个节点片段应用子规则
                item_html = item if isinstance(item, str) else etree.tostring(
                    item, encoding="unicode"
                )
                for field, rule in child_rules.items():
                    if not rule:
                        continue
                    val = RuleEngine._extract_item_child_rule(item_html, rule, is_json, base_url)
                    entry[field] = RuleEngine._normalize_value(val)
            entry = RuleEngine._apply_field_filters(entry, rules)
            results.append(entry)

        result: dict[str, Any] = {list_key: results}
        for field, rule in page_rules.items():
            val = RuleEngine.extract(content, rule, is_json, base_url)
            result[field] = RuleEngine._normalize_value(val)

        return result

    @staticmethod
    def _extract_list_items(
        content: str,
        list_rule: str,
        is_json: bool,
        base_url: str = "",
    ) -> Any:
        """Extract list items while preserving HTML node snippets for child rules."""
        if is_json:
            return RuleEngine.extract(content, list_rule, is_json=True, base_url=base_url)

        rule = RuleEngine._strip_legado_scripts(list_rule)
        if rule.startswith(_CSS_PREFIX):
            rule = rule[len(_CSS_PREFIX):]

        if rule.startswith(_XPATH_PREFIX) or rule.startswith("//") or rule.startswith("/"):
            try:
                tree = etree.HTML(content)
                if tree is None:
                    return None
                nodes = tree.xpath(rule.removeprefix(_XPATH_PREFIX))
                return [
                    etree.tostring(node, encoding="unicode") if hasattr(node, "tag") else str(node)
                    for node in nodes
                ]
            except Exception as e:  # noqa: BLE001
                logger.debug("列表 XPath 提取失败 rule=%r err=%s", rule, e)
                return None

        selector_attr = RuleEngine._split_selector_attr(rule)
        selector = selector_attr[0] if selector_attr else rule
        try:
            soup = BeautifulSoup(content, "lxml")
            selector = RuleEngine._normalize_css_selector(selector)
            elements = soup.select(selector)
            if not elements:
                return None
            return [str(el) for el in elements]
        except Exception as e:  # noqa: BLE001
            logger.debug("列表 CSS 提取失败 rule=%r err=%s", rule, e)
            return RuleEngine.extract(content, rule, is_json=False, base_url=base_url)

    @staticmethod
    def _extract_item_child_rule(
        item_html: str,
        rule: str,
        is_json: bool,
        base_url: str = "",
    ) -> Any:
        """Apply a child rule to a list item, supporting current-node attrs."""
        if is_json:
            return RuleEngine.extract(item_html, rule, is_json, base_url)

        normalized_rule = RuleEngine._strip_legado_scripts(str(rule))
        if RuleEngine._is_current_item_attr_rule(normalized_rule):
            value = RuleEngine._extract_current_item_attr(item_html, normalized_rule)
            if value is not None:
                return value
        return RuleEngine.extract(item_html, rule, is_json, base_url)

    @staticmethod
    def _is_current_item_attr_rule(rule: str) -> bool:
        if rule in {"text", "textNodes", "html", "outerHtml"}:
            return True
        return bool(re.fullmatch(r"[A-Za-z_:][-A-Za-z0-9_:.]*", rule or ""))

    @staticmethod
    def _extract_current_item_attr(item_html: str, attr: str) -> Any:
        try:
            soup = BeautifulSoup(item_html, "lxml")
            node = None
            for candidate in soup.find_all(True):
                if candidate.name not in {"html", "body"}:
                    node = candidate
                    break
            if node is None:
                return None
            return RuleEngine._soup_node_to_attr(node, attr)
        except Exception as e:  # noqa: BLE001
            logger.debug("当前节点属性提取失败 attr=%r err=%s", attr, e)
            return None

    # ---------------- 工具方法 ----------------

    @staticmethod
    def _node_to_text(node: Any) -> str:
        """将 lxml 节点/属性转为文本。"""
        if isinstance(node, str):
            return node.strip()
        if hasattr(node, "text"):
            text = node.text_content() if hasattr(node, "text_content") else (node.text or "")
            return text.strip()
        return str(node).strip()

    @staticmethod
    def _soup_node_to_text(node: Any) -> str:
        """将 BeautifulSoup 节点转为文本。"""
        if isinstance(node, str):
            return node.strip()
        return node.get_text(strip=True)

    @staticmethod
    def _normalize_value(val: Any) -> Any:
        """归一化提取结果：None→空串，单元素列表→标量。"""
        if val is None:
            return ""
        if isinstance(val, list):
            if not val:
                return ""
            if len(val) == 1:
                return val[0] if val[0] is not None else ""
            return val
        return val

    @staticmethod
    def _is_non_extract_rule(field: str) -> bool:
        return field in _META_RULE_KEYS or field.endswith(_FILTER_SUFFIX)

    @staticmethod
    def _apply_field_filters(result: dict[str, Any], rules: dict) -> dict[str, Any]:
        """Apply Legado ``nameFilter`` / ``contentFilter`` style cleanup rules."""
        for field, filter_rule in rules.items():
            if not field.endswith(_FILTER_SUFFIX) or not filter_rule:
                continue
            target_field = field[: -len(_FILTER_SUFFIX)]
            if not target_field or target_field not in result:
                continue
            result[target_field] = RuleEngine._apply_filter_value(
                result[target_field],
                filter_rule,
                target_field=target_field,
            )
        return result

    @staticmethod
    def _apply_filter_value(value: Any, filter_rule: Any, target_field: str = "") -> Any:
        if isinstance(value, list):
            return [
                RuleEngine._apply_filter_value(item, filter_rule, target_field=target_field)
                for item in value
            ]
        if value is None:
            return value

        text = str(value)
        for pattern, replacement in RuleEngine._iter_filter_operations(filter_rule, target_field):
            try:
                text = re.sub(pattern, replacement, text, flags=re.S)
            except re.error:
                text = text.replace(pattern, replacement)
        return text.strip()

    @staticmethod
    def _iter_filter_operations(filter_rule: Any, target_field: str = "") -> list[tuple[str, str]]:
        operations: list[tuple[str, str]] = []

        if isinstance(filter_rule, dict):
            pattern = filter_rule.get("regex") or filter_rule.get("pattern")
            replacement = filter_rule.get("replacement", filter_rule.get("replace", ""))
            if pattern:
                operations.append((str(pattern), str(replacement)))
            return operations

        if isinstance(filter_rule, str):
            text = str(filter_rule)
            if not text.strip():
                return operations
            if "##" in text:
                pattern, replacement = text.split("##", 1)
                if pattern:
                    operations.append((pattern, replacement))
            else:
                operations.append((text.strip(), ""))
            return operations

        if isinstance(filter_rule, list):
            if RuleEngine._is_filter_replacement_pair(filter_rule, target_field):
                operations.append((str(filter_rule[0]), str(filter_rule[1])))
                return operations
            for item in filter_rule:
                operations.extend(RuleEngine._iter_filter_operations(item, target_field))
        return operations

    @staticmethod
    def _is_filter_replacement_pair(filter_rule: list[Any], target_field: str) -> bool:
        if len(filter_rule) != 2:
            return False
        if any(isinstance(item, (dict, list)) for item in filter_rule):
            return False
        return target_field != "content"

    @staticmethod
    def _apply_operator_rules(
        content: str,
        parts: list[str],
        operator: str,
        is_json: bool,
        base_url: str = "",
    ) -> Any:
        """Apply Legado ``&&`` / ``||`` / ``%%`` connectors."""
        values: list[Any] = []
        for part in parts:
            value = RuleEngine.extract(content, part, is_json, base_url)
            normalized = RuleEngine._normalize_value(value)
            if operator == "||":
                if RuleEngine._has_value(normalized):
                    return normalized
                continue
            if RuleEngine._has_value(normalized):
                values.append(normalized)

        if operator == "%%":
            return RuleEngine._interleave_values(values)

        flattened: list[Any] = []
        for value in values:
            if isinstance(value, list):
                flattened.extend(item for item in value if RuleEngine._has_value(item))
            else:
                flattened.append(value)

        if not flattened:
            return None
        if all(isinstance(item, str) for item in flattened):
            return " ".join(str(item).strip() for item in flattened if str(item).strip())
        return flattened

    @staticmethod
    def _apply_regex_replacement(
        content: str,
        rule: str,
        is_json: bool,
        base_url: str = "",
    ) -> Any:
        """Apply Legado ``rule##regex##replacement`` purification rules."""
        parts = rule.split("##", 2)
        if len(parts) < 2:
            return None

        source_rule = parts[0]
        pattern = parts[1]
        replacement = parts[2] if len(parts) >= 3 else ""
        count = 0
        if replacement.endswith("###"):
            replacement = replacement[:-3]
            count = 1

        if not source_rule:
            source_rule = "all"

        source_value = (
            content
            if source_rule == "all"
            else RuleEngine.extract(content, source_rule, is_json, base_url)
        )
        source_value = RuleEngine._normalize_value(source_value)

        def replace_one(value: Any) -> str:
            return re.sub(pattern, replacement, str(value), count=count)

        if isinstance(source_value, list):
            return [replace_one(item) for item in source_value]
        return replace_one(source_value)

    @staticmethod
    def _apply_inline_js_rule(
        content: str,
        rule: str,
        is_json: bool,
        base_url: str = "",
    ) -> Any:
        """Apply a small supported subset of Legado ``<js>`` result transforms."""
        if "<js" not in str(rule).lower():
            return _JS_UNHANDLED

        match = re.search(r"<js>(.*?)</js>", str(rule), flags=re.S | re.I)
        if not match:
            return _JS_UNHANDLED

        source_rule = str(rule)[: match.start()].strip()
        source_value = (
            RuleEngine.extract(content, source_rule, is_json, base_url)
            if source_rule
            else content
        )
        return RuleEngine._apply_supported_js_transform(
            source_value,
            match.group(1),
            content,
            base_url,
        )

    @staticmethod
    def _apply_supported_js_transform(
        source_value: Any,
        script: str,
        content: str,
        base_url: str = "",
    ) -> Any:
        script = str(script or "")

        if "Cover(result)" in script and "novel.cooks.tw" in str(base_url):
            return RuleEngine._cooks_cover_url(source_value)

        if re.search(r"\b(?:Clean|T)\s*\(\s*result\s*\)", script):
            return RuleEngine._clean_legado_text(source_value)

        if "/api/chapter/list/" in script:
            article_id = RuleEngine._extract_article_id(content, base_url)
            origin = RuleEngine._origin_from_url(base_url)
            if article_id and origin:
                return f"{origin}/api/chapter/list/{article_id}{RuleEngine._lang_suffix(script, base_url)}"

        if "/api/chapter/content/" in script:
            chapter_id = re.sub(r"\D", "", str(source_value or ""))
            article_id = RuleEngine._extract_article_id("", base_url)
            origin = RuleEngine._origin_from_url(base_url)
            if article_id and chapter_id and origin:
                return (
                    f"{origin}/api/chapter/content/{article_id}/{chapter_id}"
                    f"{RuleEngine._lang_suffix(script, base_url)}"
                )

        return _JS_UNHANDLED

    @staticmethod
    def _cooks_cover_url(value: Any) -> str:
        book_id = re.sub(r"\D", "", str(value or ""))
        if not book_id:
            return ""
        numeric_id = int(book_id)
        return f"https://pic.cooks.tw/{numeric_id // 1000}/{numeric_id}/{numeric_id}s.jpg"

    @staticmethod
    def _clean_legado_text(value: Any) -> str:
        text = "\n".join(str(item) for item in value) if isinstance(value, list) else str(value or "")
        replacements = (
            (r"<br\s*/?>", "\n"),
            (r"<p[^>]*>", "\n"),
            (r"</p>", "\n"),
            (r"<[^>]+>", ""),
            (r"&nbsp;", " "),
            (r"&amp;", "&"),
            (r"&lt;", "<"),
            (r"&gt;", ">"),
            (r"&#39;", "'"),
            (r"&quot;", '"'),
            (r"\r", ""),
            (r"[ \t]+\n", "\n"),
            (r"\n{3,}", "\n\n"),
        )
        for pattern, replacement in replacements:
            text = re.sub(pattern, replacement, text, flags=re.I)
        return text.strip()

    @staticmethod
    def _extract_article_id(value: Any, base_url: str = "") -> str:
        article_id = RuleEngine._article_id_from_jsonish(value)
        if article_id:
            return article_id

        text = str(base_url or value or "")
        for pattern in (
            r"/api/novel/detail/(\d+)",
            r"/api/chapter/list/(\d+)",
            r"/novel/detail/(\d+)",
            r"/detail/(\d+)",
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _article_id_from_jsonish(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("articleid", "articleId", "bookid", "bookId"):
                if value.get(key):
                    return re.sub(r"\D", "", str(value[key]))
            nested = value.get("data")
            if isinstance(nested, dict):
                return RuleEngine._article_id_from_jsonish(nested)
            return ""

        if not isinstance(value, str):
            return ""

        text = value.strip()
        if not text.startswith(("{", "[")):
            return ""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return ""
        return RuleEngine._article_id_from_jsonish(parsed)

    @staticmethod
    def _origin_from_url(url: str) -> str:
        parsed = urlparse(str(url or ""))
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _lang_suffix(script: str, base_url: str = "") -> str:
        if "lang=zh-CN" in str(script) or "lang=zh-CN" in str(base_url):
            return "?lang=zh-CN"
        return ""

    @staticmethod
    def _strip_legado_scripts(rule: str) -> str:
        """Remove Legado JS transform segments, leaving the extractor rule."""
        if not rule:
            return ""
        text = str(rule).strip()
        text = re.sub(r"<js>.*?</js>", "", text, flags=re.S | re.I).strip()
        if "@js:" in text:
            text = text.split("@js:", 1)[0].strip()

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) <= 1:
            return lines[0] if lines else ""

        for line in lines:
            if line.startswith(("$", "@css:", "@xpath:", "@regex:", "//", "/", ".", "#", "[")):
                return line
        return lines[0]

    @staticmethod
    def _split_rule_operator(rule: str, operator: str) -> list[str]:
        """Split a rule by a Legado connector outside strings and brackets."""
        parts: list[str] = []
        start = 0
        in_string: str | None = None
        escape = False
        bracket_depth = 0
        index = 0
        lower_rule = rule.lower()
        while index < len(rule):
            if lower_rule.startswith("<js>", index):
                end_index = lower_rule.find("</js>", index + 4)
                if end_index >= 0:
                    index = end_index + len("</js>")
                    continue

            char = rule[index]
            if escape:
                escape = False
                index += 1
                continue
            if char == "\\":
                escape = True
                index += 1
                continue
            if in_string:
                if char == in_string:
                    in_string = None
                index += 1
                continue
            if char in {'"', "'"}:
                in_string = char
                index += 1
                continue
            if char == "[":
                bracket_depth += 1
                index += 1
                continue
            if char == "]":
                bracket_depth = max(0, bracket_depth - 1)
                index += 1
                continue
            if bracket_depth == 0 and rule.startswith(operator, index):
                parts.append(rule[start:index].strip())
                index += len(operator)
                start = index
                continue
            index += 1

        if parts:
            parts.append(rule[start:].strip())
            return [part for part in parts if part]
        return [rule]

    @staticmethod
    def _has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, list):
            return any(RuleEngine._has_value(item) for item in value)
        return str(value).strip() != ""

    @staticmethod
    def _interleave_values(values: list[Any]) -> list[Any] | None:
        lists: list[list[Any]] = []
        for value in values:
            if isinstance(value, list):
                lists.append(value)
            else:
                lists.append([value])
        if not lists:
            return None

        result: list[Any] = []
        max_len = max(len(items) for items in lists)
        for index in range(max_len):
            for items in lists:
                if index < len(items) and RuleEngine._has_value(items[index]):
                    result.append(items[index])
        return result or None

    @staticmethod
    def _extract_selector_attr(content: str, rule: str) -> Any:
        """Extract Legado ``selector@attr`` / ``selector@text`` / ``selector@html``."""
        pair = RuleEngine._split_selector_attr(rule)
        if not pair:
            return None
        selector, attr = pair
        if not selector:
            return None
        try:
            soup = BeautifulSoup(content, "lxml")
            selector, index = RuleEngine._strip_selector_index(selector)
            selector = RuleEngine._normalize_css_selector(selector)
            elements = soup.select(selector)
            if not elements:
                return None
            if index is not None:
                if index < 0 or index >= len(elements):
                    return None
                elements = [elements[index]]
            values = [RuleEngine._soup_node_to_attr(el, attr) for el in elements]
            values = [value for value in values if value is not None]
            if not values:
                return None
            if len(values) == 1:
                return values[0]
            return values
        except Exception as e:  # noqa: BLE001
            logger.debug("Legado selector@attr 提取失败 rule=%r err=%s", rule, e)
            return None

    @staticmethod
    def _split_selector_attr(rule: str) -> tuple[str, str] | None:
        """Split a selector rule on the last @ outside strings/brackets."""
        in_string: str | None = None
        escape = False
        bracket_depth = 0

        for index in range(len(rule) - 1, -1, -1):
            char = rule[index]
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
            if char in {'"', "'"}:
                in_string = char
                continue
            if char == "]":
                bracket_depth += 1
                continue
            if char == "[":
                bracket_depth = max(0, bracket_depth - 1)
                continue
            if char == "@" and bracket_depth == 0:
                selector = rule[:index].strip()
                attr = rule[index + 1 :].strip()
                if selector and attr:
                    return selector, attr
        return None

    @staticmethod
    def _strip_selector_index(selector: str) -> tuple[str, int | None]:
        match = re.fullmatch(r"(.+)\.(\d+)", selector.strip())
        if not match:
            return selector, None
        return match.group(1), int(match.group(2))

    @staticmethod
    def _normalize_css_selector(selector: str) -> str:
        return str(selector or "").replace(":contains(", ":-soup-contains(")

    @staticmethod
    def _looks_like_css_selector(rule: str) -> bool:
        if not rule:
            return False
        return rule.startswith((".", "#", "[")) or any(token in rule for token in (" > ", " + ", " ~ ", ":"))

    @staticmethod
    def _looks_like_default_rule(rule: str) -> bool:
        parts = rule.split("@")
        return any(part.startswith(("class.", "id.", "tag.")) for part in parts)

    @staticmethod
    def _extract_default_rule(content: str, rule: str) -> Any:
        """Extract a subset of Legado Default/Jsoup rules."""
        try:
            soup = BeautifulSoup(content, "lxml")
            nodes: list[Any] = [soup]
            parts = [part.strip() for part in rule.split("@") if part.strip()]

            for part in parts:
                if part in {"text", "textNodes", "html", "outerHtml"} or (
                    nodes and not RuleEngine._default_segment_to_selector(part)[0]
                ):
                    values = [RuleEngine._soup_node_to_attr(node, part) for node in nodes]
                    values = [value for value in values if value is not None]
                    if not values:
                        return None
                    return values[0] if len(values) == 1 else values

                selector, index = RuleEngine._default_segment_to_selector(part)
                if not selector:
                    values = [RuleEngine._soup_node_to_attr(node, part) for node in nodes]
                    values = [value for value in values if value is not None]
                    return values[0] if len(values) == 1 else values

                next_nodes: list[Any] = []
                for node in nodes:
                    found = node.select(selector)
                    if index is not None:
                        if 0 <= index < len(found):
                            next_nodes.append(found[index])
                    else:
                        next_nodes.extend(found)
                nodes = next_nodes
                if not nodes:
                    return None

            values = [RuleEngine._soup_node_to_text(node) for node in nodes]
            return values[0] if len(values) == 1 else values
        except Exception as e:  # noqa: BLE001
            logger.debug("Default 规则提取失败 rule=%r err=%s", rule, e)
            return None

    @staticmethod
    def _default_segment_to_selector(segment: str) -> tuple[str, int | None]:
        index: int | None = None
        tokens = segment.split(".")
        if tokens and tokens[-1].isdigit():
            index = int(tokens.pop())
        if len(tokens) >= 2 and tokens[0] == "class":
            return "." + ".".join(tokens[1:]), index
        if len(tokens) >= 2 and tokens[0] == "id":
            return "#" + tokens[1], index
        if len(tokens) >= 2 and tokens[0] == "tag":
            return tokens[1], index
        return "", index

    @staticmethod
    def _soup_node_to_attr(node: Any, attr: str) -> Any:
        """Convert a BeautifulSoup node according to a Legado attribute suffix."""
        attr = attr.strip()
        if attr in {"text", "textNodes"}:
            return node.get_text(" ", strip=True)
        if attr == "html":
            return node.decode_contents()
        if attr == "outerHtml":
            return str(node)
        value = node.get(attr)
        if isinstance(value, list):
            return " ".join(value)
        return value
