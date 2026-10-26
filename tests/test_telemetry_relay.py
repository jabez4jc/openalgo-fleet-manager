"""Telemetry stream relay: logs in, forwards the server's SSE bytes unchanged, and
turns a failure into an SSE error event. Run: python tests/test_telemetry_relay.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+asyncpg://t@localhost/t"
import asyncio, http.server, threading, json
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(302); self.send_header("Set-Cookie","oa_session=abc; Path=/"); self.send_header("Location","/"); self.end_headers()
    def do_GET(self):
        assert "oa_session=abc" in self.headers.get("Cookie",""), "no cookie"
        assert "interval=2" in self.path
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
        for i in range(2): self.wfile.write(f"data: {json.dumps({'n':i})}\n\n".encode()); self.wfile.flush()
srv=http.server.ThreadingHTTPServer(("127.0.0.1",0),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
from app.services.admin_api import AdminAPISession
async def main():
    out=b"".join([c async for c in AdminAPISession(f"http://127.0.0.1:{srv.server_port}","u","p").stream_telemetry()])
    assert out==b'data: {"n": 0}\n\ndata: {"n": 1}\n\n', out
    bad=b"".join([c async for c in AdminAPISession("http://127.0.0.1:1","u","p").stream_telemetry()])
    assert b"event: error" in bad, bad
    print("ok")
asyncio.run(main())
