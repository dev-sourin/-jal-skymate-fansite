"""Rebuild the SQLite database from CSV files in ./data.

Usage:
    python scripts/import_csv.py

This MVP intentionally does not scrape JAL pages. Replace the CSV files only with
facts that the operator is permitted to use and publish.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.db import reload_demo_data  # noqa: E402

if __name__ == "__main__":
    reload_demo_data()
    print(f"Database rebuilt: {ROOT / 'skymate.db'}")
