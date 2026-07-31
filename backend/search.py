from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .availability import choose_observation, predict_availability, unknown_availability
from .config import TIMEZONE
from .db import connection

PERIODS = {
    "all": (0, 24),
    "morning": (5, 12),
    "afternoon": (12, 17),
    "evening": (17, 20),
    "night": (20, 24),
}


def _operates(operating_days: str, flight_date: date) -> bool:
    allowed = {int(v) for v in operating_days.split(",") if v.strip()}
    return flight_date.weekday() in allowed


def _duration_minutes(dep: str, arr: str) -> int:
    dep_h, dep_m = map(int, dep.split(":"))
    arr_h, arr_m = map(int, arr.split(":"))
    minutes = (arr_h * 60 + arr_m) - (dep_h * 60 + dep_m)
    return minutes if minutes >= 0 else minutes + 24 * 60


def _time_in_period(dep: str, period: str) -> bool:
    start, end = PERIODS.get(period, PERIODS["all"])
    hour = int(dep.split(":", 1)[0])
    return start <= hour < end


def list_airports(q: str | None = None) -> list[dict[str, Any]]:
    with connection() as conn:
        if q:
            pattern = f"%{q.strip()}%"
            rows = conn.execute(
                """SELECT * FROM airports
                WHERE iata_code LIKE ? OR name_ja LIKE ? OR city LIKE ?
                ORDER BY city, iata_code""",
                (pattern.upper(), pattern, pattern),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM airports ORDER BY city, iata_code").fetchall()
    return [dict(row) for row in rows]


def dataset_meta() -> dict[str, str]:
    with connection() as conn:
        rows = conn.execute("SELECT key,value FROM dataset_meta").fetchall()
    return {row["key"]: row["value"] for row in rows}


def _get_fares(conn: Any, route_id: str, flight_date: date, cabin_class: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT * FROM fares
        WHERE route_id=? AND cabin_class=? AND valid_from<=? AND valid_to>=?
        ORDER BY amount_yen""",
        (route_id, cabin_class, flight_date.isoformat(), flight_date.isoformat()),
    ).fetchall()
    return [
        {
            "product": row["fare_product"],
            "productLabel": "スカイメイト" if row["fare_product"] == "SKYMATE" else "JALカードスカイメイト",
            "amount": row["amount_yen"],
            "sourceLabel": row["source_label"],
        }
        for row in rows
    ]


def _get_availability(conn: Any, flight_no: str, flight_date: date, cabin_class: str, *, departure_time: str, remaining_flights: int, historical_tendency: int) -> dict[str, Any]:
    now = datetime.now(ZoneInfo(TIMEZONE))
    rows = conn.execute(
        """SELECT * FROM availability_observations
        WHERE flight_no=? AND flight_date=? AND cabin_class=?
        ORDER BY observed_at DESC""",
        (flight_no, flight_date.isoformat(), cabin_class),
    ).fetchall()
    selected = choose_observation(list(rows), now)
    if selected:
        return selected.as_dict()

    today = now.date()
    if flight_date <= today + timedelta(days=1):
        return predict_availability(
            flight_date=flight_date,
            departure_time=departure_time,
            remaining_flights=remaining_flights,
            historical_tendency=historical_tendency,
        ).as_dict()
    return unknown_availability().as_dict()


def search_flights(
    *,
    origin: str,
    flight_date: date,
    destination: str | None = None,
    budget: int | None = None,
    departure_period: str = "all",
    cabin_class: str = "ECONOMY",
    availability_filter: str = "all",
    sort: str = "departure",
) -> dict[str, Any]:
    origin = origin.upper()
    destination = destination.upper() if destination else None
    with connection() as conn:
        params: list[Any] = [origin, flight_date.isoformat(), flight_date.isoformat()]
        destination_sql = ""
        if destination:
            destination_sql = " AND r.destination_iata=?"
            params.append(destination)

        schedule_rows = conn.execute(
            f"""SELECT s.*, r.origin_iata, r.destination_iata, r.carrier_code,
                    r.typical_minutes, r.historical_tendency,
                    ao.name_ja AS origin_name, ao.city AS origin_city, ao.pfc_yen AS origin_pfc,
                    ad.name_ja AS destination_name, ad.city AS destination_city,
                    ad.region AS destination_region, ad.pfc_yen AS destination_pfc
                FROM schedules s
                JOIN routes r ON r.id=s.route_id AND r.active=1
                JOIN airports ao ON ao.iata_code=r.origin_iata
                JOIN airports ad ON ad.iata_code=r.destination_iata
                WHERE r.origin_iata=?
                  AND s.valid_from<=? AND s.valid_to>=?
                  {destination_sql}
                ORDER BY s.departure_time""",
            params,
        ).fetchall()

        now = datetime.now(ZoneInfo(TIMEZONE))
        active_rows = [
            row for row in schedule_rows
            if _operates(row["operating_days"], flight_date)
            and _time_in_period(row["departure_time"], departure_period)
            and not (
                flight_date == now.date()
                and datetime.combine(
                    flight_date,
                    datetime.strptime(row["departure_time"], "%H:%M").time(),
                    tzinfo=ZoneInfo(TIMEZONE),
                ) <= now
            )
        ]
        results: list[dict[str, Any]] = []
        for row in active_rows:
            remaining = sum(
                1 for candidate in active_rows
                if candidate["route_id"] == row["route_id"]
                and candidate["departure_time"] >= row["departure_time"]
            )
            fares = _get_fares(conn, row["route_id"], flight_date, cabin_class)
            facility_fee = row["origin_pfc"] + row["destination_pfc"]
            for fare in fares:
                fare["facilityFee"] = facility_fee
                fare["totalEstimate"] = fare["amount"] + facility_fee
            min_total = min((fare["totalEstimate"] for fare in fares), default=None)
            if budget is not None and (min_total is None or min_total > budget):
                continue

            availability = _get_availability(
                conn,
                row["flight_no"],
                flight_date,
                cabin_class,
                departure_time=row["departure_time"],
                remaining_flights=remaining,
                historical_tendency=row["historical_tendency"],
            )
            if availability_filter != "all":
                allowed = {
                    "exact": {"EXACT_SKYMATE"},
                    "reference": {"GENERAL_CURRENT", "GENERAL_D1"},
                    "high": {"PREDICTED"},
                    "known": {"EXACT_SKYMATE", "GENERAL_CURRENT", "GENERAL_D1", "PREDICTED"},
                }.get(availability_filter, set())
                if availability["type"] not in allowed:
                    continue
                if availability_filter == "high" and availability.get("estimateLevel") != "HIGH":
                    continue

            dep_dt = datetime.combine(flight_date, datetime.strptime(row["departure_time"], "%H:%M").time(), tzinfo=ZoneInfo(TIMEZONE))
            results.append({
                "id": f'{row["flight_no"]}-{flight_date.isoformat()}',
                "routeId": row["route_id"],
                "origin": {
                    "iata": row["origin_iata"], "name": row["origin_name"], "city": row["origin_city"]
                },
                "destination": {
                    "iata": row["destination_iata"], "name": row["destination_name"],
                    "city": row["destination_city"], "region": row["destination_region"]
                },
                "flight": {
                    "flightNo": row["flight_no"],
                    "departure": row["departure_time"],
                    "arrival": row["arrival_time"],
                    "durationMinutes": _duration_minutes(row["departure_time"], row["arrival_time"]),
                    "hasDeparted": dep_dt <= now,
                    "remainingFlightsFromThis": remaining,
                },
                "fares": fares,
                "minimumTotal": min_total,
                "availability": availability,
            })

    sort_key = {
        "price": lambda item: item["minimumTotal"] if item["minimumTotal"] is not None else 10**9,
        "duration": lambda item: item["flight"]["durationMinutes"],
        "destination": lambda item: item["destination"]["city"],
        "availability": lambda item: -((item["availability"].get("score") or 0)),
        "departure": lambda item: item["flight"]["departure"],
    }.get(sort, lambda item: item["flight"]["departure"])
    results.sort(key=sort_key)

    meta = dataset_meta()
    return {
        "query": {
            "origin": origin,
            "destination": destination,
            "date": flight_date.isoformat(),
            "departurePeriod": departure_period,
            "budget": budget,
            "cabinClass": cabin_class,
            "availabilityFilter": availability_filter,
            "sort": sort,
        },
        "dataset": meta,
        "count": len(results),
        "results": results,
        "notice": "デモ用サンプルデータです。実際の時刻・運賃・空席ではありません。",
    }


def get_flight_detail(flight_no: str, flight_date: date, cabin_class: str = "ECONOMY") -> dict[str, Any] | None:
    """Return one normalized flight result using the same rules as the search endpoint."""
    with connection() as conn:
        row = conn.execute(
            """SELECT r.origin_iata, r.destination_iata
            FROM schedules s JOIN routes r ON r.id=s.route_id
            WHERE s.flight_no=? AND s.valid_from<=? AND s.valid_to>=?
            LIMIT 1""",
            (flight_no, flight_date.isoformat(), flight_date.isoformat()),
        ).fetchone()
    if row is None:
        return None
    payload = search_flights(
        origin=row["origin_iata"],
        destination=row["destination_iata"],
        flight_date=flight_date,
        cabin_class=cabin_class,
    )
    return next((item for item in payload["results"] if item["flight"]["flightNo"] == flight_no), None)
