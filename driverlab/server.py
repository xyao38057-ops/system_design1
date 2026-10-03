"""Run with: python server.py. Standard library only; bind to localhost."""
import argparse
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from app.behavior import analyze
from app.simulation import Simulation
from app.storage import Storage

ROOT = Path(__file__).resolve().parent


class Application:
    def __init__(self, db_path):
        self.lock = threading.RLock()
        self.sim = Simulation()
        self.store = Storage(db_path)
        self.multiplier = 1
        self.stop = threading.Event()
        self.failure = None
        self.store.save(self.sim)

    def action(self, data):
        with self.lock:
            command = data.get("action")
            if command == "start":
                if self.sim.completed or self.sim.collision:
                    raise ValueError("当前场景已结束，请重置后再开始")
                self.sim.running = True
            elif command == "pause":
                self.sim.running = False
            elif command in ("reset", "scenario"):
                self.store.save(self.sim)
                self.sim.reset(data.get("scenario", "normal"), data.get("profile", self.sim.profile))
                self.sim.running = command == "scenario"
            elif command == "profile":
                self.sim.set_profile(data.get("profile"))
            elif command == "road":
                self.sim.set_road(data.get("edge"), data.get("operation"))
            elif command == "sensor":
                if type(data.get("online")) is not bool:
                    raise ValueError("online 必须是布尔值")
                self.sim.set_sensor(data["online"])
            elif command == "behavior":
                self.sim.behavior = analyze(data.get("style"))
                self.sim.log("behavior", "重新分析用户样本", self.sim.behavior["label"])
            elif command == "speed":
                if data.get("multiplier") not in (1, 2, 4):
                    raise ValueError("倍速仅支持 1、2、4")
                self.multiplier = data["multiplier"]
            else:
                raise ValueError("未知操作")
            self.store.save(self.sim)
            return self.state()

    def state(self):
        snap = self.sim.snapshot()
        snap["multiplier"] = self.multiplier
        snap["engine_error"] = self.failure
        return snap

    def loop(self):
        count = 0
        while not self.stop.wait(.1):
            try:
                with self.lock:
                    for _ in range(self.multiplier):
                        self.sim.tick(.1)
                    count += 1
                    if self.sim.pending_events or count % 10 == 0:
                        self.store.save(self.sim)
            except Exception as exc:
                with self.lock:
                    self.sim.running = False
                    self.failure = str(exc)
                print(f"Simulation paused due to error: {exc}", flush=True)
                return


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if args and str(args[1] if len(args) > 1 else "").startswith("5"):
                super().log_message(fmt, *args)

        def send(self, code, body, content_type="application/json; charset=utf-8", attachment=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/state":
                with app.lock:
                    self.send(200, app.state())
            elif path == "/api/runs":
                with app.lock:
                    self.send(200, app.store.runs())
            elif path == "/api/export":
                with app.lock:
                    app.store.save(app.sim)
                    self.send(200, app.store.export_csv(), "text/csv; charset=utf-8", "driverlab-events.csv")
            elif path == "/api/health":
                self.send(200 if not app.failure else 503,
                          {"ok": not bool(app.failure), "engine": "builtin-2d", "error": app.failure})
            else:
                # Explicit whitelist avoids filesystem traversal and accidental database exposure.
                files = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
                if path not in files:
                    self.send(404, {"error": "资源不存在"})
                    return
                target = ROOT / "static" / files[path]
                content_type = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[target.suffix]
                self.send(200, target.read_bytes(), content_type + "; charset=utf-8")

        def do_POST(self):
            if self.path != "/api/action":
                self.send(404, {"error": "接口不存在"})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.send(415, {"error": "请使用 application/json"})
                return
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.send(403, {"error": "仅接受同源请求"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("请求长度不合法")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("请求必须是 JSON 对象")
                self.send(200, app.action(data))
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, {"error": str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description="DriverLab course demo (Python standard library only)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=str(ROOT / "data" / "driverlab.sqlite3"))
    args = parser.parse_args()
    server = None
    app = Application(args.db)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(app))
        worker = threading.Thread(target=app.loop, daemon=True)
        worker.start()
        print(f"DriverLab ready: http://127.0.0.1:{args.port}  |  Ctrl+C to stop", flush=True)
        print("Engine: built-in 2D teaching simulator; SUMO is not connected.", flush=True)
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"Cannot start server: {exc}. Try --port 8001", flush=True)
        raise SystemExit(1)
    finally:
        app.stop.set()
        if server:
            server.server_close()
        with app.lock:
            app.store.save(app.sim)


if __name__ == "__main__":
    main()
