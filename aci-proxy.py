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
import urllib.request, urllib.error, ssl, os, mimetypes, sys, argparse, json, threading, webbrowser

# Prevent PyInstaller GUI app crashes by redirecting None streams to devnull
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdin is None:
    class DummyStdin:
        def isatty(self): return False
        def read(self, *args, **kwargs): return ""
        def readline(self, *args, **kwargs): return ""
    sys.stdin = DummyStdin()

DEFAULT_TARGET = "https://myaci.company.com"
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
elif sys.stdin and hasattr(sys.stdin, "isatty") and sys.stdin.isatty() and sys.stdout and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
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

def run_tkinter_gui(server):
    import tkinter as tk
    
    root = tk.Tk()
    root.title("ACI Manager ToolSet")
    root.geometry("480x280")
    root.resizable(False, False)
    
    # Try to set the window icon if it exists
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    icon_path = os.path.join(exe_dir, "ACI Manager.ico")
    if not os.path.isfile(icon_path):
        icon_path = os.path.join(exe_dir, "app_icon.ico")
    if os.path.isfile(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    # Styling
    root.configure(bg="#f8fafc")
    
    # Title Label
    title_label = tk.Label(
        root, 
        text="ACI Manager - Local Server Controller", 
        font=("Segoe UI", 13, "bold"), 
        fg="#0f172a", 
        bg="#f8fafc",
        pady=10
    )
    title_label.pack()

    # Status Label
    status_label = tk.Label(
        root, 
        text="● Local Server is Active & Running", 
        font=("Segoe UI", 10, "bold"), 
        fg="#16a34a", 
        bg="#f8fafc"
    )
    status_label.pack(pady=3)

    # Info Box
    info_text = (
        f"  Local Access:  http://localhost:{PORT}\n"
        f"  Target APIC:   {TARGET}"
    )
    info_label = tk.Label(
        root, 
        text=info_text, 
        font=("Consolas", 10), 
        fg="#334155", 
        bg="#f1f5f9",
        padx=15,
        pady=12,
        justify=tk.LEFT,
        relief=tk.SOLID,
        borderwidth=1
    )
    info_label.pack(pady=8, fill=tk.X, padx=30)

    # Instruction Label
    inst_label = tk.Label(
        root, 
        text="Open the browser to log in to your Cisco APIC controller:", 
        font=("Segoe UI", 9), 
        fg="#64748b", 
        bg="#f8fafc"
    )
    inst_label.pack(pady=4)

    # Buttons Frame
    btn_frame = tk.Frame(root, bg="#f8fafc")
    btn_frame.pack(pady=8)

    # Open Browser Button
    btn_open = tk.Button(
        btn_frame, 
        text="Open Web App", 
        font=("Segoe UI", 9, "bold"), 
        fg="#ffffff", 
        bg="#0284c7", 
        activeforeground="#ffffff",
        activebackground="#0369a1",
        padx=14,
        pady=6,
        command=lambda: webbrowser.open(f"http://localhost:{PORT}"),
        cursor="hand2"
    )
    btn_open.pack(side=tk.LEFT, padx=8)

    # Stop Button
    btn_stop = tk.Button(
        btn_frame, 
        text="Stop Server", 
        font=("Segoe UI", 9, "bold"), 
        fg="#ffffff", 
        bg="#dc2626", 
        activeforeground="#ffffff",
        activebackground="#b91c1c",
        padx=14,
        pady=6,
        command=lambda: (server.shutdown(), server.server_close(), root.destroy()),
        cursor="hand2"
    )
    btn_stop.pack(side=tk.LEFT, padx=8)

    # Handle window close button
    root.protocol("WM_DELETE_WINDOW", lambda: (server.shutdown(), server.server_close(), root.destroy()))
    
    # Bring window to front
    root.reveal = lambda: (root.lift(), root.attributes("-topmost", True), root.after_idle(root.attributes, "-topmost", False))
    root.reveal()
    
    root.mainloop()

def run_ctypes_gui(server):
    import ctypes
    
    title = "ACI Manager ToolSet"
    message = (
        "ACI Manager Local Proxy Server is now running!\n\n"
        f"  • Local Access: http://localhost:{PORT}\n"
        f"  • Target APIC:  {TARGET}\n\n"
        "Would you like to open the web application in your default browser?"
    )
    
    # MB_YESNO (4) | MB_ICONINFORMATION (0x40)
    response = ctypes.windll.user32.MessageBoxW(0, message, title, 4 | 0x40)
    
    if response == 6: # IDYES
        webbrowser.open(f"http://localhost:{PORT}")
        
    # Dialog 2: Keep alive & allow shutdown
    keep_alive_message = (
        "ACI Manager Local Proxy Server remains active.\n\n"
        "Click OK to stop the server and exit the application."
    )
    # MB_OK (0) | MB_ICONINFORMATION (0x40)
    ctypes.windll.user32.MessageBoxW(0, keep_alive_message, title, 0 | 0x40)
    
    # Shutdown server
    server.shutdown()
    server.server_close()

def run_gui(server):
    try:
        run_tkinter_gui(server)
    except (ImportError, Exception):
        run_ctypes_gui(server)

if __name__ == "__main__":
    print(f"""
+------------------------------------------------------+
|           ACI Manager - Local Dev Server             |
+------------------------------------------------------+
|  App:    http://localhost:{PORT}                     |
|  Proxy -> {TARGET}                                   |
+------------------------------------------------------+

  Open your browser to:  http://localhost:{PORT}
  Login APIC URL field:  http://localhost:{PORT}
  Press Ctrl+C to stop.
""")
    
    server = HTTPServer(("", PORT), Handler)
    
    # Start server in a background thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        run_gui(server)
    except Exception as e:
        # Fallback to standard console blocking loop if GUI fails to start
        print(f"[devserver] GUI failed to start ({e}). Running in console mode.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[devserver] KeyboardInterrupt received. Shutting down...")
            server.shutdown()
            server.server_close()
