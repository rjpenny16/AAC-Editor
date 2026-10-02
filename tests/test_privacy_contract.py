"""The privacy and security promises, pinned so they cannot quietly stop being true.

AAC Editor tells people their words never leave their computer. These tests are
that sentence made executable. They use real sockets where the promise is about
the network, and a scan of the source where the promise is about what the code is
able to do at all.

If one of these fails because you added a legitimate new feature, that is the test
doing its job: update the allow-list, and say in ``PRIVACY.md`` what now leaves the
computer, when, and why.
"""

import contextlib
import http.server
import importlib
import io
import json
import os
import pathlib
import re
import socket
import sqlite3
import stat
import sys
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from tdsnap import pageset, schema, validate
from tdsnap.errors import PagesetError
from tdsnap.web import desktop, localhttp, ollama, server

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "tdsnap"
STATIC = PACKAGE / "web" / "static"


# ---------------------------------------------------------------------------
# helpers: a tiny local HTTP server that records what reaches it


class _Recorder(http.server.BaseHTTPRequestHandler):
    def _record(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.requests.append((self.command, self.path, body))
        status, headers, payload = self.server.reply
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = _record

    def log_message(self, *_args):  # keep the test output quiet
        pass


@pytest.fixture
def recording_server():
    """Start recording HTTP servers on loopback; stop them all afterwards."""
    started = []

    def start(reply=(200, {"Content-Type": "application/json"}, b'{"models": []}')):
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
        httpd.requests = []
        httpd.reply = reply
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return httpd

    yield start
    for httpd in started:
        httpd.shutdown()
        httpd.server_close()


def _url(httpd):
    return f"http://127.0.0.1:{httpd.server_address[1]}"


@pytest.fixture
def system_proxy(recording_server):
    """Configure a proxy the way a managed network does, and return what it saw.

    urllib reads the proxy settings when a handler is built, so the loopback opener
    is rebuilt with them in place: exactly the state of an app launched on a
    computer that already had HTTP_PROXY set. Without the reload this fixture would
    configure a proxy the opener never hears about, and no test here could fail.
    """
    proxy = recording_server()
    configured = {name: _url(proxy) for name in
                  ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY")}
    cleared = ("no_proxy", "NO_PROXY")
    saved = {name: os.environ.get(name) for name in (*configured, *cleared)}
    os.environ.update(configured)
    for name in cleared:
        os.environ.pop(name, None)
    importlib.reload(localhttp)
    try:
        yield proxy
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        importlib.reload(localhttp)


# ---------------------------------------------------------------------------
# 1. Talking to Ollama on this computer never goes through a proxy


def test_the_ordinary_urllib_route_would_send_loopback_traffic_to_the_proxy(
    system_proxy, recording_server
):
    """The bug this module exists to prevent, shown on stock urllib handlers.

    With HTTP_PROXY set and no NO_PROXY, urllib hands even a request for
    127.0.0.1 to the proxy. That is the proof the guard below is guarding
    something real, and it fails loudly if the standard library ever changes.
    """
    ollama_like = recording_server()
    stock = urllib.request.build_opener()  # default handlers, built with the proxy set
    with contextlib.suppress(urllib.error.URLError, OSError):
        stock.open(f"{_url(ollama_like)}/api/tags", timeout=3).read()
    assert system_proxy.requests, "expected stock urllib to use the proxy"
    assert not ollama_like.requests


def test_ollama_status_never_goes_through_a_proxy(system_proxy, recording_server):
    fake_ollama = recording_server(
        (200, {"Content-Type": "application/json"}, b'{"models": [{"name": "llama3.2"}]}')
    )

    result = ollama.status(_url(fake_ollama))

    assert result["reachable"] is True and result["models"] == ["llama3.2"]
    assert [path for _, path, _ in fake_ollama.requests] == ["/api/tags"]
    assert system_proxy.requests == [], "the request reached the proxy"


def test_the_words_sent_to_ollama_never_go_through_a_proxy(system_proxy, recording_server):
    """The body carries the page title, what is on the page and its wording."""
    content = json.dumps({"message": {"content": json.dumps({"items": ["apple"]})}})
    fake_ollama = recording_server((200, {"Content-Type": "application/json"}, content.encode()))

    ollama.generate_words(
        "Grandma Rose's kitchen", count=3, host=_url(fake_ollama),
        existing=["private label"], style=["Wording Sample"],
    )

    assert len(fake_ollama.requests) == 1
    sent = fake_ollama.requests[0][2].decode("utf-8")
    assert "Grandma Rose's kitchen" in sent and "private label" in sent
    assert system_proxy.requests == [], "the user's vocabulary reached the proxy"


def test_instance_checks_never_go_through_a_proxy(system_proxy, recording_server):
    health = recording_server(
        (200, {"Content-Type": "application/json"}, json.dumps({"app": server.APP_ID}).encode())
    )
    port = health.server_address[1]

    assert server.instance_running(port) is True
    assert system_proxy.requests == []


# ---------------------------------------------------------------------------
# 2. A local service cannot pass a request on to anyone else


def test_a_redirect_from_a_local_service_is_not_followed(recording_server):
    elsewhere = recording_server()
    redirecting = recording_server(
        (307, {"Location": f"{_url(elsewhere)}/stolen"}, b"")
    )

    result = ollama.status(_url(redirecting))

    assert result["reachable"] is False
    assert elsewhere.requests == [], "the redirect was followed"


def test_a_redirect_never_replays_the_request_body(recording_server):
    elsewhere = recording_server()
    redirecting = recording_server((302, {"Location": f"{_url(elsewhere)}/x"}, b""))

    words, error = ollama.generate_words("Topic", host=_url(redirecting), existing=["secret"])

    assert words == [] and error
    assert elsewhere.requests == []


def test_open_loopback_refuses_anything_that_is_not_this_computer():
    for url in (
        "http://example.com/", "https://en.wikipedia.org/", "http://192.168.1.20:11434/",
        "http://localhost.evil.test/", "ftp://127.0.0.1/", "file:///etc/passwd",
    ):
        with pytest.raises(ValueError):
            localhttp.open_loopback(urllib.request.Request(url), timeout=1)  # noqa: S310


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "127.0.0.1", "127.9.9.9", "::1", "[::1]"])
def test_loopback_names_are_recognised(host):
    assert localhttp.is_loopback_host(host)


@pytest.mark.parametrize("host", [
    "", None, "example.com", "10.0.0.5", "0.0.0.0", "localhost.example.com",  # noqa: S104
    "127.0.0.1.example.com", "169.254.169.254", "::ffff:8.8.8.8",
])
def test_everything_else_is_not_loopback(host):
    assert not localhttp.is_loopback_host(host)


# ---------------------------------------------------------------------------
# 3. The code that can reach the network is a short, named list


# Modules allowed to import a networking library, and the single reason each may.
NETWORK_MODULES = {
    "tdsnap/web/localhttp.py": "loopback only: Ollama and instance checks, no proxy, no redirects",
    "tdsnap/web/ollama.py": "builds requests for localhttp; the host is validated as loopback",
    "tdsnap/web/grounding.py": "OPTIONAL Wikipedia lookup: fixed host, page title only",
    "tdsnap/web/localai.py": "one-time model download from Hugging Face, size+SHA-256 checked",
    "tdsnap/web/server.py": "builds loopback requests for localhttp; serves the local app",
    "tdsnap/web/desktop.py": "builds loopback requests for localhttp",
}
_NETWORK_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+("
    r"urllib\.request|urllib3|http\.client|httplib|requests|httpx|aiohttp|socket|ssl|"
    r"ftplib|smtplib|poplib|imaplib|telnetlib|xmlrpc|websockets?|websocket|asyncio|"
    r"socketserver|http\.server|webbrowser"
    r")\b",
    re.MULTILINE,
)


def _python_sources():
    for path in sorted(PACKAGE.rglob("*.py")):
        yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")


def test_only_the_reviewed_modules_import_a_networking_library():
    """A new import of a networking library is a new way for data to leave.

    This is not a lint rule. It is the list a person reads to answer "what in this
    app can talk to the internet?", and it has to stay short enough to read.
    """
    found = {
        name for name, source in _python_sources()
        if _NETWORK_IMPORT.search(source)
    }
    unexpected = sorted(found - set(NETWORK_MODULES))
    assert not unexpected, (
        f"{unexpected} import a networking library. If that is intended, review what "
        "it sends, add it to NETWORK_MODULES with the reason, and describe it in PRIVACY.md."
    )


def test_the_reviewed_list_has_no_stale_entries():
    sources = dict(_python_sources())
    stale = sorted(
        name for name in NETWORK_MODULES
        if name not in sources or not _NETWORK_IMPORT.search(sources[name])
    )
    assert not stale, f"{stale} no longer import a networking library; remove them"


def test_the_two_remote_hosts_are_fixed_constants():
    """The only internet hosts the app can name are written in the source."""
    from tdsnap.web import grounding, localai

    assert grounding._API == "https://en.wikipedia.org/w/api.php"
    for choice in localai.CHOICES:
        assert choice.url.startswith("https://huggingface.co/"), choice.key
        assert choice.sha256 and choice.size, f"{choice.key} must be pinned by hash and size"
        # An immutable commit, not a branch name that could change under a user.
        assert re.fullmatch(r"[0-9a-f]{40}", choice.revision), choice.key


def test_only_wikipedia_titles_can_be_looked_up():
    """The reference field can name an article, never a web address to fetch."""
    from tdsnap.web import grounding

    for hostile in (
        "https://evil.example/wiki/Cats", "http://en.wikipedia.org/wiki/Cats",
        "https://en.wikipedia.org@evil.example/wiki/Cats", "https://localhost/wiki/Cats",
        "https://en.wikipedia.org:8443/wiki/Cats", "//evil.example/wiki/Cats",
        "file:///etc/passwd", "https://169.254.169.254/latest/meta-data",
    ):
        with pytest.raises(ValueError):
            grounding.wikipedia_title(hostile)
    assert grounding.wikipedia_title("https://en.wikipedia.org/wiki/Cat") == "Cat"


def test_the_wikipedia_lookup_is_off_unless_asked_for_and_can_be_disabled(monkeypatch):
    from tdsnap.web import grounding

    monkeypatch.delenv("TDSNAP_WEB_GROUNDING", raising=False)
    assert grounding.enabled() is False
    assert grounding.enabled(requested=True) is True
    monkeypatch.setenv("TDSNAP_WEB_GROUNDING", "0")
    assert grounding.enabled(requested=True) is False


def test_the_lookup_has_no_way_to_carry_anything_but_a_title():
    """lookup() takes a topic and article titles. There is no parameter for more."""
    import inspect

    from tdsnap.web import grounding

    assert list(inspect.signature(grounding.lookup).parameters) == [
        "category", "max_chars", "requested", "title", "exclude",
    ]


# ---------------------------------------------------------------------------
# 4. The page itself cannot contact anyone else


_EXTERNAL = re.compile(r"""(?:src|href|action|data|poster|srcset)\s*=\s*["'](?:https?:)?//""", re.I)
_CSS_EXTERNAL = re.compile(r"""(?:url\(\s*["']?|@import\s+["']?)(?:https?:)?//""", re.I)
# Plain links a person can choose to follow (opening in the system browser). None of
# them is loaded by the page, and each opens only when clicked.
ALLOWED_LINKS = {
    "https://ollama.com/download",
    "https://en.wikipedia.org",
}


def test_the_page_loads_nothing_from_anywhere_else():
    """No CDN, no web font, no analytics: every script, style and image is local."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    # A tag the browser loads on its own, as opposed to a link a person may click.
    loading = re.findall(
        r"<(?:script|link|img|iframe|frame|embed|object|source|video|audio|form)\b[^>]*>",
        html, re.I,
    )
    assert loading, "expected the page to load its own script, style and logo"
    for tag in loading:
        assert not _EXTERNAL.search(tag), f"the page loads from another host: {tag}"


def test_every_link_off_the_page_is_reviewed_and_opens_only_when_clicked():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    anchors = re.findall(r"<a\b[^>]*\bhref=[\"']https?://[^>]*>", html)
    links = {re.search(r"href=[\"']([^\"']+)", anchor).group(1) for anchor in anchors}
    assert links <= ALLOWED_LINKS, f"unreviewed link(s): {sorted(links - ALLOWED_LINKS)}"
    for anchor in anchors:
        # Opens in the system browser, and tells the other site nothing about this one.
        assert 'target="_blank"' in anchor and 'rel="noopener noreferrer"' in anchor, anchor


def test_no_script_or_stylesheet_reaches_for_the_network():
    for path in STATIC.rglob("*"):
        if path.suffix not in {".js", ".css", ".html"}:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".css":
            assert not _CSS_EXTERNAL.search(text), f"{path.name} loads from another host"
        if path.suffix == ".js":
            for forbidden in ("XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon",
                              "importScripts", "navigator.serviceWorker", "RTCPeerConnection"):
                assert forbidden not in text, f"{path.name} uses {forbidden}"
            # fetch() is the app's own, same-origin and token-bearing, and lives in api.js.
            if path.name != "api.js":
                assert "fetch(" not in text, f"{path.name} calls fetch outside api.js"
            assert not re.search(r"""fetch\(\s*["'`]https?:""", text), path.name


def test_the_page_stores_nothing_in_the_browser():
    """No cookies, no localStorage, no IndexedDB. Only an opaque tab-scoped id."""
    for path in STATIC.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for store in ("localStorage", "indexedDB", "document.cookie", "caches."):
            assert store not in text, f"{path.name} uses {store}"
    users = [p.name for p in STATIC.glob("*.js") if "sessionStorage" in p.read_text(encoding="utf-8")]
    assert users == ["connect.js"], "sessionStorage is for one opaque file-session id only"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setattr(server, "_sessions", {})
    os.makedirs(server._SESSION_ROOT)
    return server.app.test_client()


def test_the_browser_is_told_to_refuse_any_other_destination(client):
    policy = client.get("/").headers["Content-Security-Policy"]
    directives = dict(part.strip().split(" ", 1) for part in policy.split(";") if part.strip())
    # Nothing may be fetched, framed, posted or loaded from anywhere but this app.
    assert directives["default-src"] == "'self'"
    assert directives["connect-src"] == "'self'"
    assert directives["script-src"] == "'self'"
    assert directives["img-src"] == "'self' data:"
    assert directives["form-action"] == "'self'"
    assert directives["object-src"] == "'none'"
    assert directives["base-uri"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    for name, value in directives.items():
        assert "http:" not in value and "https:" not in value and "*" not in value, name
    assert "'unsafe-eval'" not in policy
    assert "'unsafe-inline'" not in directives["script-src"]


def test_everything_the_api_returns_is_kept_out_of_the_browser_cache(client):
    for path in ("/api/health", "/api/config", "/api/settings", "/api/diagnostics"):
        response = client.get(path)
        assert response.headers.get("Cache-Control") == "no-store", path
    assert client.get("/api/ai/status").headers.get("Cache-Control") == "no-store"


def test_the_page_is_isolated_from_other_sites(client):
    headers = client.get("/").headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    policy = headers["Permissions-Policy"]
    for feature in ("camera", "microphone", "geolocation"):
        assert f"{feature}=()" in policy


# ---------------------------------------------------------------------------
# 5. Only this computer can reach the app, and only this app's own page can drive it


def test_the_server_binds_to_loopback_only():
    """Every place the app opens a listening socket names 127.0.0.1, and nothing offers a choice."""
    source = (PACKAGE / "web" / "server.py").read_text(encoding="utf-8")
    addresses = re.findall(r"(?:_make_server|\.bind)\(\(?\s*([^,)]+)", source)
    assert len(addresses) == 3, addresses  # the server, and the two port probes
    assert all(address.strip() == '"127.0.0.1"' for address in addresses), addresses
    for name in ("web/server.py", "web/desktop.py", "web/__main__.py"):
        text = (PACKAGE / name).read_text(encoding="utf-8")
        assert "0.0.0.0" not in text and '"::"' not in text, name  # noqa: S104
        assert "--host" not in text, f"{name} must not let anyone choose a bind address"


def test_every_state_changing_route_needs_the_per_run_token(client):
    """Enumerates the real routes, so a new one cannot be added without the check."""
    exempt = {"/api/focus"}  # a second launch raising the running window; no input
    checked = []
    for rule in server.app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        for method in sorted(rule.methods & {"POST", "PUT", "DELETE"}):
            if rule.rule in exempt:
                continue
            path = re.sub(r"<int:[^>]+>", "1", rule.rule)
            path = re.sub(r"<[^>]+>", "x" * 22, path)
            response = client.open(path, method=method)
            assert response.status_code == 403, f"{method} {rule.rule} did not need the token"
            checked.append(f"{method} {rule.rule}")
    # Not a target: a floor, so an enumeration that quietly found nothing cannot pass.
    assert len(checked) >= 20, checked
    # And the two that used to be exempt are among them.
    assert "POST /api/tdsnap/edit-plan" in checked and "POST /api/tdsnap/page" in checked


def test_the_token_is_compared_in_constant_time():
    source = (PACKAGE / "web" / "server.py").read_text(encoding="utf-8")
    assert "compare_digest" in source
    assert "!= API_TOKEN" not in source and "== API_TOKEN" not in source


def test_a_wrong_token_is_refused_like_a_missing_one(client):
    for token in ("", "wrong", server.API_TOKEN[:-1], server.API_TOKEN + "x", "é" * 10):
        response = client.delete(
            "/api/settings", headers={"X-TDSnap-Token": token.encode("utf-8").decode("latin-1")}
        )
        assert response.status_code == 403


def test_a_web_page_cannot_make_the_browser_navigate_tdsnap_with_a_plain_get(client):
    """A GET a page can forge from another origin carries no token, so it is refused."""
    for path in (
        "/api/tdsnap/page-layout?page=Home", "/api/tdsnap/status", "/api/tdsnap/vocabulary",
        "/api/grid3/status", "/api/grid3/page-layout",
    ):
        assert client.get(path).status_code == 403, path


def test_a_hostile_host_header_is_refused(client):
    for host in ("evil.example", "127.0.0.1.evil.example", "localhost.evil.example:8765"):
        assert client.get("/api/health", headers={"Host": host}).status_code == 403


# ---------------------------------------------------------------------------
# 6. Working copies of a page set stay private to the person who opened it


@pytest.mark.parametrize("hostile", [
    "..", ".", "../..", "a/../..", "%2e%2e", "a b", "a.b", "..\\..", "x" * 65, "", "é",
])
def test_a_session_id_can_never_be_a_path(hostile):
    with pytest.raises(PagesetError):
        server._session_dir(hostile)
    assert server._rehydrate_session(hostile) is None


def test_a_crafted_session_id_cannot_delete_the_folder_above_the_session_root(
    client, tmp_path, monkeypatch
):
    """The traversal this guards: '..' resolving to the temp directory itself."""
    victim = tmp_path
    (victim / "current").write_bytes(b"x")
    (victim / "meta.json").write_text('{"filename": "x.sps"}', encoding="utf-8")
    keepsake = victim / "keepsake.txt"
    keepsake.write_text("do not delete", encoding="utf-8")

    for session in ("..", "%2e%2e"):
        client.get(f"/api/pageset/{session}", headers={"X-TDSnap-Token": server.API_TOKEN})
        client.post(f"/api/pageset/{session}/close", headers={"X-TDSnap-Token": server.API_TOKEN})

    assert keepsake.exists()
    assert (victim / "current").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_the_session_folder_is_private_to_this_user(tmp_path, monkeypatch):
    root = tmp_path / "root"
    monkeypatch.setattr(server, "_SESSION_ROOT", str(root))
    monkeypatch.setattr(server, "_sessions", {})
    session_id, session_dir = server._new_session_dir()
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(session_dir).st_mode) == 0o700
    assert session_id and os.path.dirname(session_dir) == str(root)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_a_loose_session_folder_is_tightened_not_trusted_blindly(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)  # noqa: S103 - deliberately loose, to show it is tightened
    monkeypatch.setattr(server, "_SESSION_ROOT", str(root))
    monkeypatch.setattr(server, "_sessions", {})
    server._new_session_dir()
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700


@pytest.mark.skipif(os.name == "nt", reason="symlinks and POSIX ownership")
def test_a_symlinked_session_folder_is_refused(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = tmp_path / "root"
    link.symlink_to(elsewhere, target_is_directory=True)
    monkeypatch.setattr(server, "_SESSION_ROOT", str(link))
    monkeypatch.setattr(server, "_sessions", {})
    with pytest.raises(PagesetError, match="not safe"):
        server._new_session_dir()
    assert os.listdir(elsewhere) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX uid")
def test_each_user_gets_a_session_folder_of_their_own():
    assert server._session_root_name() == f"tdsnap-editor-{os.getuid()}"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_the_settings_file_and_its_folder_are_private(tmp_path, monkeypatch):
    from tdsnap.web import settings

    folder = tmp_path / "data"
    monkeypatch.setattr(settings, "_data_dir", lambda: str(folder))
    settings.save({"provider": "tdsnap"}, None)
    assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(folder / "settings.json").st_mode) == 0o600


def test_leftover_working_copies_are_removed_when_the_app_exits_normally(tmp_path, monkeypatch):
    import atexit

    import werkzeug.serving

    registered = []
    stand_in = SimpleNamespace(shutdown=lambda: None)
    monkeypatch.setattr(atexit, "register", lambda fn, *a, **k: registered.append(fn))
    monkeypatch.setattr(server, "_cleanup_registered", False)
    monkeypatch.setattr(server, "_SESSION_ROOT", str(tmp_path / "root"))
    # make_server records the server's shutdown in module state; keep that out of
    # every other test, and never start a real server here.
    monkeypatch.setattr(server, "_runtime", {"native": False, "focus": None, "shutdown": None})
    monkeypatch.setattr(werkzeug.serving, "make_server", lambda *args, **kwargs: stand_in)

    assert server.make_server(0) is stand_in
    assert server.cleanup_sessions in registered


# ---------------------------------------------------------------------------
# 7. A person's real TD Snap page set is only ever read


def test_the_open_page_set_is_never_opened_for_writing():
    """Every read of TD Snap's own file asks SQLite for read-only access."""
    offenders = []
    for name in ("tdsnap/live.py", "tdsnap/grid3.py", "tdsnap/cli.py", "tdsnap/web/server.py"):
        source = (ROOT / name).read_text(encoding="utf-8")
        for match in re.finditer(r"sqlite3\.connect\(", source):
            call = source[match.start():match.start() + 160]
            if "mode=ro" not in call:
                offenders.append(f"{name}: {call.splitlines()[0]}")
    assert not offenders, offenders


def test_only_the_private_working_copy_is_opened_read_write():
    source = (PACKAGE / "pageset.py").read_text(encoding="utf-8")
    writers = re.findall(r"sqlite3\.connect\((?!f?\"file:)([^)]*)\)", source)
    assert writers == ["working_copy"]


# ---------------------------------------------------------------------------
# 8. A hostile page set cannot do more than fail


def _hostile_page_set(path, table_name):
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE {schema.quote_identifier(table_name)} (x INTEGER)")
    conn.execute(f"INSERT INTO {schema.quote_identifier(table_name)} VALUES (1)")
    conn.commit()
    return conn


@pytest.mark.parametrize("name", [
    'a"b', 'Page"; DROP TABLE Page; --', "x y", "Button) UNION SELECT 1 --", "é", "'quoted'",
])
def test_a_table_named_by_a_hostile_file_stays_just_a_name(tmp_path, name):
    conn = _hostile_page_set(str(tmp_path / "evil.sps"), name)
    assert schema.table_counts(conn) == {name: 1}
    snapshot = validate.table_snapshot(conn)
    assert snapshot[name]["count"] == 1
    # The one place a table name is not quoted for use refuses anything but a plain name.
    if not name.replace("_", "").isalnum():
        with pytest.raises(PagesetError, match="Suspicious table name"):
            schema.columns(conn, name)
    conn.close()


def test_quote_identifier_doubles_embedded_quotes():
    assert schema.quote_identifier("Page") == '"Page"'
    assert schema.quote_identifier('a"b') == '"a""b"'


def test_a_files_own_triggers_cannot_reach_a_function_the_app_registers(tmp_path):
    """What trusted_schema=OFF buys: a file's schema cannot call the app's own functions.

    Python registers no such functions today, so this is a seatbelt, not a wall (see
    ``harden_untrusted``). The mechanism is shown with a function the test registers.
    """
    path = str(tmp_path / "evil.sps")
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE T (x INTEGER); CREATE TABLE Loot (v TEXT);"
        "CREATE TRIGGER grab AFTER INSERT ON T BEGIN INSERT INTO Loot VALUES (leak()); END;"
    )
    conn.commit()
    conn.close()

    def open_with(harden):
        opened = sqlite3.connect(path)
        opened.create_function("leak", 0, lambda: "private")
        if harden:
            pageset.harden_untrusted(opened)
        return opened

    unguarded = open_with(harden=False)
    unguarded.execute("INSERT INTO T VALUES (1)")  # the trigger fires
    assert unguarded.execute("SELECT v FROM Loot").fetchone() == ("private",)
    unguarded.close()

    guarded = open_with(harden=True)
    assert guarded.execute("PRAGMA trusted_schema").fetchone()[0] == 0
    assert guarded.execute("PRAGMA cell_size_check").fetchone()[0] == 1
    with pytest.raises(sqlite3.Error, match="unsafe use of leak"):
        guarded.execute("INSERT INTO T VALUES (2)")
    guarded.close()


def test_every_working_copy_the_editor_writes_to_is_hardened(seeded_source, tmp_path):
    with pageset.Pageset(seeded_source, working_copy=str(tmp_path / "copy")) as editing:
        assert editing.conn.execute("PRAGMA trusted_schema").fetchone()[0] == 0
        assert editing.conn.execute("PRAGMA cell_size_check").fetchone()[0] == 1


def test_the_genuine_schema_is_unaffected_by_that_hardening(tmp_path):
    """The real TD Snap 4.13 schema: tables and indexes with constant defaults."""
    snapshot = (ROOT / "tests" / "fixtures" / "schema_snapshot.sql").read_text(encoding="utf-8")
    assert not re.search(r"CREATE\s+(TEMP\s+|TEMPORARY\s+)?(TRIGGER|VIEW|VIRTUAL)", snapshot, re.I)
    path = str(tmp_path / "real.sps")
    conn = sqlite3.connect(path)
    pageset.harden_untrusted(conn)
    conn.executescript(snapshot)
    conn.commit()
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_a_board_file_cannot_write_outside_memory():
    """OBF zips are read in memory, member by member, and never extracted."""
    source = (PACKAGE / "obf.py").read_text(encoding="utf-8")
    assert "extractall" not in source and ".extract(" not in source


# ---------------------------------------------------------------------------
# 9. The desktop window keeps nothing and lets no web page reach its bridge


def test_the_desktop_window_is_started_in_private_mode_with_links_kept_outside(monkeypatch):
    calls = {}

    class FakeWindow:
        def restore(self): ...
        def show(self): ...

    link_settings = {"OPEN_EXTERNAL_LINKS_IN_BROWSER": False}

    class FakeWebview:
        settings = link_settings
        OPEN_DIALOG = 10
        SAVE_DIALOG = 30

        @staticmethod
        def create_window(*args, **kwargs):
            calls["window"] = (args, kwargs)
            return FakeWindow()

        @staticmethod
        def start(*args, **kwargs):
            calls["start"] = (args, kwargs)

    class FakeServer:
        def serve_forever(self): ...
        def shutdown(self): ...
        def server_close(self): ...

    monkeypatch.setitem(sys.modules, "webview", FakeWebview)
    # run_desktop marks the app native and installs a focus handler; keep that
    # module state from leaking into the tests that read it afterwards.
    monkeypatch.setattr(server, "_runtime", {"native": False, "focus": None, "shutdown": None})
    monkeypatch.setattr(desktop.server, "instance_running", lambda port: False)
    monkeypatch.setattr(desktop.server, "pick_port", lambda port: port)
    monkeypatch.setattr(desktop.server, "make_server", lambda port: FakeServer())
    monkeypatch.setattr(desktop.server, "cleanup_sessions", lambda: None)
    monkeypatch.setattr(desktop.threading, "Thread", lambda **kw: type("T", (), {
        "start": lambda self: None, "join": lambda self: None})())

    desktop.run_desktop(port=8765)

    assert calls["start"][1] == {"private_mode": True}
    assert link_settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True
    url = calls["window"][0][1]
    assert url.startswith("http://127.0.0.1:")


def test_the_native_bridge_exposes_only_its_three_documented_actions():
    public = sorted(name for name in vars(desktop.NativeApi) if not name.startswith("_"))
    assert public == ["open_pageset", "restart_elevated_for_grid3", "save_pageset"]


# ---------------------------------------------------------------------------
# 10. The support report cannot carry what a person typed or opened


def test_the_support_report_is_built_from_an_allow_list():
    source = (PACKAGE / "web" / "diagnostics.py").read_text(encoding="utf-8")
    assert "_LIVE_KEYS" in source and "_GRID3_KEYS" in source
    for private in ("labels", "pages", "grid_set", "user"):
        assert f'"{private}"' not in source.split("_GRID3_KEYS = (")[1].split(")")[0]


def test_error_responses_do_not_echo_request_bodies(client):
    marker = "SECRET-VOCABULARY-123"
    response = client.post(
        "/api/ai/words", json={"category": marker, "kind": "bogus"},
        headers={"X-TDSnap-Token": server.API_TOKEN},
    )
    assert response.status_code == 400
    assert marker not in response.get_data(as_text=True)


def test_a_malformed_upload_leaves_nothing_on_disk(client):
    response = client.post(
        "/api/pageset", data={"file": (io.BytesIO(b"not sqlite"), "../../evil.sps")},
        headers={"X-TDSnap-Token": server.API_TOKEN},
    )
    assert response.status_code == 400
    assert os.listdir(server._SESSION_ROOT) == []


# ---------------------------------------------------------------------------
# 11. What the documents promise is what the code does


# Every host a person can be told about. Anything else in the source is a bug in
# this list or a new way for data to leave, and a reviewer has to decide which.
DOCUMENTED_REMOTE_HOSTS = {"huggingface.co", "en.wikipedia.org"}
# Addresses that appear in the source without being somewhere the app connects to.
NOT_CONNECTIONS = {
    "github.com",        # the User-Agent string names the project; it is not fetched
    "localhost", "127.0.0.1",
    "www.w3.org",        # an XML namespace in an SVG, not a request
    "www.openboardformat.org",  # the format's home page, named in a docstring
}


def test_every_web_address_in_the_python_source_is_documented_or_inert():
    found = set()
    for _name, source in _python_sources():
        for host in re.findall(r"https?://([A-Za-z0-9.-]+)", source):
            found.add(host.lower())
    unexplained = sorted(found - DOCUMENTED_REMOTE_HOSTS - NOT_CONNECTIONS)
    assert not unexplained, (
        f"{unexplained} appear in the source. If the app now connects there, document it in "
        "PRIVACY.md and the What AAC Editor saves panel, then add it to DOCUMENTED_REMOTE_HOSTS."
    )


def test_the_privacy_page_names_exactly_the_hosts_the_code_uses():
    privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    for host in DOCUMENTED_REMOTE_HOSTS:
        assert host in privacy, f"PRIVACY.md does not mention {host}"
        assert host in page, f"the What AAC Editor saves panel does not mention {host}"
    # No other site is named as something the app talks to.
    named = set(re.findall(r"`((?:[a-z0-9-]+\.)+(?:com|org|net|io|co|dev|app))`", privacy))
    assert named == DOCUMENTED_REMOTE_HOSTS, sorted(named)


def test_the_folders_the_documents_name_are_the_ones_the_code_uses():
    from tdsnap.web import settings

    privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
    assert os.path.basename(settings._data_dir()) == "tdsnap-editor"
    assert "tdsnap-editor" in privacy and "models" in privacy
    assert "settings.json" in privacy and os.path.basename(settings.settings_path()) == "settings.json"
    assert server._session_root_name().startswith("tdsnap-editor")


def test_the_documents_and_the_code_agree_about_the_two_opt_ins():
    privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # The unfinished page is off until chosen: in the saved-preference schema and in the docs.
    assert server._PREFERENCE_SCHEMA["draft_autosave"] == {"bool": True}
    assert "Keep an unfinished page" in privacy and "off" in privacy.lower()
    # The Wikipedia tick is not something the app can remember.
    assert "ai_grounding" not in server._PREFERENCE_SCHEMA
    assert "off again each time you open" in privacy
    assert "PRIVACY.md" in readme


def test_the_privacy_documents_avoid_promises_the_code_cannot_keep():
    """Words that overclaim. A real absolute needs a test of its own before it comes back."""
    for name in ("PRIVACY.md",):
        text = (ROOT / name).read_text(encoding="utf-8")
        for overclaim in ("100% secure", "unhackable", "completely secure", "military",
                          "guarantee", "impossible to"):
            assert overclaim.lower() not in text.lower(), f"{name} says {overclaim!r}"


# ---------------------------------------------------------------------------
# 12. A real process, stopped the ways people stop one, leaves nothing behind


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _upload(port, path):
    """POST *path* to a running app as a page set, the way the browser does."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f"http://127.0.0.1:{port}"
    token = json.load(opener.open(f"{base}/api/config", timeout=5))["token"]
    boundary = "----privacycontract"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"t.sps\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + pathlib.Path(path).read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(  # noqa: S310 - our own loopback server
        f"{base}/api/pageset", data=body, method="POST",
        headers={"X-TDSnap-Token": token,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return json.load(opener.open(request, timeout=10))


@pytest.mark.skipif(os.name == "nt", reason="POSIX signals")
@pytest.mark.parametrize("sig", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_stopping_the_app_removes_the_working_copy_of_an_open_page_set(
    sig, seeded_source, tmp_path
):
    import signal
    import subprocess
    import time

    temp = tmp_path / "tmp"
    temp.mkdir()
    port = _free_port()
    env = {**os.environ, "TMPDIR": str(temp), "XDG_DATA_HOME": str(tmp_path / "data"),
           "TDSNAP_WEB_GROUNDING": "0"}
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        env.pop(name, None)
    process = subprocess.Popen(
        [sys.executable, "-m", "tdsnap.web", "--no-browser", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 20
        while True:
            try:
                opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1).read()
                break
            except (urllib.error.URLError, OSError):
                assert time.monotonic() < deadline, "the app did not start"
                time.sleep(0.2)

        assert _upload(port, seeded_source)["ok"] is True
        roots = list(temp.glob("tdsnap-editor*"))
        assert len(roots) == 1 and len(list(roots[0].iterdir())) == 1, "a working copy is expected"

        process.send_signal(getattr(signal, sig))
        process.wait(timeout=15)

        assert not list(roots[0].iterdir()), f"{sig} left a working copy of the page set behind"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


# ---------------------------------------------------------------------------
# 13. Looking does not leave anything behind


def test_checking_on_the_ai_model_creates_no_folder_until_a_download_starts(
    tmp_path, monkeypatch
):
    """On a fresh install, opening the suggestions panel must not put a folder on disk."""
    from tdsnap.web import localai

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    localai.status()
    localai.is_downloaded()
    localai.model_path()
    localai.downloaded_keys()
    assert list(tmp_path.iterdir()) == [], "a status check created files"

    created = localai._models_dir(create=True)
    assert os.path.isdir(created)
    if os.name != "nt":
        assert stat.S_IMODE(os.stat(created).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(tmp_path / "tdsnap-editor").st_mode) == 0o700


def test_a_fresh_start_of_the_app_and_the_settings_panel_write_nothing(client, tmp_path, monkeypatch):
    """Nothing is written by reading: the settings and AI status endpoints are read-only."""
    from tdsnap.web import settings

    data = tmp_path / "data"
    monkeypatch.setattr(settings, "_data_dir", lambda: str(data / "tdsnap-editor"))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("LOCALAPPDATA", str(data))
    token = {"X-TDSnap-Token": server.API_TOKEN}

    for path in ("/api/settings", "/api/ai/status", "/api/health", "/api/config", "/api/diagnostics"):
        client.get(path, headers=token)
    assert not data.exists() or list(data.rglob("*")) == [], "reading wrote something to disk"
