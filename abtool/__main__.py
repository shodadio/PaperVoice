"""Command line entry point: `abtool serve`."""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

from . import net, store, tts
from .app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="abtool",
        description="Turn EPUB, PDF and other documents into downloadable audiobooks, using this machine.",
    )
    parser.add_argument("command", nargs="?", default="serve", choices=["serve"], help="serve (default)")
    parser.add_argument("--port", type=int, default=8765, help="port to listen on (default 8765)")
    parser.add_argument("--lan", action="store_true", help="let your iPhone or iPad reach the library over Wi-Fi")
    parser.add_argument("--host", default=None, help="bind address (default 127.0.0.1, or 0.0.0.0 with --lan)")
    parser.add_argument("--token", default=None, help="fixed access token instead of a random one")
    parser.add_argument("--no-auth", action="store_true", help="disable the access token (only for trusted networks)")
    parser.add_argument("--allow-host", action="append", default=[], metavar="HOST", help="extra Host header to accept")
    parser.add_argument("--data", default=None, help="library folder (default ./library)")
    parser.add_argument("--max-upload-mb", type=int, default=200, help="largest accepted upload in MB")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
    loopback = host in ("127.0.0.1", "localhost", "::1")
    require_token = (args.lan or not loopback) and not args.no_auth
    token = args.token or secrets.token_urlsafe(12)
    data_dir = Path(args.data).expanduser() if args.data else Path.cwd() / "library"

    store.init(data_dir)
    app = create_app(
        data_dir=data_dir,
        token=token,
        allow_hosts=net.allowed_hosts(args.allow_host),
        require_token=require_token,
        max_upload_mb=args.max_upload_mb,
    )
    net.print_banner(
        urls_list=net.urls(args.port, args.lan or not loopback),
        token=token,
        lan=args.lan,
        require_token=require_token,
        engine=tts.default_engine_name(),
        data_dir=str(data_dir),
    )

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is missing. Run: pip install -e .", file=sys.stderr)
        return 1

    uvicorn.run(app, host=host, port=args.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
