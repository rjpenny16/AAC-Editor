import argparse

parser = argparse.ArgumentParser(prog="tdsnap.web",
                                 description="AAC Editor web UI")
parser.add_argument("--port", type=int, default=8765)
parser.add_argument("--no-browser", action="store_true",
                    help="don't open a browser tab automatically")
parser.add_argument("--window", action="store_true",
                    help="open in a native window instead of the browser "
                         "(requires the 'desktop' extra: pip install .[desktop])")
parser.add_argument("--replace-instance", action="store_true",
                    help=argparse.SUPPRESS)
parser.add_argument("--grid3", action="store_true", help=argparse.SUPPRESS)
args = parser.parse_args()

if args.window:
    from .desktop import run_desktop

    run_desktop(
        port=args.port,
        replace_instance=args.replace_instance,
        initial_provider="grid3" if args.grid3 else None,
    )
else:
    from .server import run

    run(port=args.port, open_browser=not args.no_browser)
