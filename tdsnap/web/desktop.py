"""Native-window mode: the same local web UI inside a real OS window.

pywebview hosts the frontend in the system webview (WebView2 on Windows),
so the packaged app behaves like a desktop application:

- it has its own window and taskbar entry instead of a browser tab;
- closing the window stops the local server — no lingering process;
- launching it again raises the existing window instead of opening a
  second copy or hitting a port conflict;
- opening and saving page sets uses the OS file dialogs directly on files
  on disk, replacing the browser upload/download flow.

If pywebview isn't installed or the OS webview runtime is missing, this
falls back to the classic browser mode so the app still works.
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import ctypes
from ctypes import wintypes
from typing import Optional

from ..errors import PagesetError
from . import server

WINDOW_TITLE = "AAC Editor"
FILE_TYPES = ("TD Snap page sets (*.sps;*.spb)", "All files (*.*)")


class NativeApi:
    """Exposed to the frontend as ``window.pywebview.api``.

    Methods return ``{"ok": ...}`` payloads instead of raising so the
    frontend handles errors the same way as HTTP responses.
    """

    def __init__(self, port):
        self.window = None  # set once the window exists
        self.port = port

    def open_pageset(self):
        """Native open dialog → load the chosen file into a new session."""
        import webview

        try:
            chosen = self.window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False, file_types=FILE_TYPES
            )
            if not chosen:
                return {"ok": True, "cancelled": True}
            path = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
            return server.open_path(path)
        except (PagesetError, OSError) as exc:
            return {"ok": False, "error": str(exc)}

    def save_pageset(self, session_id):
        """Native save dialog → write the edited copy where the user picks."""
        import webview

        try:
            suggested = server.edited_filename(session_id)
            chosen = self.window.create_file_dialog(
                webview.SAVE_DIALOG,
                directory=os.path.expanduser("~"),
                save_filename=suggested,
            )
            if not chosen:
                return {"ok": True, "cancelled": True}
            path = chosen[0] if isinstance(chosen, (list, tuple)) else chosen
            server.save_current_as(session_id, path)
            return {"ok": True, "path": path}
        except (PagesetError, OSError) as exc:
            return {"ok": False, "error": str(exc)}

    def restart_elevated_for_grid3(self):
        """Request UAC elevation, leaving this instance intact on cancel."""
        if sys.platform != "win32":
            return {"ok": False, "error": "Grid 3 editing is available on Windows only."}
        try:
            if getattr(sys, "frozen", False):
                executable = sys.executable
                arguments = ["--replace-instance", "--grid3", "--port", str(self.port)]
            else:
                executable = sys.executable
                arguments = [
                    "-m", "tdsnap.web", "--window", "--replace-instance",
                    "--grid3", "--port", str(self.port),
                ]
            execute = ctypes.windll.shell32.ShellExecuteW
            execute.argtypes = [
                wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int,
            ]
            execute.restype = wintypes.HINSTANCE
            result = execute(
                None, "runas", executable, subprocess.list2cmdline(arguments),
                os.getcwd(), 1,
            )
            if result <= 32:
                return {
                    "ok": False,
                    "error": "Administrator restart was cancelled or Windows denied it.",
                }
            # The elevated child waits for this server to release the normal
            # port. Destroying the window follows the same clean shutdown path
            # as the user closing it.
            threading.Timer(0.25, self.window.destroy).start()
            return {"ok": True, "restarting": True}
        except (AttributeError, OSError) as exc:
            return {"ok": False, "error": f"Could not request administrator access: {exc}"}


def _focus_running(port: int) -> None:
    """A copy is already running: raise its window, or open a tab to it."""
    url = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"{url}/api/focus", method="POST"), timeout=2
        ) as response:
            focused = json.load(response).get("focused", False)
    except Exception:
        focused = False
    if not focused:
        # The running copy is in browser mode; point a tab at it.
        server._open_browser(url)


def _bring_to_front(window) -> None:
    """Best-effort raise/unminimize across pywebview backends."""
    try:
        window.restore()
    except Exception:
        pass
    try:
        window.show()
    except Exception:
        pass
    try:
        window.on_top = True
        window.on_top = False
    except Exception:
        pass


def run_desktop(
    port: int = server.DEFAULT_PORT,
    *,
    replace_instance: bool = False,
    initial_provider: Optional[str] = None,
) -> None:
    """Open the app in a native window; fall back to browser mode if needed."""
    try:
        import webview
    except ImportError:
        server.run(port=port)
        return

    if replace_instance:
        deadline = time.monotonic() + 20
        while server.instance_running(port) and time.monotonic() < deadline:
            time.sleep(0.2)

    if server.instance_running(port):
        _focus_running(port)
        return

    port = server.pick_port(port)
    url = f"http://127.0.0.1:{port}"
    if initial_provider == "grid3":
        url += "/?provider=grid3"
    server.set_native(True)
    flask_server = server.make_server(port)

    serve_thread = threading.Thread(target=flask_server.serve_forever, daemon=True)
    serve_thread.start()

    api = NativeApi(port)
    try:
        window = webview.create_window(
            WINDOW_TITLE,
            url,
            js_api=api,
            width=1100,
            height=800,
            min_size=(760, 560),
        )
        api.window = window
        server.set_focus_handler(lambda: _bring_to_front(window))
        webview.start()
    except Exception:
        # No usable webview runtime — behave like browser mode with the
        # already-running server; the Quit button in the UI stops it.
        server.set_native(False)
        server.set_focus_handler(None)
        server._open_browser(url)
        serve_thread.join()
    else:
        # Window closed: stop the server and exit.
        flask_server.shutdown()
    server.cleanup_sessions()
    flask_server.server_close()
