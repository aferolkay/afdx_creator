"""Entry point: `python -m afdx_generator.main` or `afdx-generator`."""

from __future__ import annotations

import argparse
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the afdx_generator web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes.")
    args = parser.parse_args()

    import uvicorn

    url = f"http://{args.host}:{args.port}/"
    print(f"\n  afdx_generator -> {url}\n")
    if not args.no_browser and not args.reload:
        try:
            webbrowser.open(url)
        except Exception:
            pass  # headless environment: the URL above is enough

    uvicorn.run(
        "afdx_generator.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
