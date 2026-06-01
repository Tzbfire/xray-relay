from .nodes import normalize_kernel
from .normalizers import normalize_singbox_log_level, normalize_tls, normalize_xray_log_level


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
    header_type = node.get("header_type") or "none"

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
        outbounds.append({**build_singbox_outbound(node), "tag": outbound_tag})
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
            {**build_singbox_outbound(node), "tag": outbound_tag},
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "auto_detect_interface": True,
            "final": outbound_tag,
        },
    }
