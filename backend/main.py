from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import ADMIN_TOKEN, APP_DIR
from .db import initialize_database, reload_demo_data
from .search import dataset_meta, get_flight_detail, list_airports, search_flights

app = FastAPI(
    title="Unofficial Skymate Route Search API",
    version="0.1.0",
    description="非公式・非営利ファンサイト向けMVP。予約・決済機能はありません。",
)


@app.on_event("startup")
def startup() -> None:
    initialize_database()


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/airports")
def airports(q: str | None = None) -> dict:
    return {"airports": list_airports(q)}


@app.get("/api/v1/meta/dataset")
def meta() -> dict:
    return dataset_meta()


@app.get("/api/v1/destinations")
def destinations(
    origin: Annotated[str, Query(min_length=3, max_length=3)],
    date_value: Annotated[date, Query(alias="date")],
    destination: Annotated[str | None, Query(min_length=3, max_length=3)] = None,
    budget: Annotated[int | None, Query(ge=0)] = None,
    departure_period: Annotated[str, Query(pattern="^(all|morning|afternoon|evening|night)$")] = "all",
    cabin_class: Annotated[str, Query(pattern="^(ECONOMY|CLASS_J|FIRST)$")] = "ECONOMY",
    availability_filter: Annotated[str, Query(pattern="^(all|exact|reference|high|known)$")] = "all",
    sort: Annotated[str, Query(pattern="^(departure|price|duration|destination|availability)$")] = "departure",
) -> dict:
    return search_flights(
        origin=origin,
        destination=destination,
        flight_date=date_value,
        budget=budget,
        departure_period=departure_period,
        cabin_class=cabin_class,
        availability_filter=availability_filter,
        sort=sort,
    )


@app.get("/api/v1/timetable")
def timetable(
    origin: Annotated[str, Query(min_length=3, max_length=3)],
    destination: Annotated[str, Query(min_length=3, max_length=3)],
    date_value: Annotated[date, Query(alias="date")],
    cabin_class: Annotated[str, Query(pattern="^(ECONOMY|CLASS_J|FIRST)$")] = "ECONOMY",
) -> dict:
    return search_flights(
        origin=origin,
        destination=destination,
        flight_date=date_value,
        cabin_class=cabin_class,
    )


@app.get("/api/v1/flights/{flight_no}")
def flight_detail(
    flight_no: str,
    date_value: Annotated[date, Query(alias="date")],
    cabin_class: Annotated[str, Query(pattern="^(ECONOMY|CLASS_J|FIRST)$")] = "ECONOMY",
) -> dict:
    result = get_flight_detail(flight_no, date_value, cabin_class)
    if result is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return result


@app.get("/api/v1/availability")
def availability(
    flight_no: str,
    date_value: Annotated[date, Query(alias="date")],
    cabin_class: Annotated[str, Query(pattern="^(ECONOMY|CLASS_J|FIRST)$")] = "ECONOMY",
) -> dict:
    result = get_flight_detail(flight_no, date_value, cabin_class)
    if result is None:
        raise HTTPException(status_code=404, detail="Flight not found")
    return result["availability"]


@app.post("/api/v1/admin/reload-demo")
def admin_reload_demo(x_admin_token: Annotated[str | None, Header()] = None) -> dict[str, str]:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    reload_demo_data()
    return {"status": "reloaded"}


@app.get("/api/v1/admin/sample-csv/{filename}")
def sample_csv(filename: str, x_admin_token: Annotated[str | None, Header()] = None):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    allowed = {"airports.csv", "routes.csv", "schedules.csv", "fares.csv", "availability.csv"}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Not found")
    path = Path(__file__).resolve().parent.parent / "data" / filename
    return FileResponse(path, media_type="text/csv", filename=filename)


app.mount("/assets", StaticFiles(directory=APP_DIR), name="assets")


@app.get("/{path:path}")
def frontend(path: str):
    # SPA fallback. API routes are registered before this catch-all.
    return FileResponse(APP_DIR / "index.html")
