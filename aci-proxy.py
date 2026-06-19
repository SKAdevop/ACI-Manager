#!/usr/bin/env python3
"""
aci-proxy.py — Combined ACI CORS Proxy + Static File Server
Serves the HTML app AND proxies all /api/* calls to your APIC.

Usage:
    python3 aci-proxy.py

Then open:  http://localhost:8888
Login URL:  http://localhost:8888  (the proxy handles forwarding)
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request, urllib.error, ssl, os, mimetypes

TARGET  = "https://tpaci.bswhealth.org"   # ← your APIC
PORT    = 8888
WEBROOT = os.path.dirname(os.path.abspath(__file__))  # serve files from same folder

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode    = ssl.CERT_NONE

class Handler(BaseHTTPRequestHandler):

    # ── CORS preflight ──────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── Static files ────────────────────────────────────────────
    def do_GET(self):
        # Proxy ACI API calls
        if self.path.startswith("/api/") or self.path.startswith("/api"):
            self._proxy("GET")
            return

        # Serve local files
        path = self.path.split("?")[0]
        if path == "/" or path == "":
            path = "/aci-manager.html"

        file_path = WEBROOT + path
        if os.path.isfile(file_path):
            mime, _ = mimetypes.guess_type(file_path)
            with open(file_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime or "text/plain")
            self.send_header("Content-Length", len(data))
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    # ── Proxy POST (login, create) ──────────────────────────────
    def do_POST(self):
        self._proxy("POST")

    def _proxy(self, method):
        target = TARGET + self.path
        body   = None

        if method == "POST":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length) if length else None

        # Forward all headers except host
        hdrs = {k: v for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length", "origin", "referer")}

        req = urllib.request.Request(target, data=body, headers=hdrs, method=method)
        try:
            resp = urllib.request.urlopen(req, context=ctx)
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "connection") and not k.lower().startswith("access-control-"):
                    self.send_header(k, v)
            self._cors()
            self.end_headers()
            self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self._cors()
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self._cors()
            self.end_headers()
            self.wfile.write(str(e).encode())

    def _cors(self):
        origin = self.headers.get("Origin") or "*"
        self.send_header("Access-Control-Allow-Origin",      origin)
        self.send_header("Access-Control-Allow-Methods",     "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",     "Content-Type, APIC-cookie, Origin, Accept, X-Requested-With")
        self.send_header("Access-Control-Allow-Credentials", "true")

    def log_message(self, fmt, *args):
        method = args[0] if args else "?"
        code   = args[1] if len(args) > 1 else "?"
        print(f"  {code}  {self.path}")

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════╗
║           ACI Manager — Local Dev Server             ║
╠══════════════════════════════════════════════════════╣
║  App:    http://localhost:{PORT}                     ║
║  Proxy → {TARGET}                                    ║
╚══════════════════════════════════════════════════════╝

  Open your browser to:  http://localhost:{PORT}
  Login APIC URL field:  http://localhost:{PORT}
  Press Ctrl+C to stop.
""")
    server = HTTPServer(("", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[devserver] KeyboardInterrupt received. Shutting down...")
        try:
            server.server_close()
        except Exception:
            pass
