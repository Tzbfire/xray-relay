import json
import os
import tempfile
from pathlib import Path

from . import runtime
from .normalizers import normalize_singbox_log_level, normalize_xray_log_level


def load_nodes():
    if not runtime.NODES_PATH.exists():
        return []
    with runtime.NODES_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("nodes.json 必须是数组结构")
    return data


def load_settings():
    defaults = {
        "xray_log_level": "warning",
        "singbox_log_level": "info",
    }
    if not runtime.SETTINGS_PATH.exists():
        return defaults
    with runtime.SETTINGS_PATH.open("r", encoding="utf-8") as fh:
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
