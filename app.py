"""ccdeck — desktop launcher.

Starts uvicorn on a background thread and opens the UI in a native pywebview
(WebView2) window. When pywebview is unavailable, opens the default browser
instead (via --browser or automatic fallback).

Usage:
    python app.py             # desktop window
    python app.py --browser   # open in the browser
    python app.py --port 9000
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
import urllib.request

import uvicorn


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
    parser = argparse.ArgumentParser(description="ccdeck")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--browser", action="store_true",
                        help="open in the default browser instead of pywebview")
    args = parser.parse_args()

    port = find_free_port(args.port)
    url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config("server.main:app", host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    if not wait_for_server(url):
        raise SystemExit("Failed to start the server")
    print(f"ccdeck: {url}")

    use_browser = args.browser
    if not use_browser:
        try:
            import webview
            window = webview.create_window(
                "ccdeck", url, width=1360, height=880,
                background_color="#14151a")
            webview.start()
        except Exception as e:
            print(f"Could not start pywebview ({e}); opening in the browser.")
            use_browser = True

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
    main()
