"""Where the demo sends its data: read from the environment, then from the repo-root .env file."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _dotenv() -> dict[str, str]:
    path = REPO_ROOT / ".env"
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def setting(name: str, default: str) -> str:
    return os.environ.get(name) or _dotenv().get(name) or default


def api_url() -> str:
    return setting("GHOSTWATCH_API_URL", "http://localhost:8000/api/v1").rstrip("/")


def api_key() -> str:
    return setting("GHOSTWATCH_API_KEY", "")


def dashboard_url() -> str:
    return setting("GHOSTWATCH_DASHBOARD_URL", "http://localhost:3000").rstrip("/")
