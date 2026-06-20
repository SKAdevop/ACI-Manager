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
import urllib.request, urllib.error, ssl, os, mimetypes, sys, argparse, json

DEFAULT_TARGET = "https://yourapic.url.com"
TARGET = DEFAULT_TARGET
PORT   = 8888

# 1. Try APIC_URL environment variable
if "APIC_URL" in os.environ:
    TARGET = os.environ["APIC_URL"]
    print(f"[config] Using APIC URL from environment: {TARGET}")

# 2. Try config.json in the same directory as this script/executable
else:
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    config_path = os.path.join(exe_dir, "config.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if "apic_url" in cfg:
                    TARGET = cfg["apic_url"]
                    print(f"[config] Loaded APIC URL from config.json: {TARGET}")
        except Exception as e:
            print(f"[config] Error reading config.json: {e}")

# 3. Try command-line arguments (--url or -u)
parser = argparse.ArgumentParser(description="ACI CORS Proxy Server")
parser.add_argument("--url", "-u", help="Target APIC URL (e.g., https://my-apic.com)")
args, unknown = parser.parse_known_args()
if args.url:
    TARGET = args.url
    print(f"[config] Using APIC URL from command line: {TARGET}")

# 4. Prompt user if running interactively in terminal and still using default
elif sys.stdin.isatty() and sys.stdout.isatty():
    try:
        print(f"\nNo custom APIC URL configured (via CLI, Env, or config.json).")
        user_input = input(f"Enter target APIC URL [{DEFAULT_TARGET}]: ").strip()
        if user_input:
            TARGET = user_input
            print(f"[config] Using entered APIC URL: {TARGET}")
        else:
            print(f"[config] Using default APIC URL: {TARGET}")
    except (KeyboardInterrupt, EOFError):
        print(f"\n[config] Using default APIC URL: {TARGET}")
else:
    print(f"[config] Running in non-interactive mode. Using default APIC URL: {TARGET}")

# Normalize TARGET format (strip whitespace, ensure protocol prefix, remove trailing slash)
TARGET = TARGET.strip().rstrip("/")
if not TARGET.startswith("http://") and not TARGET.startswith("https://"):
    TARGET = "https://" + TARGET

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
