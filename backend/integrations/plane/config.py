"""Configuration and status for the Plane integration.

The API key is read from the environment or from a file — never from the repo, never echoed.
"""
import os

DEFAULT_KEY_FILE = "/root/.config/plane/api_key"
DEFAULT_WEBHOOK_SECRET_FILE = "/etc/agentic-pmo/plane_webhook_secret"


def api_key() -> str:
    direct = os.getenv("PLANE_API_KEY", "").strip()
    if direct:
        return direct
    path = os.getenv("PLANE_API_KEY_FILE", DEFAULT_KEY_FILE)
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def base_url() -> str:
    return os.getenv("PLANE_BASE_URL", "https://plane.agenticpmo.tech").rstrip("/")


def workspace() -> str:
    return os.getenv("PLANE_WORKSPACE", "").strip()


def configured() -> bool:
    return bool(api_key() and workspace())


def status() -> dict:
    """Report shape without leaking the credential."""
    key = api_key()
    return {
        "configured": configured(),
        "base_url": base_url(),
        "workspace": workspace() or None,
        "api_key_present": bool(key),
        "api_key_length": len(key),
        "api_key_source": "env" if os.getenv("PLANE_API_KEY") else (
            os.getenv("PLANE_API_KEY_FILE", DEFAULT_KEY_FILE)
        ),
        "webhook_secret_present": bool(webhook_secret()),
        "webhook_secret_length": len(webhook_secret()),
    }


def webhook_secret() -> str:
    direct = os.getenv("PLANE_WEBHOOK_SECRET", "").strip()
    if direct:
        return direct
    path = os.getenv("PLANE_WEBHOOK_SECRET_FILE", DEFAULT_WEBHOOK_SECRET_FILE)
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""
