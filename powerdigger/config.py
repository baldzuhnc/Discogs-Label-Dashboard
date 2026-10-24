import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(ROOT / ".env")

DISCOGS_TOKEN = os.environ.get("DISCOGS_TOKEN", "")
CURRENCY = os.environ.get("PD_CURRENCY", "EUR")
DB_PATH = Path(os.environ.get("PD_DB", ROOT / "powerdigger.db"))
LEGACY_DATA = ROOT / "Data"
USER_AGENT = "PowerDigger3000/2.0 +https://github.com/baldzuhnc/Power-Digger-3000"
# Details older than this get refreshed on the next label sync (prices and want/have drift).
DETAIL_MAX_AGE_DAYS = int(os.environ.get("PD_DETAIL_MAX_AGE_DAYS", "30"))
