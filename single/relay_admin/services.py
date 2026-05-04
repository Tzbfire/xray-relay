from pathlib import Path

from . import runtime
from .config_builders import generate_xray_config
from .cores import persist_and_reload, restart_cores, write_singbox_configs
from .nodes import next_port, validate_kernel_for_node
from .normalizers import normalize_kernel, normalize_singbox_log_level, normalize_xray_log_level
from .share_links import parse_share_link, update_node
from .storage import atomic_write_json, load_nodes, load_settings


def parse_local_port(raw_value: str, fallback: int | None = None) -> int:
    value = (raw_value or "").strip()
    local_port = int(value) if value else fallback
    if local_port is None:
        raise ValueError("缺少本地端口")
    if local_port <= 0 or local_port > 65535:
        raise ValueError("本地端口必须在 1 到 65535 之间")
    return local_port


def ensure_port_available(nodes, local_port: int, exclude_node_id: str | None = None):
    for node in nodes:
        if int(node["local_port"]) != local_port:
            continue
        if exclude_node_id and node["id"] == exclude_node_id:
            continue
        raise ValueError(f"本地端口已存在: {local_port}")


def import_node(form):
    nodes = load_nodes()
    local_port = parse_local_port(form.get("local_port", [""])[0], fallback=next_port(nodes))
    ensure_port_available(nodes, local_port)
    share_link = form.get("share_link", [""])[0]
    name_override = form.get("name_override", [""])[0]
    kernel = normalize_kernel(form.get("kernel", ["xray"])[0])
    node = parse_share_link(share_link, local_port, name_override)
    node["kernel"] = kernel
    validate_kernel_for_node(node)
    nodes.append(node)
    persist_and_reload(nodes)
    return f"已导入节点“{node['name']}”，内核 {kernel}，本地端口 {local_port}"


def delete_node(form):
    target_id = form.get("id", [""])[0]
    nodes = load_nodes()
    new_nodes = [node for node in nodes if node["id"] != target_id]
    if len(new_nodes) == len(nodes):
        raise ValueError("未找到要删除的节点")
    persist_and_reload(new_nodes)
    return "节点已删除，Xray 已自动重载"


def edit_node(form):
    target_id = form.get("id", [""])[0]
    nodes = load_nodes()
    target = next((node for node in nodes if node["id"] == target_id), None)
    if target is None:
        raise ValueError("未找到要编辑的节点")

    local_port = parse_local_port(form.get("local_port", [""])[0], fallback=int(target["local_port"]))
    ensure_port_available(nodes, local_port, exclude_node_id=target_id)
    share_link = form.get("share_link", [""])[0]
    name_override = form.get("name_override", [""])[0]
    kernel = normalize_kernel(form.get("kernel", [target.get("kernel", "xray")])[0])
    updated = update_node(target, share_link, local_port, name_override)
    updated["kernel"] = kernel
    validate_kernel_for_node(updated)
    new_nodes = [updated if node["id"] == target_id else node for node in nodes]
    persist_and_reload(new_nodes)
    return f"已更新节点“{updated['name']}”，内核 {kernel}"


def save_settings(form):
    settings = load_settings()
    settings["xray_log_level"] = normalize_xray_log_level(form.get("xray_log_level", [settings["xray_log_level"]])[0])
    settings["singbox_log_level"] = normalize_singbox_log_level(
        form.get("singbox_log_level", [settings["singbox_log_level"]])[0]
    )
    atomic_write_json(runtime.SETTINGS_PATH, settings)
    nodes = load_nodes()
    atomic_write_json(Path(runtime.XRAY_CONFIG), generate_xray_config(nodes, settings))
    write_singbox_configs(nodes, settings)
    restart_cores(nodes)
    return "日志级别已更新"
