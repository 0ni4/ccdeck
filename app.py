"""cc-home — desktop launcher.

Starts uvicorn on a background thread and opens the UI in a native pywebview
(WebView2) window. When pywebview is unavailable, opens the default browser
instead (via --browser or automatic fallback).

Usage:
    python app.py             # desktop window
    python app.py --browser   # open in the browser
    python app.py --no-window # run the server only (no window/browser)
    python app.py --port 9000
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import urllib.request

# In a windowed (console=False) PyInstaller build there is no console, so
# sys.stdout / sys.stderr are None. uvicorn's log config calls
# sys.stdout.isatty() at startup and would crash — give them a sink.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import uvicorn

from server.main import app as fastapi_app


def find_free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def wait_for_server(url: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="cc-home")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--browser", action="store_true",
                        help="open in the default browser instead of pywebview")
    parser.add_argument("--no-window", action="store_true",
                        help="run the server only, without opening any window")
    args = parser.parse_args()

    port = find_free_port(args.port)
    url = f"http://127.0.0.1:{port}"

    # pass the app object directly (not an import string) so it resolves in a
    # frozen build and no reloader/worker subprocess is spawned
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    if not wait_for_server(url):
        raise SystemExit("Failed to start the server")
    print(f"cc-home: {url}")

    use_browser = args.browser
    if not args.no_window and not use_browser:
        try:
            import webview
            webview.create_window(
                "cc-home", url, width=1360, height=880,
                background_color="#14151a")
            webview.start()
        except Exception as e:
            print(f"Could not start pywebview ({e}); opening in the browser.")
            use_browser = True

    if args.no_window or use_browser:
        if use_browser:
            import webbrowser
            webbrowser.open(url)
        try:
            while thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    server.should_exit = True
    thread.join(timeout=5)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()  # required for frozen (PyInstaller) builds
    main()
