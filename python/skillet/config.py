"""Environment-driven configuration for the Skillet Flask app."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Tiny .env loader (no dependency). Existing env vars win."""
    env_path = path or BASE_DIR / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _get(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else default


def on_pythonanywhere() -> bool:
    """True when running inside a PythonAnywhere web app or console."""
    return bool(
        os.environ.get("PYTHONANYWHERE_DOMAIN")
        or os.environ.get("PYTHONANYWHERE_USER")
        or os.environ.get("PYTHONANYWHERE_SITE")
    )


def resolve_data_dir() -> Path:
    """Persistent data directory (database + uploaded photos).

    On PythonAnywhere this defaults to ``~/skillet-data`` — outside the code
    directory so deployments never touch user data. Locally it defaults to
    ``python/instance``. Override with ``SKILLET_DATA_DIR``.
    """
    override = _get("SKILLET_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if on_pythonanywhere():
        return (Path.home() / "skillet-data").resolve()
    return (BASE_DIR / "instance").resolve()


def resolve_database_uri(data_dir: Path) -> str:
    """SQLite connection URI. Override with ``DATABASE_URL`` (a sqlite:///
    URI or a bare filesystem path); otherwise ``<data_dir>/skillet.db``."""
    raw = _get("DATABASE_URL") or _get("SKILLET_DB_PATH")
    if raw:
        if raw.startswith("sqlite:///"):
            return raw
        if "://" in raw:
            return raw  # non-SQLite URL: let SQLAlchemy raise a clear error
        return f"sqlite:///{Path(raw).expanduser().resolve()}"
    return f"sqlite:///{data_dir / 'skillet.db'}"


class Config:
    """Reads database, session, and retailer settings from the environment."""

    def __init__(self) -> None:
        load_dotenv()
        self.DATA_DIR = resolve_data_dir()
        self.DATABASE_URI = resolve_database_uri(self.DATA_DIR)
        self.UPLOAD_DIR = Path(_get("SKILLET_UPLOAD_DIR") or (self.DATA_DIR / "uploads" / "recipe-photos"))
        self.APP_URL = _get("APP_URL") or _get("NEXT_PUBLIC_APP_URL") or "http://localhost:5000"
        self.APP_URL = self.APP_URL.rstrip("/")

        self.WALMART_CONSUMER_ID = _get("WALMART_CONSUMER_ID") or None
        self.WALMART_PRIVATE_KEY = _get("WALMART_PRIVATE_KEY") or None
        self.WALMART_ACCESS_TOKEN = _get("WALMART_ACCESS_TOKEN") or None
        self.WALMART_API_BASE = _get("WALMART_API_BASE") or "https://developer.api.walmart.com"
        self.WALMART_CART_ENDPOINT = _get("WALMART_CART_ENDPOINT") or None

        self.INSTACART_API_KEY = _get("INSTACART_API_KEY") or None
        self.INSTACART_API_BASE = _get("INSTACART_API_BASE") or "https://api.instacart.com/v2"
        self.INSTACART_SEARCH_PATH = _get("INSTACART_SEARCH_PATH") or "/products"
        self.INSTACART_CART_PATH = _get("INSTACART_CART_PATH") or "/carts"

        self.SECRET_KEY = _get("SECRET_KEY") or _get("FLASK_SECRET_KEY") or "skillet-dev-secret-change-me"
        self.MAX_PHOTO_BYTES = 5 * 1024 * 1024

    @property
    def is_configured(self) -> bool:
        return True

    def public_photo_url(self, path: str | None) -> str | None:
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.APP_URL}/media/{path.lstrip('/')}"
