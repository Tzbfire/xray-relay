import os
import subprocess
import threading
from pathlib import Path


DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
NODES_PATH = DATA_DIR / "nodes.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "18080"))
XRAY_BIN = os.environ.get("XRAY_BIN", "/usr/local/bin/xray")
XRAY_CONFIG = os.environ.get("XRAY_CONFIG", "/data/xray-config.json")
SINGBOX_BIN = os.environ.get("SINGBOX_BIN", "/usr/local/bin/sing-box")
SINGBOX_CONFIG = os.environ.get("SINGBOX_CONFIG", "/data/singbox-config.json")
SINGBOX_CONFIG_DIR = Path(os.environ.get("SINGBOX_CONFIG_DIR", "/data/singbox.d"))
SINGBOX_MODE = os.environ.get("SINGBOX_MODE", "single").strip().lower()

XRAY: subprocess.Popen | None = None
SINGBOX: subprocess.Popen | None = None
SINGBOX_PROCS: dict[str, subprocess.Popen] = {}
CORE_LOCK = threading.Lock()
SERVER = None
SHUTDOWN_EVENT = threading.Event()
