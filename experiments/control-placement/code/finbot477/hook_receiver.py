"""Local passive guardrail-hook receiver: logs every FinBot hook call to JSONL, always answers allow."""
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
OUT = sys.argv[1]; PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try: env = json.loads(body)
        except Exception: env = {"_raw": body.decode("utf-8", "replace")[:2000]}
        env["_received_at"] = time.time()
        with open(OUT, "a", encoding="utf-8") as f: f.write(json.dumps(env, ensure_ascii=False) + "\n")
        resp = json.dumps({"verdict": "allow", "reason": "observer"}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp))); self.end_headers(); self.wfile.write(resp)
    def log_message(self, *a): pass
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
