import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .nodes import next_port
from .services import delete_node, edit_node, import_node, save_settings
from .storage import load_nodes, load_settings

STATIC_DIR = Path(__file__).with_name("static")


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        super().server_bind()


class IPv4Server(ThreadingHTTPServer):
    address_family = socket.AF_INET
    daemon_threads = True


def json_response(handler, status: int, payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("请求体必须是对象")
    return data


def form_payload(data: dict) -> dict:
    return {key: ["" if value is None else str(value)] for key, value in data.items()}


def send_static_file(handler, relative_path: str):
    target = (STATIC_DIR / relative_path).resolve()
    if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
        handler.send_error(404)
        return
    if not target.exists() or not target.is_file():
        handler.send_error(404)
        return

    content_type = "text/plain; charset=utf-8"
    if target.suffix == ".html":
        content_type = "text/html; charset=utf-8"
    elif target.suffix == ".css":
        content_type = "text/css; charset=utf-8"
    elif target.suffix == ".js":
        content_type = "application/javascript; charset=utf-8"

    body = target.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def create_admin_server(port: int):
    try:
        return DualStackServer(("::", port), RelayAdminHandler)
    except OSError:
        return IPv4Server(("0.0.0.0", port), RelayAdminHandler)


class RelayAdminHandler(BaseHTTPRequestHandler):
    server_version = "relay-admin/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            json_response(self, 200, {"ok": True})
            return
        if parsed.path == "/api/state":
            nodes = load_nodes()
            settings = load_settings()
            json_response(
                self,
                200,
                {
                    "nodes": nodes,
                    "settings": settings,
                    "next_local_port": next_port(nodes),
                },
            )
            return
        if parsed.path == "/":
            send_static_file(self, "index.html")
            return
        if parsed.path.startswith("/static/"):
            send_static_file(self, parsed.path.removeprefix("/static/"))
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = form_payload(read_json(self))

            if parsed.path == "/api/nodes/import":
                json_response(self, 200, {"ok": True, "message": import_node(payload)})
                return

            if parsed.path == "/api/nodes/delete":
                json_response(self, 200, {"ok": True, "message": delete_node(payload)})
                return

            if parsed.path == "/api/nodes/edit":
                json_response(self, 200, {"ok": True, "message": edit_node(payload)})
                return

            if parsed.path == "/api/settings":
                json_response(self, 200, {"ok": True, "message": save_settings(payload)})
                return

            self.send_error(404)
        except Exception as exc:
            json_response(self, 400, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        return
