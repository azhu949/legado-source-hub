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


class RuleEngine:
    """规则提取引擎。"""

    # ---------------- 公共入口 ----------------

    @staticmethod
    def extract(content: str, rule: str, is_json: bool = False) -> Any:
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
                return RuleEngine._apply_regex_replacement(content, rule, is_json)
            for operator in ("||", "%%", "&&"):
                parts = RuleEngine._split_rule_operator(rule, operator)
                if len(parts) > 1:
                    return RuleEngine._apply_operator_rules(content, parts, operator, is_json)

            rule = RuleEngine._strip_legado_scripts(rule)
            if not rule:
                return None

            if is_json:
                return RuleEngine._extract_json(content, rule)

            # 复合规则：规则1$$规则2 依次应用
            if "$$" in rule:
                return RuleEngine._apply_compound(content, rule, is_json)

            return RuleEngine._extract_html(content, rule)
        except Exception as e:  # noqa: BLE001
            logger.debug("规则提取失败 rule=%r err=%s", rule, e)
            return None

    @staticmethod
    def apply_rules(content: str, rules: dict, is_json: bool = False) -> dict:
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
            return RuleEngine._apply_list_rules(content, rules, list_key, is_json)

        # 普通字段提取
        result: dict[str, Any] = {}
        for field, rule in rules.items():
            if not rule:
                continue
            val = RuleEngine.extract(content, rule, is_json)
            result[field] = RuleEngine._normalize_value(val)
        return result

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
        if not rule.startswith("$"):
            # 不是 JsonPath，尝试当作键名
            if isinstance(data, dict) and rule in data:
                return data[rule]
            return None
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
            decrypted = decryptor.update(encrypted) + decryptor.finalize()
            return decrypted.rstrip(b"\x00").decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            logger.debug("xsw.tw AES 正文解密失败: %s", e)
            return None

    @staticmethod
    def _apply_compound(content: str, rule: str, is_json: bool) -> Any:
        """应用复合规则（规则1$$规则2）：前者结果作为后者输入。"""
        parts = rule.split("$$", 1)
        first_rule = parts[0].strip()
        second_rule = parts[1].strip()
        first_result = RuleEngine.extract(content, first_rule, is_json)
        if first_result is None:
            return None
        if isinstance(first_result, list):
            return [RuleEngine.extract(str(item), second_rule, is_json) for item in first_result]
        return RuleEngine.extract(str(first_result), second_rule, is_json)

    @staticmethod
    def _apply_list_rules(
        content: str, rules: dict, list_key: str, is_json: bool
    ) -> dict:
        """处理包含列表规则的规则集（如 ruleSearch.bookList）。"""
        list_rule = RuleEngine._strip_legado_scripts(str(rules.get(list_key, "")))
        if not list_rule:
            return {}

        items = RuleEngine._extract_list_items(content, list_rule, is_json)
        if items is None:
            items = []

        if not isinstance(items, list):
            items = [items]

        # 子规则字段
        child_rules = {k: v for k, v in rules.items() if k != list_key}
        results: list[dict] = []

        for item in items:
            entry: dict[str, Any] = {}
            if is_json:
                # 对每个列表元素应用 JsonPath
                for field, rule in child_rules.items():
                    if not rule:
                        continue
                    val = RuleEngine._jsonpath_query(item, rule)
                    entry[field] = RuleEngine._normalize_value(val)
            else:
                # HTML 列表：对每个节点片段应用子规则
                item_html = item if isinstance(item, str) else etree.tostring(
                    item, encoding="unicode"
                )
                for field, rule in child_rules.items():
                    if not rule:
                        continue
                    val = RuleEngine.extract(item_html, rule, is_json)
                    entry[field] = RuleEngine._normalize_value(val)
            results.append(entry)

        return {list_key: results}

    @staticmethod
    def _extract_list_items(content: str, list_rule: str, is_json: bool) -> Any:
        """Extract list items while preserving HTML node snippets for child rules."""
        if is_json:
            return RuleEngine.extract(content, list_rule, is_json=True)

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
            elements = soup.select(selector)
            if not elements:
                return None
            return [str(el) for el in elements]
        except Exception as e:  # noqa: BLE001
            logger.debug("列表 CSS 提取失败 rule=%r err=%s", rule, e)
            return RuleEngine.extract(content, rule, is_json=False)

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
    def _apply_operator_rules(content: str, parts: list[str], operator: str, is_json: bool) -> Any:
        """Apply Legado ``&&`` / ``||`` / ``%%`` connectors."""
        values: list[Any] = []
        for part in parts:
            value = RuleEngine.extract(content, part, is_json)
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
    def _apply_regex_replacement(content: str, rule: str, is_json: bool) -> Any:
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

        source_value = content if source_rule == "all" else RuleEngine.extract(content, source_rule, is_json)
        source_value = RuleEngine._normalize_value(source_value)

        def replace_one(value: Any) -> str:
            return re.sub(pattern, replacement, str(value), count=count)

        if isinstance(source_value, list):
            return [replace_one(item) for item in source_value]
        return replace_one(source_value)

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
        while index < len(rule):
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
