import atexit
import signal

from relay_admin import runtime
from relay_admin.cores import cleanup_cores, ensure_bootstrap, handle_termination, restart_cores, stop_all_singbox, stop_singbox_single, stop_xray
from relay_admin.server import create_admin_server
from relay_admin.storage import load_nodes


def main():
    runtime.DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_bootstrap()
    atexit.register(stop_xray)
    atexit.register(stop_singbox_single)
    atexit.register(stop_all_singbox)
    signal.signal(signal.SIGTERM, handle_termination)
    signal.signal(signal.SIGINT, handle_termination)
    restart_cores(load_nodes())
    runtime.SERVER = create_admin_server(runtime.ADMIN_PORT)
    try:
        runtime.SERVER.serve_forever()
    finally:
        try:
            runtime.SERVER.server_close()
        finally:
            cleanup_cores()


if __name__ == "__main__":
    main()
