import argparse

parser = argparse.ArgumentParser(prog="tdsnap.web",
                                 description="TD Snap Page Builder web UI")
parser.add_argument("--port", type=int, default=8765)
parser.add_argument("--no-browser", action="store_true",
                    help="don't open a browser tab automatically")
parser.add_argument("--window", action="store_true",
                    help="open in a native window instead of the browser "
                         "(requires the 'desktop' extra: pip install .[desktop])")
args = parser.parse_args()

if args.window:
    from .desktop import run_desktop

    run_desktop(port=args.port)
else:
    from .server import run

    run(port=args.port, open_browser=not args.no_browser)
