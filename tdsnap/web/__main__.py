import argparse

from .server import run

parser = argparse.ArgumentParser(prog="tdsnap.web",
                                 description="TD Snap Page Builder web UI")
parser.add_argument("--port", type=int, default=8765)
parser.add_argument("--no-browser", action="store_true",
                    help="don't open a browser tab automatically")
args = parser.parse_args()
run(port=args.port, open_browser=not args.no_browser)
