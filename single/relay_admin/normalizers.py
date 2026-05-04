def truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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


def normalize_xray_log_level(value: str) -> str:
    val = (value or "warning").strip().lower()
    allowed = {"debug", "info", "warning", "error"}
    return val if val in allowed else "warning"


def normalize_singbox_log_level(value: str) -> str:
    val = (value or "info").strip().lower()
    allowed = {"trace", "debug", "info", "warn", "error", "fatal", "panic"}
    return val if val in allowed else "info"
