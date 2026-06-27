"""HTTP client behavior tests."""

from types import SimpleNamespace

from app.core.http_client import HttpClient


def test_decode_body_prefers_html_meta_charset_when_header_is_wrong():
    raw = '<meta charset="big5"><title>鬥破蒼穹</title>'.encode("big5")
    resp = SimpleNamespace(charset="utf-8")

    decoded = HttpClient._decode_body(raw, resp)

    assert "鬥破蒼穹" in decoded


def test_decode_body_keeps_header_charset_when_html_meta_is_wrong():
    raw = '<meta charset="big5"><title>鬥破蒼穹</title>'.encode("utf-8")
    resp = SimpleNamespace(charset="utf-8")

    decoded = HttpClient._decode_body(raw, resp)

    assert "鬥破蒼穹" in decoded
