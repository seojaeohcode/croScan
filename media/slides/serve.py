# Local static server with CORS, so the Figma tab can load slide data and images (http://localhost:8790/...).
import http.server, socketserver, os
ROOT = os.environ.get("SERVE_ROOT") or os.path.dirname(os.path.abspath(__file__)) + "/.."   # SERVE_ROOT=D:/croScan_temp PORT=8791 for the reference board
os.chdir(ROOT)
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def log_message(self, *a): pass
    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Access-Control-Allow-Methods", "POST, GET"); self.send_header("Access-Control-Allow-Headers", "*"); self.end_headers()
    def do_POST(self):   # Figma exports: POST /save/<name> → croScan_PPT/figma_out/<name>
        import urllib.parse
        name = urllib.parse.unquote(self.path.split("/save/", 1)[1]).replace("/", "_").replace("..", "_")
        out = os.environ.get("SAVE_DIR") or os.path.join("croScan_PPT", "figma_out"); os.makedirs(out, exist_ok=True)
        data = self.rfile.read(int(self.headers["Content-Length"]))
        open(os.path.join(out, name), "wb").write(data)
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", int(os.environ.get("PORT", "8790"))), H) as s: s.serve_forever()
