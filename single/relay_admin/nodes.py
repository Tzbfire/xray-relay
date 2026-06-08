from .normalizers import normalize_kernel


def allowed_kernels(protocol: str, node: dict | None = None):
    if protocol in {"hysteria2", "tuic", "anytls"}:
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


def next_port(nodes):
    used = {int(node["local_port"]) for node in nodes}
    port = 11080
    while port in used:
        port += 1
    return port
