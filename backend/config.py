from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
APP_DIR = BASE_DIR / "app"
DB_PATH = Path(os.getenv("SKYMATE_DB_PATH", BASE_DIR / "skymate.db"))
ADMIN_TOKEN = os.getenv("SKYMATE_ADMIN_TOKEN", "change-me-before-production")
TIMEZONE = "Asia/Tokyo"
