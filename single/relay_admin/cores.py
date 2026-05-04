import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import runtime
from .config_builders import generate_singbox_node_config, generate_singbox_single_config, generate_xray_config
from .nodes import normalize_kernel
from .normalizers import normalize_singbox_log_level
from .storage import atomic_write_json, load_nodes, load_settings


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


def singbox_node_config_path(node_id: str) -> Path:
    return runtime.SINGBOX_CONFIG_DIR / f"{node_id}.json"


def write_singbox_node_configs(nodes, settings):
    runtime.SINGBOX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    expected = set()
    for node in nodes:
        if normalize_kernel(node.get("kernel")) != "sing-box":
            continue
        path = singbox_node_config_path(node["id"])
        atomic_write_json(path, generate_singbox_node_config(node, settings))
        expected.add(path.name)

    for path in runtime.SINGBOX_CONFIG_DIR.glob("*.json"):
        if path.name not in expected:
            path.unlink(missing_ok=True)


def write_singbox_configs(nodes, settings):
    if runtime.SINGBOX_MODE == "per_node":
        write_singbox_node_configs(nodes, settings)
        atomic_write_json(Path(runtime.SINGBOX_CONFIG), {"log": {"level": normalize_singbox_log_level(settings.get("singbox_log_level"))}})
        return
    atomic_write_json(Path(runtime.SINGBOX_CONFIG), generate_singbox_single_config(nodes, settings))
    runtime.SINGBOX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for path in runtime.SINGBOX_CONFIG_DIR.glob("*.json"):
        path.unlink(missing_ok=True)


def persist_and_reload(nodes):
    previous_nodes = load_nodes()
    settings = load_settings()
    xray_config = generate_xray_config(nodes, settings)
    atomic_write_json(runtime.NODES_PATH, nodes)
    atomic_write_json(Path(runtime.XRAY_CONFIG), xray_config)
    write_singbox_configs(nodes, settings)
    try:
        restart_cores(nodes)
    except Exception:
        atomic_write_json(runtime.NODES_PATH, previous_nodes)
        atomic_write_json(Path(runtime.XRAY_CONFIG), generate_xray_config(previous_nodes, settings))
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
    if runtime.XRAY is None:
        return
    proc = runtime.XRAY
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    runtime.XRAY = None
    wait_port_closed("127.0.0.1", 11080, timeout=5)


def stop_singbox_node(node_id: str):
    proc = runtime.SINGBOX_PROCS.get(node_id)
    if proc is None:
        return
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    runtime.SINGBOX_PROCS.pop(node_id, None)


def stop_all_singbox():
    for node_id in list(runtime.SINGBOX_PROCS):
        stop_singbox_node(node_id)


def stop_singbox_single():
    if runtime.SINGBOX is None:
        return
    proc = runtime.SINGBOX
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    runtime.SINGBOX = None


def cleanup_cores():
    with runtime.CORE_LOCK:
        stop_xray()
        stop_singbox_single()
        stop_all_singbox()


def request_shutdown(source: str):
    if runtime.SHUTDOWN_EVENT.is_set():
        return
    runtime.SHUTDOWN_EVENT.set()
    try:
        sys.stdout.write(f"[shutdown] received {source}, stopping relay cores\n")
        sys.stdout.flush()
    except Exception:
        pass
    if runtime.SERVER is not None:
        threading.Thread(target=runtime.SERVER.shutdown, daemon=True).start()


def handle_termination(signum, _frame):
    try:
        source = signal.Signals(signum).name
    except Exception:
        source = f"signal {signum}"
    request_shutdown(source)


def start_xray():
    proc = subprocess.Popen(
        [runtime.XRAY_BIN, "run", "-config", runtime.XRAY_CONFIG],
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
    runtime.XRAY = proc


def start_singbox_node(node):
    node_id = node["id"]
    config_path = singbox_node_config_path(node_id)
    proc = subprocess.Popen(
        [runtime.SINGBOX_BIN, "run", "-c", str(config_path)],
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
    runtime.SINGBOX_PROCS[node_id] = proc


def start_singbox_single():
    proc = subprocess.Popen(
        [runtime.SINGBOX_BIN, "run", "-c", runtime.SINGBOX_CONFIG],
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
    runtime.SINGBOX = proc


def restart_cores(nodes):
    with runtime.CORE_LOCK:
        stop_xray()
        stop_singbox_single()
        stop_all_singbox()
        if any(normalize_kernel(node.get("kernel")) == "xray" for node in nodes):
            start_xray()
        singbox_nodes = [node for node in nodes if normalize_kernel(node.get("kernel")) == "sing-box"]
        if runtime.SINGBOX_MODE == "per_node":
            for node in singbox_nodes:
                start_singbox_node(node)
        elif singbox_nodes:
            start_singbox_single()


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
        atomic_write_json(runtime.NODES_PATH, nodes)
    atomic_write_json(runtime.SETTINGS_PATH, settings)
    atomic_write_json(Path(runtime.XRAY_CONFIG), generate_xray_config(nodes, settings))
    write_singbox_configs(nodes, settings)
