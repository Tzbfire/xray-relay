import base64
import json
import uuid
from urllib.parse import parse_qs, unquote, urlparse

from .normalizers import normalize_header_type, normalize_tls, truthy


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


def parse_anytls_link(link: str, local_port: int, name_override: str = ""):
    parsed = urlparse(link.strip())
    if parsed.scheme != "anytls":
        raise ValueError("不是 anytls:// 分享链接")
    params = parse_qs(parsed.query)
    insecure_value = params.get("allowInsecure", [None])[0]
    if insecure_value in (None, ""):
        insecure_value = params.get("insecure", ["0"])[0]
    network = (params.get("type", ["tcp"])[0] or "tcp").strip().lower()
    if network != "tcp":
        raise ValueError("AnyTLS 当前仅支持 type=tcp")
    node = {
        "id": f"node-{uuid.uuid4().hex[:8]}",
        "name": name_override.strip() or unquote(parsed.fragment or "") or parsed.hostname or f"anytls-{local_port}",
        "kernel": "sing-box",
        "protocol": "anytls",
        "link": link,
        "local_port": local_port,
        "address": parsed.hostname or "",
        "port": int(parsed.port or 443),
        "password": unquote(parsed.username or ""),
        "network": network,
        "tls": normalize_tls(params.get("security", ["tls"])[0]) or "tls",
        "sni": params.get("sni", [""])[0] or (parsed.hostname or ""),
        "alpn": params.get("alpn", [""])[0],
        "fingerprint": params.get("fp", [""])[0],
        "allow_insecure": truthy(insecure_value),
    }
    if node["tls"] != "tls":
        raise ValueError("AnyTLS 必须启用 TLS")
    if not node["address"] or not node["port"] or not node["password"]:
        raise ValueError("AnyTLS 链接缺少必要字段")
    return node


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
    if network == "grpc" and not path:
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
    if trimmed.startswith("anytls://"):
        return parse_anytls_link(trimmed, local_port, name_override)
    raise ValueError("当前只支持 vmess / vless / trojan / ss / hysteria2 / tuic / anytls 分享链接")


def update_node(existing_node: dict, link: str, local_port: int, name_override: str = ""):
    node = parse_share_link(link, local_port, name_override)
    node["id"] = existing_node["id"]
    return node
