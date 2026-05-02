import atexit
import base64
import html
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
NODES_PATH = DATA_DIR / "nodes.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "18080"))
XRAY_BIN = os.environ.get("XRAY_BIN", "/usr/local/bin/xray")
XRAY_CONFIG = os.environ.get("XRAY_CONFIG", "/data/xray-config.json")
SINGBOX_BIN = os.environ.get("SINGBOX_BIN", "/usr/local/bin/sing-box")
SINGBOX_CONFIG = os.environ.get("SINGBOX_CONFIG", "/data/singbox-config.json")
SINGBOX_CONFIG_DIR = Path(os.environ.get("SINGBOX_CONFIG_DIR", "/data/singbox.d"))
XRAY = None
SINGBOX = None
SINGBOX_PROCS: dict[str, subprocess.Popen] = {}
SINGBOX_MODE = os.environ.get("SINGBOX_MODE", "single").strip().lower()
CORE_LOCK = threading.Lock()


def forward_xray_output(proc: subprocess.Popen):
    if proc.stdout is None:
        return
    for line in proc.stdout:
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            return


def forward_proc_output(proc: subprocess.Popen, prefix: str):
    if proc.stdout is None:
        return
    for line in proc.stdout:
        try:
            sys.stdout.write(f"[{prefix}] {line}")
            sys.stdout.flush()
        except Exception:
            return


def read_flash(handler):
    raw_cookie = handler.headers.get("Cookie", "")
    if not raw_cookie:
        return "", False
    cookie = SimpleCookie()
    try:
        cookie.load(raw_cookie)
    except Exception:
        return "", False
    msg = cookie.get("flash_msg")
    err = cookie.get("flash_err")
    if not msg:
        return "", False
    try:
        text = unquote(msg.value)
    except Exception:
        text = msg.value
    return text, bool(err and err.value == "1")


def set_flash_headers(handler, message: str, error: bool):
    cookie = SimpleCookie()
    cookie["flash_msg"] = quote(message, safe="")
    cookie["flash_msg"]["path"] = "/"
    cookie["flash_msg"]["max-age"] = 15
    cookie["flash_msg"]["samesite"] = "Lax"
    cookie["flash_err"] = "1" if error else "0"
    cookie["flash_err"]["path"] = "/"
    cookie["flash_err"]["max-age"] = 15
    cookie["flash_err"]["samesite"] = "Lax"
    for morsel in cookie.values():
        handler.send_header("Set-Cookie", morsel.OutputString())


def clear_flash_headers(handler):
    cookie = SimpleCookie()
    cookie["flash_msg"] = ""
    cookie["flash_msg"]["path"] = "/"
    cookie["flash_msg"]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    cookie["flash_msg"]["max-age"] = 0
    cookie["flash_msg"]["samesite"] = "Lax"
    cookie["flash_err"] = ""
    cookie["flash_err"]["path"] = "/"
    cookie["flash_err"]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    cookie["flash_err"]["max-age"] = 0
    cookie["flash_err"]["samesite"] = "Lax"
    for morsel in cookie.values():
        handler.send_header("Set-Cookie", morsel.OutputString())


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        super().server_bind()


def html_page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(title)}</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f3f1ea;
        --card: #fffdf8;
        --line: #d8d1c2;
        --text: #1f1d17;
        --muted: #6c6658;
        --accent: #0d5c63;
        --danger: #8c2f39;
        --overlay: rgba(24, 22, 17, 0.45);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        padding: 24px;
        background: radial-gradient(circle at top, #fff7df 0, var(--bg) 48%);
        color: var(--text);
        font: 14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
      }}
      .wrap {{ max-width: 1080px; margin: 0 auto; }}
      h1, h2 {{ margin: 0 0 12px; }}
      .sub {{ color: var(--muted); margin: 8px 0 20px; }}
      .grid {{
        display: grid;
        grid-template-columns: 1.2fr 1fr;
        gap: 18px;
      }}
      .card {{
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 18px;
        box-shadow: 0 12px 40px rgba(38, 33, 20, 0.05);
      }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{
        text-align: left;
        padding: 10px 8px;
        border-bottom: 1px solid #ece5d8;
        vertical-align: top;
      }}
      th {{ color: var(--muted); font-weight: 600; }}
      textarea, input, select {{
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 10px 12px;
        font: inherit;
        background: #fff;
        color: var(--text);
      }}
      textarea {{ min-height: 180px; resize: vertical; }}
      .row {{
        display: grid;
        grid-template-columns: 1fr 160px;
        gap: 12px;
      }}
      .row3 {{
        display: grid;
        grid-template-columns: 1fr 160px 160px;
        gap: 12px;
      }}
      .field {{ margin-bottom: 12px; }}
      label {{
        display: block;
        margin-bottom: 6px;
        color: var(--muted);
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }}
      button {{
        border: 0;
        border-radius: 10px;
        padding: 10px 14px;
        font: inherit;
        cursor: pointer;
        background: var(--accent);
        color: #fff;
      }}
      button.danger {{ background: var(--danger); }}
      .hint, .note {{
        color: var(--muted);
        font-size: 12px;
      }}
      .flash {{
        margin-bottom: 16px;
        padding: 12px 14px;
        border-radius: 12px;
        border: 1px solid var(--line);
        background: #fff8e8;
      }}
      .actions {{
        display: flex;
        align-items: center;
        gap: 8px;
      }}
      .plain {{
        background: transparent;
        color: var(--muted);
        border: 1px solid var(--line);
      }}
      .overlay {{
        position: fixed;
        inset: 0;
        display: none;
        align-items: center;
        justify-content: center;
        padding: 20px;
        background: var(--overlay);
        z-index: 20;
      }}
      .overlay.open {{
        display: flex;
      }}
      .modal {{
        width: min(100%, 420px);
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 24px 80px rgba(23, 19, 12, 0.18);
      }}
      .modal h3 {{
        margin: 0 0 10px;
        font-size: 20px;
      }}
      .modal p {{
        margin: 0 0 18px;
        color: var(--muted);
      }}
      .modal-actions {{
        display: flex;
        justify-content: flex-end;
        gap: 10px;
      }}
      .modal .field:last-of-type {{
        margin-bottom: 0;
      }}
      code {{
        background: #f2ecde;
        padding: 2px 6px;
        border-radius: 6px;
      }}
      .socks {{
        font-family: ui-monospace,SFMono-Regular,Menlo,monospace;
        word-break: break-all;
      }}
      @media (max-width: 900px) {{
        .grid {{ grid-template-columns: 1fr; }}
        .row {{ grid-template-columns: 1fr; }}
        .row3 {{ grid-template-columns: 1fr; }}
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      {body}
    </div>
    <div class="overlay" id="delete-modal" aria-hidden="true">
      <div class="modal">
        <h3>删除节点</h3>
        <p id="delete-modal-text">确认删除这个中转节点吗？删除后将自动重载 Xray。</p>
        <form method="post" action="/delete" id="delete-form">
          <input type="hidden" name="id" id="delete-id">
          <div class="modal-actions">
            <button type="button" class="plain" id="delete-cancel">取消</button>
            <button type="submit" class="danger">确认删除</button>
          </div>
        </form>
      </div>
    </div>
    <div class="overlay" id="edit-modal" aria-hidden="true">
      <div class="modal">
        <h3>编辑节点</h3>
        <p>修改名称、本地端口或分享链接。保存后将自动重载 Xray。</p>
        <form method="post" action="/edit" id="edit-form">
          <input type="hidden" name="id" id="edit-id">
          <div class="field">
            <label for="edit-name_override">节点名称</label>
            <input id="edit-name_override" name="name_override" placeholder="可选，不填则使用分享链接名称">
          </div>
          <div class="row">
            <div class="field">
              <label for="edit-local_port">本地端口</label>
              <input id="edit-local_port" name="local_port" placeholder="11080">
            </div>
            <div class="field">
              <label for="edit-kernel">内核</label>
              <select id="edit-kernel" name="kernel">
                <option value="xray">xray</option>
                <option value="sing-box">sing-box</option>
              </select>
            </div>
          </div>
          <div class="field">
            <label for="edit-share_link">分享链接</label>
            <textarea id="edit-share_link" name="share_link" placeholder="vmess:// / vless:// / trojan:// / ss:// / hysteria2:// / tuic://"></textarea>
          </div>
          <div class="modal-actions">
            <button type="button" class="plain" id="edit-cancel">取消</button>
            <button type="submit">保存并重载</button>
          </div>
        </form>
      </div>
    </div>
    <script>
      (() => {{
        const deleteModal = document.getElementById('delete-modal');
        const deleteIdInput = document.getElementById('delete-id');
        const deleteText = document.getElementById('delete-modal-text');
        const deleteCancel = document.getElementById('delete-cancel');
        const deleteButtons = document.querySelectorAll('[data-delete-id]');
        const editModal = document.getElementById('edit-modal');
        const editIdInput = document.getElementById('edit-id');
        const editNameInput = document.getElementById('edit-name_override');
        const editPortInput = document.getElementById('edit-local_port');
        const editKernelInput = document.getElementById('edit-kernel');
        const editShareInput = document.getElementById('edit-share_link');
        const editCancel = document.getElementById('edit-cancel');
        const editButtons = document.querySelectorAll('[data-edit-id]');

        function closeDeleteModal() {{
          deleteModal.classList.remove('open');
          deleteModal.setAttribute('aria-hidden', 'true');
          deleteIdInput.value = '';
        }}

        function closeEditModal() {{
          editModal.classList.remove('open');
          editModal.setAttribute('aria-hidden', 'true');
          editIdInput.value = '';
          editNameInput.value = '';
          editPortInput.value = '';
          editKernelInput.value = 'xray';
          editShareInput.value = '';
        }}

        deleteButtons.forEach((button) => {{
          button.addEventListener('click', () => {{
            const nodeId = button.getAttribute('data-delete-id') || '';
            const nodeName = button.getAttribute('data-delete-name') || '该节点';
            deleteIdInput.value = nodeId;
            deleteText.textContent = `确认删除“${{nodeName}}”吗？删除后将自动重载 Xray。`;
            deleteModal.classList.add('open');
            deleteModal.setAttribute('aria-hidden', 'false');
          }});
        }});

        editButtons.forEach((button) => {{
          button.addEventListener('click', () => {{
            editIdInput.value = button.getAttribute('data-edit-id') || '';
            editNameInput.value = button.getAttribute('data-edit-name') || '';
            editPortInput.value = button.getAttribute('data-edit-port') || '';
            editKernelInput.value = button.getAttribute('data-edit-kernel') || 'xray';
            editShareInput.value = button.getAttribute('data-edit-link') || '';
            editModal.classList.add('open');
            editModal.setAttribute('aria-hidden', 'false');
          }});
        }});

        deleteCancel.addEventListener('click', closeDeleteModal);
        editCancel.addEventListener('click', closeEditModal);
        deleteModal.addEventListener('click', (event) => {{
          if (event.target === deleteModal) closeDeleteModal();
        }});
        editModal.addEventListener('click', (event) => {{
          if (event.target === editModal) closeEditModal();
        }});
        document.addEventListener('keydown', (event) => {{
          if (event.key === 'Escape') {{
            closeDeleteModal();
            closeEditModal();
          }}
        }});
      }})();
    </script>
  </body>
</html>
""".encode("utf-8")


def load_nodes():
    if not NODES_PATH.exists():
        return []
    with NODES_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("nodes.json 必须是数组结构")
    return data


def load_settings():
    defaults = {
        "xray_log_level": "warning",
        "singbox_log_level": "info",
    }
    if not SETTINGS_PATH.exists():
        return defaults
    with SETTINGS_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return defaults
    merged = {**defaults, **data}
    merged["xray_log_level"] = normalize_xray_log_level(merged.get("xray_log_level"))
    merged["singbox_log_level"] = normalize_singbox_log_level(merged.get("singbox_log_level"))
    return merged


def atomic_write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        tmp_name = fh.name
    os.replace(tmp_name, path)


def truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def decode_b64(text: str) -> str:
    raw = text.strip()
    if not raw:
        raise ValueError("VMess 内容为空")
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return decoder(padded.encode("utf-8")).decode("utf-8")
        except Exception:
            continue
    raise ValueError("VMess Base64 内容无效")


def normalize_tls(value: str) -> str:
    val = (value or "").strip().lower()
    if val in {"", "none", "off"}:
        return "none"
    return val


def normalize_header_type(value: str) -> str:
    val = (value or "").strip()
    return val if val else "none"


def normalize_kernel(value: str) -> str:
    kernel = (value or "xray").strip().lower()
    if kernel not in {"xray", "sing-box"}:
        return "xray"
    return kernel


def allowed_kernels(protocol: str, node: dict | None = None):
    if protocol in {"hysteria2", "tuic"}:
        return {"sing-box"}
    if protocol == "shadowsocks" and node and node.get("plugin"):
        return {"sing-box"}
    return {"xray", "sing-box"}


def validate_kernel_for_node(node: dict):
    allowed = allowed_kernels(node["protocol"], node)
    kernel = normalize_kernel(node.get("kernel"))
    if kernel not in allowed:
        allowed_text = " / ".join(sorted(allowed))
        raise ValueError(f"协议 {node['protocol']} 仅支持内核：{allowed_text}")


def normalize_xray_log_level(value: str) -> str:
    val = (value or "warning").strip().lower()
    allowed = {"debug", "info", "warning", "error"}
    return val if val in allowed else "warning"


def normalize_singbox_log_level(value: str) -> str:
    val = (value or "info").strip().lower()
    allowed = {"trace", "debug", "info", "warn", "error", "fatal", "panic"}
    return val if val in allowed else "info"


def next_port(nodes):
    used = {int(node["local_port"]) for node in nodes}
    port = 11080
    while port in used:
        port += 1
    return port


def get_path_from_params(network: str, params):
    network = (network or "tcp").strip().lower()
    if network == "grpc":
        return params.get("serviceName", [""])[0]
    if network in {"mkcp", "kcp"}:
        return params.get("seed", [""])[0]
    if network == "meek":
        return params.get("url", [""])[0]
    return params.get("path", [""])[0]


def parse_common_v2_params(parsed, local_port: int, protocol: str, name_override: str):
    params = parse_qs(parsed.query)
    network = (params.get("type", ["tcp"])[0] or "tcp").strip()
    name = name_override.strip() or unquote(parsed.fragment or "") or parsed.hostname or f"{protocol}-{local_port}"
    return {
        "id": f"node-{uuid.uuid4().hex[:8]}",
        "name": name,
        "kernel": "xray",
        "protocol": protocol,
        "link": parsed.geturl(),
        "local_port": local_port,
        "address": parsed.hostname or "",
        "port": int(parsed.port or 443),
        "network": network,
        "header_type": normalize_header_type(params.get("headerType", ["none"])[0]),
        "host": params.get("host", [""])[0],
        "path": get_path_from_params(network, params) or "/",
        "tls": normalize_tls(params.get("security", ["none"])[0]),
        "sni": params.get("sni", [""])[0],
        "alpn": params.get("alpn", [""])[0],
        "fingerprint": params.get("fp", [""])[0],
        "allow_insecure": truthy(params.get("allowInsecure", ["0"])[0]),
        "flow": params.get("flow", [""])[0],
        "public_key": params.get("pbk", [""])[0],
        "short_id": params.get("sid", [""])[0],
        "spider_x": params.get("spx", [""])[0],
    }


def parse_vless_link(link: str, local_port: int, name_override: str = ""):
    parsed = urlparse(link.strip())
    if parsed.scheme != "vless":
        raise ValueError("不是 vless:// 分享链接")
    node = parse_common_v2_params(parsed, local_port, "vless", name_override)
    node["uuid"] = unquote(parsed.username or "")
    if not node["address"] or not node["port"] or not node["uuid"]:
        raise ValueError("VLESS 链接缺少必要字段")
    return node


def parse_trojan_link(link: str, local_port: int, name_override: str = ""):
    parsed = urlparse(link.strip())
    if parsed.scheme != "trojan":
        raise ValueError("不是 trojan:// 分享链接")
    node = parse_common_v2_params(parsed, local_port, "trojan", name_override)
    node["password"] = unquote(parsed.username or "")
    if node["tls"] == "none":
        node["tls"] = "tls"
    if not node["sni"]:
        node["sni"] = node["host"] or node["address"]
    if not node["address"] or not node["port"] or not node["password"]:
        raise ValueError("Trojan 链接缺少必要字段")
    return node


def decode_ss_credentials(raw: str):
    decoded = decode_b64(raw)
    if ":" not in decoded:
        raise ValueError("SS 凭据格式无效")
    method, password = decoded.split(":", 1)
    return method, password


def parse_ss_link(link: str, local_port: int, name_override: str = ""):
    link = link.strip()
    if not link.startswith("ss://"):
        raise ValueError("不是 ss:// 分享链接")
    parsed = urlparse(link)
    fragment_name = unquote(parsed.fragment or "")
    query = parse_qs(parsed.query)
    node = {
        "id": f"node-{uuid.uuid4().hex[:8]}",
        "name": name_override.strip() or fragment_name or f"ss-{local_port}",
        "kernel": "xray",
        "protocol": "shadowsocks",
        "link": link,
        "local_port": local_port,
        "plugin": query.get("plugin", [""])[0],
    }

    if parsed.hostname and parsed.username:
        userinfo = unquote(parsed.username)
        password_part = unquote(parsed.password or "")
        if password_part:
            method = userinfo
            password = password_part
        else:
            method, password = decode_ss_credentials(userinfo)
        node["address"] = parsed.hostname
        node["port"] = int(parsed.port or 0)
        node["method"] = method
        node["password"] = password
    else:
        body = link[5:]
        if "#" in body:
            body = body.split("#", 1)[0]
        if "?" in body:
            body = body.split("?", 1)[0]
        decoded = decode_b64(body)
        if "@" not in decoded:
            raise ValueError("SS 链接格式无效")
        creds, server = decoded.rsplit("@", 1)
        if ":" not in creds or ":" not in server:
            raise ValueError("SS 链接格式无效")
        method, password = creds.split(":", 1)
        address, port = server.rsplit(":", 1)
        node["address"] = address
        node["port"] = int(port)
        node["method"] = method
        node["password"] = password

    if not node["address"] or not node["port"] or not node["method"]:
        raise ValueError("SS 链接缺少必要字段")
    return node


def parse_hysteria2_link(link: str, local_port: int, name_override: str = ""):
    parsed = urlparse(link.strip())
    if parsed.scheme not in {"hy2", "hysteria2"}:
        raise ValueError("不是 hysteria2:// 分享链接")
    params = parse_qs(parsed.query)
    node = {
        "id": f"node-{uuid.uuid4().hex[:8]}",
        "name": name_override.strip() or unquote(parsed.fragment or "") or parsed.hostname or f"hysteria2-{local_port}",
        "kernel": "sing-box",
        "protocol": "hysteria2",
        "link": link,
        "local_port": local_port,
        "address": parsed.hostname or "",
        "port": int(parsed.port or 443),
        "password": unquote(parsed.username or ""),
        "sni": params.get("sni", [""])[0] or (parsed.hostname or ""),
        "alpn": params.get("alpn", [""])[0],
        "allow_insecure": truthy(params.get("insecure", ["0"])[0]),
        "obfs": params.get("obfs", [""])[0],
        "obfs_password": params.get("obfs-password", [""])[0],
    }
    if not node["address"] or not node["port"] or not node["password"]:
        raise ValueError("Hysteria2 链接缺少必要字段")
    return node


def parse_tuic_link(link: str, local_port: int, name_override: str = ""):
    parsed = urlparse(link.strip())
    if parsed.scheme != "tuic":
        raise ValueError("不是 tuic:// 分享链接")
    params = parse_qs(parsed.query)
    insecure_value = params.get("allow_insecure", [None])[0]
    if insecure_value in (None, ""):
        insecure_value = params.get("insecure", ["0"])[0]
    node = {
        "id": f"node-{uuid.uuid4().hex[:8]}",
        "name": name_override.strip() or unquote(parsed.fragment or "") or parsed.hostname or f"tuic-{local_port}",
        "kernel": "sing-box",
        "protocol": "tuic",
        "link": link,
        "local_port": local_port,
        "address": parsed.hostname or "",
        "port": int(parsed.port or 443),
        "uuid": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "sni": params.get("sni", [""])[0] or (parsed.hostname or ""),
        "alpn": params.get("alpn", [""])[0],
        "allow_insecure": truthy(insecure_value),
        "congestion_control": params.get("congestion_control", [""])[0],
        "udp_relay_mode": params.get("udp_relay_mode", [""])[0],
        "zero_rtt_handshake": truthy(params.get("zero_rtt_handshake", ["0"])[0]),
        "heartbeat": params.get("heartbeat", [""])[0],
    }
    if not node["address"] or not node["port"] or not node["uuid"] or not node["password"]:
        raise ValueError("TUIC 链接缺少必要字段")
    return node


def parse_share_link(link: str, local_port: int, name_override: str = ""):
    trimmed = link.strip()
    if trimmed.startswith("vmess://"):
        return parse_vmess_link(trimmed, local_port, name_override)
    if trimmed.startswith("vless://"):
        return parse_vless_link(trimmed, local_port, name_override)
    if trimmed.startswith("trojan://"):
        return parse_trojan_link(trimmed, local_port, name_override)
    if trimmed.startswith("ss://"):
        return parse_ss_link(trimmed, local_port, name_override)
    if trimmed.startswith("hy2://") or trimmed.startswith("hysteria2://"):
        return parse_hysteria2_link(trimmed, local_port, name_override)
    if trimmed.startswith("tuic://"):
        return parse_tuic_link(trimmed, local_port, name_override)
    raise ValueError("当前只支持 vmess / vless / trojan / ss / hysteria2 / tuic 分享链接")


def parse_vmess_link(link: str, local_port: int, name_override: str = ""):
    link = link.strip()
    if not link.startswith("vmess://"):
        raise ValueError("当前只支持导入 vmess:// 分享链接")

    payload = link[8:]
    try:
        body = json.loads(decode_b64(payload))
    except Exception:
        parsed = urlparse(link)
        params = parse_qs(parsed.query)
        net = (params.get("type", ["tcp"])[0] or "tcp").strip()
        path = params.get("path", [""])[0]
        if net == "grpc":
            path = params.get("serviceName", [path])[0]
        return {
            "id": f"node-{uuid.uuid4().hex[:8]}",
            "name": name_override.strip() or unquote(parsed.fragment or "") or parsed.hostname or f"vmess-{local_port}",
            "kernel": "xray",
            "protocol": "vmess",
            "link": link,
            "local_port": local_port,
            "address": parsed.hostname or "",
            "port": int(parsed.port or 443),
            "uuid": unquote(parsed.username or ""),
            "alter_id": int(params.get("aid", params.get("alterId", ["0"]))[0] or 0),
            "security": params.get("encryption", ["auto"])[0] or "auto",
            "network": net,
            "header_type": normalize_header_type(params.get("headerType", ["none"])[0]),
            "host": params.get("host", [""])[0],
            "path": path or "/",
            "tls": normalize_tls(params.get("security", ["none"])[0]),
            "sni": params.get("sni", [""])[0],
            "alpn": params.get("alpn", [""])[0],
            "fingerprint": params.get("fp", [""])[0],
            "allow_insecure": truthy(params.get("allowInsecure", ["0"])[0]),
        }

    network = (body.get("net") or "tcp").strip()
    path = body.get("path") or ""
    if network in {"grpc"} and not path:
        path = body.get("serviceName") or ""
    node = {
        "id": f"node-{uuid.uuid4().hex[:8]}",
        "name": name_override.strip() or body.get("ps") or body.get("add") or f"vmess-{local_port}",
        "kernel": "xray",
        "protocol": "vmess",
        "link": link,
        "local_port": local_port,
        "address": body.get("add", ""),
        "port": int(body.get("port") or 0),
        "uuid": body.get("id", ""),
        "alter_id": int(body.get("aid") or 0),
        "security": body.get("scy") or body.get("security") or "auto",
        "network": network,
        "header_type": normalize_header_type(body.get("type") or body.get("headerType")),
        "host": body.get("host", ""),
        "path": path or "/",
        "tls": normalize_tls(body.get("tls") or body.get("securityType") or "none"),
        "sni": body.get("sni", ""),
        "alpn": body.get("alpn", ""),
        "fingerprint": body.get("fp", ""),
        "allow_insecure": truthy(body.get("allowInsecure") or body.get("insecure") or 0),
    }
    if not node["address"] or not node["port"] or not node["uuid"]:
        raise ValueError("VMess 链接缺少必要字段")
    return node


def update_node(existing_node: dict, link: str, local_port: int, name_override: str = ""):
    node = parse_share_link(link, local_port, name_override)
    node["id"] = existing_node["id"]
    return node


def build_stream_settings(node):
    network = (node.get("network") or "tcp").strip().lower()
    tls = normalize_tls(node.get("tls", "none"))
    stream = {
        "network": network,
        "security": tls,
    }

    if tls == "tls":
        tls_settings = {}
        server_name = (node.get("sni") or node.get("host") or "").strip()
        if server_name:
            tls_settings["serverName"] = server_name
        if node.get("allow_insecure"):
            tls_settings["allowInsecure"] = True
        fingerprint = (node.get("fingerprint") or "").strip()
        if fingerprint:
            tls_settings["fingerprint"] = fingerprint
        alpn = (node.get("alpn") or "").strip()
        if alpn:
            tls_settings["alpn"] = [item.strip() for item in alpn.split(",") if item.strip()]
        if tls_settings:
            stream["tlsSettings"] = tls_settings

    host = (node.get("host") or "").strip()
    path = (node.get("path") or "/").strip() or "/"
    header_type = normalize_header_type(node.get("header_type"))

    if network == "tcp":
        header = {"type": header_type}
        if header_type == "http":
            request = {"path": [path]}
            if host:
                request["headers"] = {"Host": [host]}
            header["request"] = request
        stream["tcpSettings"] = {"header": header}
    elif network == "ws":
        ws_settings = {"path": path}
        if host:
            ws_settings["host"] = host
        stream["wsSettings"] = ws_settings
    elif network == "grpc":
        stream["grpcSettings"] = {"serviceName": path.lstrip("/") or path or "GunService"}
    elif network in {"http", "h2"}:
        stream["network"] = "http"
        http_settings = {"path": path}
        if host:
            http_settings["host"] = [host]
        stream["httpSettings"] = http_settings
    elif network == "httpupgrade":
        httpupgrade = {"path": path}
        if host:
            httpupgrade["host"] = host
        stream["httpupgradeSettings"] = httpupgrade
    elif network == "kcp":
        kcp_settings = {}
        if path:
            kcp_settings["seed"] = path
        if header_type not in {"none", ""}:
            kcp_settings["header"] = {"type": header_type}
        stream["kcpSettings"] = kcp_settings
    else:
        raise ValueError(f"暂不支持的 network 类型: {network}")

    return stream


def build_xray_outbound(node):
    protocol = node["protocol"]
    if protocol in {"vmess", "vless"}:
        user = {"id": node["uuid"]}
        if protocol == "vmess":
            user["alterId"] = int(node.get("alter_id", 0))
            user["security"] = node.get("security") or "auto"
        else:
            user["encryption"] = "none"
            flow = (node.get("flow") or "").strip()
            if flow:
                user["flow"] = flow
        return {
            "tag": f"relay-{node['id']}",
            "protocol": protocol,
            "settings": {
                "vnext": [
                    {
                        "address": node["address"],
                        "port": int(node["port"]),
                        "users": [user],
                    }
                ]
            },
            "streamSettings": build_stream_settings(node),
        }

    if protocol == "trojan":
        return {
            "tag": f"relay-{node['id']}",
            "protocol": "trojan",
            "settings": {
                "servers": [
                    {
                        "address": node["address"],
                        "port": int(node["port"]),
                        "password": node["password"],
                    }
                ]
            },
            "streamSettings": build_stream_settings(node),
        }

    if protocol == "shadowsocks":
        if node.get("plugin"):
            raise ValueError(f"Xray 暂不支持带 plugin 的 SS 节点：{node['name']}")
        return {
            "tag": f"relay-{node['id']}",
            "protocol": "shadowsocks",
            "settings": {
                "servers": [
                    {
                        "address": node["address"],
                        "port": int(node["port"]),
                        "method": node["method"],
                        "password": node["password"],
                    }
                ]
            },
        }

    raise ValueError(f"Xray 暂不支持该协议：{protocol}")


def generate_xray_config(nodes, settings):
    inbounds = []
    outbounds = []
    rules = []

    for node in nodes:
        if normalize_kernel(node.get("kernel")) != "xray":
            continue
        node_id = node["id"]
        inbound_tag = f"socks-{node_id}"
        outbound_tag = f"relay-{node_id}"
        inbounds.append(
            {
                "tag": inbound_tag,
                "listen": "0.0.0.0",
                "port": int(node["local_port"]),
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": False,
                },
            }
        )
        outbounds.append(build_xray_outbound(node))
        rules.append(
            {
                "type": "field",
                "inboundTag": [inbound_tag],
                "outboundTag": outbound_tag,
            }
        )

    outbounds.extend(
        [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ]
    )

    return {
        "log": {"loglevel": normalize_xray_log_level(settings.get("xray_log_level"))},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "AsIs",
            "rules": rules,
        },
    }


def build_singbox_outbound(node):
    protocol = node["protocol"]
    network = (node.get("network") or "tcp").strip().lower()

    transport = None
    if protocol in {"vmess", "vless", "trojan"}:
        transport = {"type": network}
        if network == "ws":
            transport["path"] = node["path"]
            host = (node.get("host") or "").strip()
            if host:
                transport["headers"] = {"Host": host}
        elif network == "http":
            transport["path"] = node["path"]
            host = (node.get("host") or "").strip()
            if host:
                transport["host"] = [host]
        elif network == "grpc":
            transport["service_name"] = node["path"].lstrip("/") or node["path"] or "GunService"
        elif network == "httpupgrade":
            transport["path"] = node["path"]
            host = (node.get("host") or "").strip()
            if host:
                transport["host"] = host
        elif network == "tcp":
            if protocol == "vmess":
                transport["type"] = "http"
                transport["path"] = node["path"]
                host = (node.get("host") or "").strip()
                if host:
                    transport["host"] = [host]
            else:
                transport = None
        else:
            raise ValueError(f"sing-box 暂不支持该 network 类型: {network}")

    if protocol == "vmess":
        outbound = {
            "type": "vmess",
            "tag": f"relay-{node['id']}",
            "server": node["address"],
            "server_port": int(node["port"]),
            "uuid": node["uuid"],
            "alter_id": int(node.get("alter_id", 0)),
            "security": node.get("security") or "auto",
        }
    elif protocol == "vless":
        outbound = {
            "type": "vless",
            "tag": f"relay-{node['id']}",
            "server": node["address"],
            "server_port": int(node["port"]),
            "uuid": node["uuid"],
        }
        flow = (node.get("flow") or "").strip()
        if flow:
            outbound["flow"] = flow
    elif protocol == "trojan":
        outbound = {
            "type": "trojan",
            "tag": f"relay-{node['id']}",
            "server": node["address"],
            "server_port": int(node["port"]),
            "password": node["password"],
        }
    elif protocol == "shadowsocks":
        outbound = {
            "type": "shadowsocks",
            "tag": f"relay-{node['id']}",
            "server": node["address"],
            "server_port": int(node["port"]),
            "method": node["method"],
            "password": node["password"],
        }
        if node.get("plugin"):
            outbound["plugin"] = node["plugin"]
    elif protocol == "hysteria2":
        outbound = {
            "type": "hysteria2",
            "tag": f"relay-{node['id']}",
            "server": node["address"],
            "server_port": int(node["port"]),
            "password": node["password"],
            "tls": {
                "enabled": True,
                "server_name": (node.get("sni") or node["address"]).strip(),
                "insecure": bool(node.get("allow_insecure")),
            },
        }
        if node.get("obfs"):
            outbound["obfs"] = {
                "type": node["obfs"],
                "password": node.get("obfs_password", ""),
            }
        alpn = (node.get("alpn") or "").strip()
        if alpn:
            outbound["tls"]["alpn"] = [item.strip() for item in alpn.split(",") if item.strip()]
        return outbound
    elif protocol == "tuic":
        outbound = {
            "type": "tuic",
            "tag": f"relay-{node['id']}",
            "server": node["address"],
            "server_port": int(node["port"]),
            "uuid": node["uuid"],
            "password": node["password"],
            "tls": {
                "enabled": True,
                "server_name": (node.get("sni") or node["address"]).strip(),
                "insecure": bool(node.get("allow_insecure")),
            },
        }
        if node.get("congestion_control"):
            outbound["congestion_control"] = node["congestion_control"]
        if node.get("udp_relay_mode"):
            outbound["udp_relay_mode"] = node["udp_relay_mode"]
        if node.get("heartbeat"):
            outbound["heartbeat"] = node["heartbeat"]
        if node.get("zero_rtt_handshake"):
            outbound["zero_rtt_handshake"] = bool(node["zero_rtt_handshake"])
        alpn = (node.get("alpn") or "").strip()
        if alpn:
            outbound["tls"]["alpn"] = [item.strip() for item in alpn.split(",") if item.strip()]
        return outbound
    else:
        raise ValueError(f"sing-box 暂不支持该协议：{protocol}")

    if transport:
        outbound["transport"] = transport

    if protocol in {"vmess", "vless", "trojan"}:
        if normalize_tls(node.get("tls")) == "tls":
            outbound["tls"] = {
                "enabled": True,
                "server_name": (node.get("sni") or node.get("host") or node["address"]).strip(),
                "insecure": bool(node.get("allow_insecure")),
            }
            alpn = (node.get("alpn") or "").strip()
            if alpn:
                outbound["tls"]["alpn"] = [item.strip() for item in alpn.split(",") if item.strip()]
        elif protocol == "trojan":
            outbound["tls"] = {
                "enabled": True,
                "server_name": (node.get("sni") or node.get("host") or node["address"]).strip(),
                "insecure": bool(node.get("allow_insecure")),
            }
        else:
            outbound["tls"] = {"enabled": False}

    return outbound


def generate_singbox_single_config(nodes, settings):
    inbounds = []
    outbounds = []
    route_rules = []

    for node in nodes:
        if normalize_kernel(node.get("kernel")) != "sing-box":
            continue
        node_id = node["id"]
        inbound_tag = f"socks-{node_id}"
        outbound_tag = f"relay-{node_id}"
        inbounds.append(
            {
                "type": "mixed",
                "tag": inbound_tag,
                "listen": "0.0.0.0",
                "listen_port": int(node["local_port"]),
            }
        )
        outbounds.append(
            {
                **build_singbox_outbound(node),
                "tag": outbound_tag,
            }
        )
        route_rules.append(
            {
                "inbound": [inbound_tag],
                "outbound": outbound_tag,
            }
        )

    outbounds.extend(
        [
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ]
    )

    return {
        "log": {"level": normalize_singbox_log_level(settings.get("singbox_log_level")), "timestamp": True},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {
            "auto_detect_interface": True,
            "rules": route_rules,
            "final": "direct",
        },
    }


def singbox_node_config_path(node_id: str) -> Path:
    return SINGBOX_CONFIG_DIR / f"{node_id}.json"


def generate_singbox_node_config(node, settings):
    outbound_tag = node["id"]
    return {
        "log": {"level": normalize_singbox_log_level(settings.get("singbox_log_level")), "timestamp": True},
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "0.0.0.0",
                "listen_port": int(node["local_port"]),
            }
        ],
        "outbounds": [
            {
                **build_singbox_outbound(node),
                "tag": outbound_tag,
            },
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "auto_detect_interface": True,
            "final": outbound_tag,
        },
    }


def write_singbox_node_configs(nodes, settings):
    SINGBOX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    expected = set()
    for node in nodes:
        if normalize_kernel(node.get("kernel")) != "sing-box":
            continue
        path = singbox_node_config_path(node["id"])
        atomic_write_json(path, generate_singbox_node_config(node, settings))
        expected.add(path.name)

    for path in SINGBOX_CONFIG_DIR.glob("*.json"):
        if path.name not in expected:
            path.unlink(missing_ok=True)


def write_singbox_configs(nodes, settings):
    if SINGBOX_MODE == "per_node":
        write_singbox_node_configs(nodes, settings)
        atomic_write_json(Path(SINGBOX_CONFIG), {"log": {"level": normalize_singbox_log_level(settings.get("singbox_log_level"))}})
        return
    atomic_write_json(Path(SINGBOX_CONFIG), generate_singbox_single_config(nodes, settings))
    SINGBOX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for path in SINGBOX_CONFIG_DIR.glob("*.json"):
        path.unlink(missing_ok=True)


def persist_and_reload(nodes):
    previous_nodes = load_nodes()
    settings = load_settings()
    xray_config = generate_xray_config(nodes, settings)
    atomic_write_json(NODES_PATH, nodes)
    atomic_write_json(Path(XRAY_CONFIG), xray_config)
    write_singbox_configs(nodes, settings)
    try:
        restart_cores(nodes)
    except Exception:
        atomic_write_json(NODES_PATH, previous_nodes)
        atomic_write_json(Path(XRAY_CONFIG), generate_xray_config(previous_nodes, settings))
        write_singbox_configs(previous_nodes, settings)
        restart_cores(previous_nodes)
        raise


def wait_port_closed(host: str, port: int, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) != 0:
                return
        time.sleep(0.1)


def stop_xray():
    global XRAY
    if XRAY is None:
        return
    proc = XRAY
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    XRAY = None
    wait_port_closed("127.0.0.1", 11080, timeout=5)


def stop_singbox_node(node_id: str):
    proc = SINGBOX_PROCS.get(node_id)
    if proc is None:
        return
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    SINGBOX_PROCS.pop(node_id, None)


def stop_all_singbox():
    for node_id in list(SINGBOX_PROCS):
        stop_singbox_node(node_id)


def stop_singbox_single():
    global SINGBOX
    if SINGBOX is None:
        return
    proc = SINGBOX
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    SINGBOX = None


def start_xray():
    global XRAY
    proc = subprocess.Popen(
        [XRAY_BIN, "run", "-config", XRAY_CONFIG],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    time.sleep(0.4)
    if proc.poll() is not None:
        output = ""
        try:
            output = (proc.stdout.read() or "").strip()
        except Exception:
            output = ""
        raise RuntimeError(f"Xray 启动失败，请检查节点配置是否正确。{output}".strip())
    threading.Thread(target=forward_xray_output, args=(proc,), daemon=True).start()
    XRAY = proc


def start_singbox_node(node):
    node_id = node["id"]
    config_path = singbox_node_config_path(node_id)
    proc = subprocess.Popen(
        [SINGBOX_BIN, "run", "-c", str(config_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    time.sleep(0.4)
    if proc.poll() is not None:
        output = ""
        try:
            output = (proc.stdout.read() or "").strip()
        except Exception:
            output = ""
        raise RuntimeError(f"sing-box 节点 {node.get('name', node_id)} 启动失败，请检查节点配置是否正确。{output}".strip())
    threading.Thread(target=forward_proc_output, args=(proc, f"sing-box:{node.get('name', node_id)}"), daemon=True).start()
    SINGBOX_PROCS[node_id] = proc


def start_singbox_single():
    global SINGBOX
    proc = subprocess.Popen(
        [SINGBOX_BIN, "run", "-c", SINGBOX_CONFIG],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    time.sleep(0.4)
    if proc.poll() is not None:
        output = ""
        try:
            output = (proc.stdout.read() or "").strip()
        except Exception:
            output = ""
        raise RuntimeError(f"sing-box 启动失败，请检查节点配置是否正确。{output}".strip())
    threading.Thread(target=forward_proc_output, args=(proc, "sing-box"), daemon=True).start()
    SINGBOX = proc


def restart_cores(nodes):
    with CORE_LOCK:
        stop_xray()
        stop_singbox_single()
        stop_all_singbox()
        if any(normalize_kernel(node.get("kernel")) == "xray" for node in nodes):
            start_xray()
        singbox_nodes = [node for node in nodes if normalize_kernel(node.get("kernel")) == "sing-box"]
        if SINGBOX_MODE == "per_node":
            for node in singbox_nodes:
                start_singbox_node(node)
        elif singbox_nodes:
            start_singbox_single()


def redirect(handler, location: str = "/", flash: str | None = None, error: bool = False):
    handler.send_response(303)
    if flash is not None:
        set_flash_headers(handler, flash, error)
    handler.send_header("Location", location)
    handler.end_headers()


class RelayAdminHandler(BaseHTTPRequestHandler):
    server_version = "relay-admin/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if parsed.path != "/":
            self.send_error(404)
            return

        nodes = load_nodes()
        settings = load_settings()
        flash, error = read_flash(self)
        next_local_port = next_port(nodes)

        flash_html = ""
        if flash:
            tone = "#fff0ef" if error else "#fff8e8"
            flash_html = (
                f'<div class="flash" style="background:{tone};">{html.escape(flash)}</div>'
            )

        rows = []
        for node in nodes:
            socks = f"socks5://127.0.0.1:{node['local_port']}#{node['name']}"
            hint_parts = [normalize_kernel(node.get("kernel")), node["protocol"]]
            network = (node.get("network") or "").strip()
            if network:
                hint_parts.append(network)
            rows.append(
                f"""
                <tr>
                  <td>
                    <strong>{html.escape(node['name'])}</strong><br>
                    <span class="hint">{html.escape(' / '.join(hint_parts))}</span>
                  </td>
                  <td class="socks">{html.escape(socks)}</td>
                  <td>{html.escape(node['address'])}:{int(node['port'])}</td>
                  <td>
                    <div class="actions">
                      <button
                        type="button"
                        class="plain"
                        data-edit-id="{html.escape(node['id'])}"
                        data-edit-name="{html.escape(node['name'])}"
                        data-edit-port="{int(node['local_port'])}"
                        data-edit-kernel="{html.escape(normalize_kernel(node.get('kernel')))}"
                        data-edit-link="{html.escape(node['link']) if node.get('link') else ''}"
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        class="danger"
                        data-delete-id="{html.escape(node['id'])}"
                        data-delete-name="{html.escape(node['name'])}"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
                """
            )
        table_html = "\n".join(rows) if rows else '<tr><td colspan="4">当前还没有节点。</td></tr>'

        body = f"""
        <h1>Xray 中转管理</h1>
        <p class="sub">在这里导入分享链接，系统会生成本地 <code>socks5://127.0.0.1:端口</code> 节点，随后你再把它加到 daed。</p>
        {flash_html}
        <div class="grid">
          <section class="card">
            <h2>当前中转节点</h2>
            <p class="note">请确保你的 dae routing 中保留 <code>pname(xray) -&gt; must_direct</code>，避免出现回环。</p>
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>本地 SOCKS5</th>
                  <th>上游节点</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {table_html}
              </tbody>
            </table>
          </section>
          <section class="card">
            <h2>导入分享链接</h2>
            <form method="post" action="/import-vmess">
              <div class="field">
                <label for="share_link">分享链接</label>
                <textarea id="share_link" name="share_link" placeholder="vmess:// / vless:// / trojan:// / ss:// / hysteria2:// / tuic://"></textarea>
              </div>
              <div class="row3">
                <div class="field">
                  <label for="name_override">节点名称覆盖</label>
                  <input id="name_override" name="name_override" placeholder="可选，不填则使用分享链接名称">
                </div>
                <div class="field">
                  <label for="local_port">本地端口</label>
                  <input id="local_port" name="local_port" value="{next_local_port}" placeholder="{next_local_port}">
                </div>
                <div class="field">
                  <label for="kernel">内核</label>
                  <select id="kernel" name="kernel">
                    <option value="xray">xray</option>
                    <option value="sing-box">sing-box</option>
                  </select>
                </div>
              </div>
              <button type="submit">导入并重载</button>
            </form>
            <p class="hint">当前页面支持 <code>vmess://</code>、<code>vless://</code>、<code>trojan://</code>、<code>ss://</code>、<code>hysteria2://</code>、<code>tuic://</code>。可按节点选择 <code>xray</code> 或 <code>sing-box</code> 内核。</p>
          </section>
          <section class="card">
            <h2>日志级别</h2>
            <form method="post" action="/save-settings">
              <div class="row">
                <div class="field">
                  <label for="xray_log_level">Xray 日志</label>
                  <select id="xray_log_level" name="xray_log_level">
                    <option value="debug" {"selected" if settings["xray_log_level"] == "debug" else ""}>debug</option>
                    <option value="info" {"selected" if settings["xray_log_level"] == "info" else ""}>info</option>
                    <option value="warning" {"selected" if settings["xray_log_level"] == "warning" else ""}>warning</option>
                    <option value="error" {"selected" if settings["xray_log_level"] == "error" else ""}>error</option>
                  </select>
                </div>
                <div class="field">
                  <label for="singbox_log_level">sing-box 日志</label>
                  <select id="singbox_log_level" name="singbox_log_level">
                    <option value="trace" {"selected" if settings["singbox_log_level"] == "trace" else ""}>trace</option>
                    <option value="debug" {"selected" if settings["singbox_log_level"] == "debug" else ""}>debug</option>
                    <option value="info" {"selected" if settings["singbox_log_level"] == "info" else ""}>info</option>
                    <option value="warn" {"selected" if settings["singbox_log_level"] == "warn" else ""}>warn</option>
                    <option value="error" {"selected" if settings["singbox_log_level"] == "error" else ""}>error</option>
                    <option value="fatal" {"selected" if settings["singbox_log_level"] == "fatal" else ""}>fatal</option>
                    <option value="panic" {"selected" if settings["singbox_log_level"] == "panic" else ""}>panic</option>
                  </select>
                </div>
              </div>
              <button type="submit">保存日志设置</button>
            </form>
          </section>
        </div>
        """
        payload = html_page("Xray 中转管理", body)
        self.send_response(200)
        clear_flash_headers(self)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        form = parse_qs(raw)

        try:
            if parsed.path == "/import-vmess":
                nodes = load_nodes()
                local_port_raw = form.get("local_port", [""])[0].strip()
                local_port = int(local_port_raw) if local_port_raw else next_port(nodes)
                if local_port <= 0 or local_port > 65535:
                    raise ValueError("本地端口必须在 1 到 65535 之间")
                if any(int(node["local_port"]) == local_port for node in nodes):
                    raise ValueError(f"本地端口已存在: {local_port}")
                share_link = form.get("share_link", [""])[0]
                name_override = form.get("name_override", [""])[0]
                kernel = normalize_kernel(form.get("kernel", ["xray"])[0])
                node = parse_share_link(share_link, local_port, name_override)
                node["kernel"] = kernel
                validate_kernel_for_node(node)
                nodes.append(node)
                persist_and_reload(nodes)
                redirect(self, "/", flash=f"已导入节点“{node['name']}”，内核 {kernel}，本地端口 {local_port}")
                return

            if parsed.path == "/delete":
                target_id = form.get("id", [""])[0]
                nodes = load_nodes()
                new_nodes = [node for node in nodes if node["id"] != target_id]
                if len(new_nodes) == len(nodes):
                    raise ValueError("未找到要删除的节点")
                persist_and_reload(new_nodes)
                redirect(self, "/", flash="节点已删除，Xray 已自动重载")
                return

            if parsed.path == "/edit":
                target_id = form.get("id", [""])[0]
                nodes = load_nodes()
                target = next((node for node in nodes if node["id"] == target_id), None)
                if target is None:
                    raise ValueError("未找到要编辑的节点")
                local_port_raw = form.get("local_port", [""])[0].strip()
                local_port = int(local_port_raw) if local_port_raw else int(target["local_port"])
                if local_port <= 0 or local_port > 65535:
                    raise ValueError("本地端口必须在 1 到 65535 之间")
                if any(int(node["local_port"]) == local_port and node["id"] != target_id for node in nodes):
                    raise ValueError(f"本地端口已存在: {local_port}")
                share_link = form.get("share_link", [""])[0]
                name_override = form.get("name_override", [""])[0]
                kernel = normalize_kernel(form.get("kernel", [target.get("kernel", "xray")])[0])
                updated = update_node(target, share_link, local_port, name_override)
                updated["kernel"] = kernel
                validate_kernel_for_node(updated)
                new_nodes = [updated if node["id"] == target_id else node for node in nodes]
                persist_and_reload(new_nodes)
                redirect(self, "/", flash=f"已更新节点“{updated['name']}”，内核 {kernel}")
                return

            if parsed.path == "/save-settings":
                settings = load_settings()
                settings["xray_log_level"] = normalize_xray_log_level(form.get("xray_log_level", [settings["xray_log_level"]])[0])
                settings["singbox_log_level"] = normalize_singbox_log_level(
                    form.get("singbox_log_level", [settings["singbox_log_level"]])[0]
                )
                atomic_write_json(SETTINGS_PATH, settings)
                nodes = load_nodes()
                atomic_write_json(Path(XRAY_CONFIG), generate_xray_config(nodes, settings))
                write_singbox_configs(nodes, settings)
                restart_cores(nodes)
                redirect(self, "/", flash="日志级别已更新")
                return

            self.send_error(404)
        except Exception as exc:
            redirect(self, "/", flash=str(exc), error=True)

    def log_message(self, fmt, *args):
        return


def ensure_bootstrap():
    nodes = load_nodes()
    settings = load_settings()
    changed = False
    for node in nodes:
        kernel = normalize_kernel(node.get("kernel"))
        if node.get("kernel") != kernel:
            node["kernel"] = kernel
            changed = True
        if "link" not in node:
            node["link"] = ""
            changed = True
    if changed:
        atomic_write_json(NODES_PATH, nodes)
    atomic_write_json(SETTINGS_PATH, settings)
    atomic_write_json(Path(XRAY_CONFIG), generate_xray_config(nodes, settings))
    write_singbox_configs(nodes, settings)


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_bootstrap()
    atexit.register(stop_xray)
    atexit.register(stop_singbox_single)
    atexit.register(stop_all_singbox)
    bootstrap_nodes = load_nodes()
    restart_cores(bootstrap_nodes)
    server = DualStackServer(("::", ADMIN_PORT), RelayAdminHandler)
    server.serve_forever()
