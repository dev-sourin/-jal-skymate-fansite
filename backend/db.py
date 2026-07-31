from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from .config import DATA_DIR, DB_PATH, TIMEZONE

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS airports (
    iata_code TEXT PRIMARY KEY,
    name_ja TEXT NOT NULL,
    city TEXT NOT NULL,
    region TEXT NOT NULL,
    pfc_yen INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS routes (
    id TEXT PRIMARY KEY,
    origin_iata TEXT NOT NULL REFERENCES airports(iata_code),
    destination_iata TEXT NOT NULL REFERENCES airports(iata_code),
    carrier_code TEXT NOT NULL,
    typical_minutes INTEGER NOT NULL,
    historical_tendency INTEGER NOT NULL DEFAULT 8,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id TEXT NOT NULL REFERENCES routes(id),
    flight_no TEXT NOT NULL,
    departure_time TEXT NOT NULL,
    arrival_time TEXT NOT NULL,
    operating_days TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    UNIQUE(route_id, flight_no, departure_time, valid_from)
);

CREATE TABLE IF NOT EXISTS fares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id TEXT NOT NULL REFERENCES routes(id),
    fare_product TEXT NOT NULL,
    cabin_class TEXT NOT NULL,
    amount_yen INTEGER NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    source_label TEXT NOT NULL,
    UNIQUE(route_id, fare_product, cabin_class, valid_from)
);

CREATE TABLE IF NOT EXISTS availability_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_no TEXT NOT NULL,
    flight_date TEXT NOT NULL,
    cabin_class TEXT NOT NULL,
    fare_product TEXT,
    status TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_label TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_schedule_route_dates
ON schedules(route_id, valid_from, valid_to);

CREATE INDEX IF NOT EXISTS idx_availability_lookup
ON availability_observations(flight_no, flight_date, cabin_class, source_type, observed_at);

CREATE TABLE IF NOT EXISTS dataset_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _read_csv(name: str) -> list[dict[str, str]]:
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _resolve_date_token(value: str, today: date) -> str:
    token = value.strip().upper()
    if token == "TODAY":
        return today.isoformat()
    if token == "TOMORROW":
        return (today + timedelta(days=1)).isoformat()
    if token == "YESTERDAY":
        return (today - timedelta(days=1)).isoformat()
    return value


def _resolve_datetime_token(value: str, today: date) -> str:
    # Supported demo format: TODAY@HH:MM, TOMORROW@HH:MM, YESTERDAY@HH:MM
    if "@" not in value:
        return value
    day_token, time_part = value.split("@", 1)
    day = date.fromisoformat(_resolve_date_token(day_token, today))
    tz = ZoneInfo(TIMEZONE)
    return datetime.combine(day, datetime.strptime(time_part, "%H:%M").time(), tzinfo=tz).isoformat()


def initialize_database(force: bool = False) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if force and DB_PATH.exists():
        DB_PATH.unlink()

    with connection() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0] > 0 and not force:
            return

        for row in _read_csv("airports.csv"):
            conn.execute(
                "INSERT OR REPLACE INTO airports(iata_code,name_ja,city,region,pfc_yen) VALUES(?,?,?,?,?)",
                (row["iata_code"], row["name_ja"], row["city"], row["region"], int(row["pfc_yen"])),
            )

        for row in _read_csv("routes.csv"):
            conn.execute(
                """INSERT OR REPLACE INTO routes
                (id,origin_iata,destination_iata,carrier_code,typical_minutes,historical_tendency,active)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    row["id"], row["origin_iata"], row["destination_iata"], row["carrier_code"],
                    int(row["typical_minutes"]), int(row["historical_tendency"]), int(row["active"]),
                ),
            )

        for row in _read_csv("schedules.csv"):
            conn.execute(
                """INSERT OR REPLACE INTO schedules
                (route_id,flight_no,departure_time,arrival_time,operating_days,valid_from,valid_to)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    row["route_id"], row["flight_no"], row["departure_time"], row["arrival_time"],
                    row["operating_days"], row["valid_from"], row["valid_to"],
                ),
            )

        for row in _read_csv("fares.csv"):
            conn.execute(
                """INSERT OR REPLACE INTO fares
                (route_id,fare_product,cabin_class,amount_yen,valid_from,valid_to,source_label)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    row["route_id"], row["fare_product"], row["cabin_class"], int(row["amount_yen"]),
                    row["valid_from"], row["valid_to"], row["source_label"],
                ),
            )

        today = datetime.now(ZoneInfo(TIMEZONE)).date()
        for row in _read_csv("availability.csv"):
            flight_date = _resolve_date_token(row["flight_date"], today)
            observed_at = _resolve_datetime_token(row["observed_at"], today)
            expires_at = _resolve_datetime_token(row["expires_at"], today)
            conn.execute(
                """INSERT INTO availability_observations
                (flight_no,flight_date,cabin_class,fare_product,status,source_type,source_label,observed_at,expires_at,details_json)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["flight_no"], flight_date, row["cabin_class"], row.get("fare_product") or None,
                    row["status"], row["source_type"], row["source_label"], observed_at, expires_at,
                    json.dumps({"note": row.get("note", "")}, ensure_ascii=False),
                ),
            )

        now = datetime.now(ZoneInfo(TIMEZONE)).isoformat()
        meta = {
            "fare_version": "DEMO-2026-01",
            "schedule_version": "DEMO-SUMMER-01",
            "availability_version": now,
            "last_updated": now,
            "data_mode": "DEMO_SAMPLE",
        }
        conn.executemany(
            "INSERT OR REPLACE INTO dataset_meta(key,value) VALUES(?,?)",
            meta.items(),
        )


def reload_demo_data() -> None:
    initialize_database(force=True)
