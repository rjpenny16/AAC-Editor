"""Entry point for the packaged (PyInstaller) app.

Double-clicking the executable starts the local web server and opens the
browser — same as `python -m tdsnap.web`, with multiprocessing guarded for
frozen Windows builds (llama-cpp workers would otherwise respawn the GUI).
"""

import multiprocessing
import os
import sys


def main() -> None:
    multiprocessing.freeze_support()
    # Windowed builds have no console; writes to a None stream would crash
    # Flask/llama.cpp logging.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    from tdsnap.web.server import run

    run()


if __name__ == "__main__":
    main()
