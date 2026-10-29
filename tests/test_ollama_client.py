"""Ollama client: every failure comes back as a message, never an exception."""

import io
import json
from urllib.error import HTTPError, URLError

import pytest

from tdsnap.web import ollama


class _Response:
    def __init__(self, body: bytes, status: int = 200):
        self._body, self.status = body, status

    def read(self, limit=-1):
        return self._body[:limit] if limit >= 0 else self._body

    def getcode(self):
        return self.status

    def close(self):
        pass


def _serve(monkeypatch, body=b"{}", status=200, error=None):
    def fake(request, timeout):
        if error is not None:
            raise error
        return _Response(body, status)

    monkeypatch.setattr(ollama.localhttp, "open_loopback", fake)


def _generate():
    return ollama.generate_words("Snacks", count=3)


def test_status_lists_models(monkeypatch):
    body = json.dumps({"models": [{"name": "llama3.2"}, {"name": ""}, "junk"]}).encode()
    _serve(monkeypatch, body)
    result = ollama.status()
    assert result == {"reachable": True, "models": ["llama3.2"], "message": "Connected."}


def test_status_without_models_suggests_a_pull(monkeypatch):
    _serve(monkeypatch, b'{"models": []}')
    assert "ollama pull" in ollama.status()["message"]


@pytest.mark.parametrize(
    "body",
    [b"[]", b'{"models": 3}', b"not json", b"\xff\xfe", b"[" * 100_000],
)
def test_status_treats_malformed_replies_as_unreachable(monkeypatch, body):
    _serve(monkeypatch, body)
    result = ollama.status()
    assert result["reachable"] is False and result["models"] == []


def test_status_reports_non_200_and_connection_errors(monkeypatch):
    _serve(monkeypatch, b"{}", status=503)
    assert "503" in ollama.status()["message"]
    _serve(monkeypatch, error=URLError("refused"))
    assert "URLError" in ollama.status()["message"]


def test_status_rejects_a_remote_host():
    result = ollama.status("http://example.com")
    assert result["reachable"] is False


def test_http_error_body_is_read_as_a_response(monkeypatch):
    error = HTTPError("http://localhost", 404, "nope", {}, io.BytesIO(b"no such model"))
    _serve(monkeypatch, error=error)
    words, message = _generate()
    assert words == [] and "404" in message and "no such model" in message


def test_oversized_response_is_refused(monkeypatch):
    _serve(monkeypatch, b"x" * (ollama.MAX_RESPONSE_BYTES + 1))
    words, message = _generate()
    assert words == [] and "ValueError" in message


def test_generate_reports_unreachable_server(monkeypatch):
    _serve(monkeypatch, error=ConnectionRefusedError())
    words, message = _generate()
    assert words == [] and "ConnectionRefusedError" in message


@pytest.mark.parametrize("body", [b"nope", b"[]", b'{"message": "text"}', b"\xff"])
def test_generate_rejects_unparseable_replies(monkeypatch, body):
    _serve(monkeypatch, body)
    words, message = _generate()
    assert words == [] and "valid JSON" in message


def test_generate_rejects_a_bad_host_before_any_request(monkeypatch):
    _serve(monkeypatch, error=AssertionError("must not connect"))
    words, message = ollama.generate_words("Snacks", host="http://example.com")
    assert words == [] and "loopback" in message


@pytest.mark.parametrize(
    "host",
    ["http://localhost:0", "http://localhost:99999", "http://local host", None, ""],
)
def test_normalize_host_rejects_bad_ports_and_types(host):
    with pytest.raises(ValueError):
        ollama.normalize_host(host)
