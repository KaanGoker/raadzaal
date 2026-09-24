"""Screenshots of the live site for assets/ and the README. Runs a local server on docs/ and drives Chromium.

usage: python scripts/screenshots.py [session_id]   (needs playwright and chromium)
"""
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = ROOT / "assets"


def serve(port: int):
    socketserver.TCPServer.allow_reuse_address = True
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(DOCS), **k)  # noqa: E731
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    from playwright.sync_api import sync_playwright
    ASSETS.mkdir(exist_ok=True)
    httpd = serve(0)  # any free port
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}/index.html"
    import json
    index = json.loads((DOCS / "data" / "index.json").read_text(encoding="utf-8"))
    sid = sys.argv[1] if len(sys.argv) > 1 else index["sessions"][0]["id"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width, tag in ((1280, "1280"), (390, "390")):
            pg = b.new_page(viewport={"width": width, "height": 900})
            pg.goto(base + "#/"); pg.wait_for_timeout(1800)
            pg.screenshot(path=str(ASSETS / f"home-{tag}.png"), full_page=(width == 390))
            pg.goto(base + f"#/s/{sid}"); pg.wait_for_timeout(1500)
            pg.locator("details.item").first.click(); pg.wait_for_timeout(400)
            pg.screenshot(path=str(ASSETS / f"session-{tag}.png"), full_page=(width == 390))
            if width == 1280:
                pg.goto(base + "#/zoek?q=fietspad"); pg.wait_for_timeout(2500)
                pg.screenshot(path=str(ASSETS / "search-1280.png"))
                pg.goto(base + "#/methode"); pg.wait_for_timeout(1200)
                pg.screenshot(path=str(ASSETS / "method-1280.png"))
            print("scrollWidth", width, pg.evaluate("document.documentElement.scrollWidth"))
        b.close()
    httpd.shutdown()
    print("written to", ASSETS)


if __name__ == "__main__":
    main()
