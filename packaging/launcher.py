"""Entry point for the packaged (PyInstaller) app.

Double-clicking the executable opens the app in its own native window
(falling back to the browser if the OS webview runtime is missing) — same
as `python -m tdsnap.web --window`, with multiprocessing guarded for
frozen Windows builds (llama-cpp workers would otherwise respawn the GUI).
"""

import multiprocessing
import os
import sys
import argparse


def main() -> None:
    multiprocessing.freeze_support()
    # Windowed builds have no console; writes to a None stream would crash
    # Flask/llama.cpp logging.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    from tdsnap.web.desktop import run_desktop

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--replace-instance", action="store_true")
    parser.add_argument("--grid3", action="store_true")
    args, _ = parser.parse_known_args()
    run_desktop(
        port=args.port,
        replace_instance=args.replace_instance,
        initial_provider="grid3" if args.grid3 else None,
    )


if __name__ == "__main__":
    main()
