"""Command line entry point for the loopback-only local Web server."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MiniCode local Web console.")
    parser.add_argument("--port", type=int, default=8765, help="Loopback port (default: 8765)")
    parser.add_argument("--workspace", default=".", help="Workspace directory (default: current directory)")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Web dependencies are missing. Install with: pip install -e '.[web]'") from exc

    from minicode.web.app import create_app

    workspace = Path(args.workspace).resolve()
    uvicorn.run(
        create_app(workspace=workspace),
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
