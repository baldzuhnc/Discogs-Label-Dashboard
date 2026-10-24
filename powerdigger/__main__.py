import argparse
import threading
import webbrowser

from .config import DB_PATH, LEGACY_DATA


def main():
    parser = argparse.ArgumentParser(prog="powerdigger", description="Power Digger 3000")
    sub = parser.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="run the web app (default)")
    serve.add_argument("--port", type=int, default=8300)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--no-browser", action="store_true")
    sub.add_parser("import-legacy", help="import the old Data/<Label>/raw_*.json dumps")
    args = parser.parse_args()

    if args.cmd == "import-legacy":
        from .db import DB
        from .legacy_import import import_legacy

        n = import_legacy(DB(DB_PATH), LEGACY_DATA)
        print(f"Imported {n} labels into {DB_PATH}")
        return

    import uvicorn

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8300)
    if not getattr(args, "no_browser", False):
        threading.Timer(1.2, webbrowser.open, (f"http://{host}:{port}",)).start()
    uvicorn.run("powerdigger.server:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
