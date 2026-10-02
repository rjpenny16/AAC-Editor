"""HTTP to this computer, and only to this computer.

``urllib`` sends a request through ``HTTP_PROXY`` or the Windows proxy settings
whatever the destination, loopback included, unless ``NO_PROXY`` happens to
exempt it. For a request to a local Ollama server that is a privacy failure,
not a quirk: the body carries the page title, the labels already on the page and
a sample of the page set's wording, and a proxy would receive all of it.

Everything that talks to a loopback address goes through :func:`open_loopback`
instead, which

* never uses a proxy,
* refuses any address that is not loopback, so the guarantee holds even if a
  caller forgets to validate its host first, and
* refuses to follow a redirect, so a local service cannot send the request on
  to somebody else.

The two requests that are *meant* to leave the computer (the one-time model
download and the optional Wikipedia lookup) deliberately do not use this module:
on a managed network they need the system proxy to work at all.
"""

import ipaddress
from typing import Optional
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class _RefuseRedirects(HTTPRedirectHandler):
    """Turn every 3xx into an ``HTTPError`` instead of a second request."""

    def redirect_request(self, *_args, **_kwargs):
        return None


# An empty ProxyHandler replaces the default one, so no proxy is ever consulted.
_OPENER = build_opener(ProxyHandler({}), _RefuseRedirects())


def is_loopback_host(hostname: Optional[str]) -> bool:
    """True for ``localhost`` and loopback IP literals, and nothing else."""
    if not hostname:
        return False
    name = hostname.strip("[]").lower()
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def open_loopback(request: Request, timeout: float):
    """Open *request*, which must target a loopback address, without a proxy."""
    parts = urlsplit(request.full_url)
    if parts.scheme.lower() not in {"http", "https"} or not is_loopback_host(parts.hostname):
        raise ValueError("Only requests to this computer are allowed here.")
    return _OPENER.open(request, timeout=timeout)
