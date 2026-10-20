"""Replace an already running copy of the GUI instead of failing on its port."""

from __future__ import annotations

import logging
import socket
import time

import requests

logger = logging.getLogger(__name__)

APP_ID = "elAPI_Plugins"

# Every page of the older versions (which have no /ping) carries this footer link.
_LEGACY_MARKER = "sfb1638/elAPI_Plugins"


def port_in_use(host: str, port: int) -> bool:
    """True if something accepts connections on host:port."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _identify(base: str) -> str | None:
    """Return "current", "legacy" or None for whatever answers at ``base``."""
    try:
        reply = requests.get(f"{base}/ping", timeout=2)
        if reply.ok and reply.json().get("app") == APP_ID:
            return "current"
        if reply.status_code == 404:
            page = requests.get(f"{base}/setup", timeout=2)
            if page.ok and _LEGACY_MARKER in page.text:
                return "legacy"
    except (requests.RequestException, ValueError, AttributeError):
        pass
    return None


def stop_running_instance(host: str, port: int, timeout: float = 5.0) -> bool:
    """Ask a running copy of this app on host:port to quit.

    Returns True once the port is free. Anything that is not this app is left
    alone (False), so an unrelated program on the port is never touched.
    """
    base = f"http://{host}:{port}"
    kind = _identify(base)
    if kind is None:
        return False

    logger.info("Stopping the %s copy already running on port %d.", kind, port)
    # "/quit" is immediate; "/shutdown" of a current copy waits for page reloads,
    # but an older copy's "/shutdown" is immediate.
    try:
        requests.post(
            f"{base}/quit" if kind == "current" else f"{base}/shutdown", timeout=2
        )
    except requests.RequestException:
        pass  # the old copy may drop the connection while it exits

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not port_in_use(host, port):
            return True
        time.sleep(0.2)
    return False
