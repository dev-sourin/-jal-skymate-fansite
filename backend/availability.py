from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .config import TIMEZONE

PRIORITY = {
    "EXACT_SKYMATE": 5,
    "GENERAL_CURRENT": 4,
    "GENERAL_D1": 3,
    "PREDICTED": 2,
    "UNKNOWN": 1,
}

STATUS_LABELS = {
    "AVAILABLE_MANY": "余裕あり",
    "AVAILABLE": "空席あり",
    "AVAILABLE_FEW": "残りわずか",
    "WAITLIST": "要確認",
    "SOLD_OUT": "満席",
    "UNKNOWN": "未確認",
}

TYPE_LABELS = {
    "EXACT_SKYMATE": "当日スカイメイト空席",
    "GENERAL_CURRENT": "当日一般席参考",
    "GENERAL_D1": "前日一般席参考",
    "PREDICTED": "利用見込み",
    "UNKNOWN": "空席未確認",
}


@dataclass(frozen=True)
class AvailabilityView:
    type: str
    type_label: str
    status: str
    status_label: str
    estimate_level: str | None
    score: int | None
    confidence: str
    observed_at: str | None
    expires_at: str | None
    source_label: str
    message: str
    factors: list[dict[str, Any]]
    stale: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "typeLabel": self.type_label,
            "status": self.status,
            "statusLabel": self.status_label,
            "estimateLevel": self.estimate_level,
            "score": self.score,
            "confidence": self.confidence,
            "observedAt": self.observed_at,
            "expiresAt": self.expires_at,
            "sourceLabel": self.source_label,
            "message": self.message,
            "factors": self.factors,
            "stale": self.stale,
        }


def _message(source_type: str) -> str:
    return {
        "EXACT_SKYMATE": "対象運賃の販売可否を直接確認したデータです。購入時点で変動する可能性があります。",
        "GENERAL_CURRENT": "当日の一般席参考です。スカイメイトの販売を保証しません。",
        "GENERAL_D1": "前日の一般席参考です。翌日のスカイメイト販売を保証しません。",
        "PREDICTED": "一般席参考・便数・曜日等から算出した独自予測で、実在庫ではありません。",
        "UNKNOWN": "利用可能な空席データがありません。JAL公式サイトでご確認ください。",
    }[source_type]


def observation_to_view(row: Any, now: datetime) -> AvailabilityView | None:
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at <= now:
        return None
    source_type = row["source_type"]
    return AvailabilityView(
        type=source_type,
        type_label=TYPE_LABELS[source_type],
        status=row["status"],
        status_label=STATUS_LABELS.get(row["status"], row["status"]),
        estimate_level=None,
        score=None,
        confidence="HIGH" if source_type == "EXACT_SKYMATE" else "MEDIUM",
        observed_at=row["observed_at"],
        expires_at=row["expires_at"],
        source_label=row["source_label"],
        message=_message(source_type),
        factors=[],
    )


def choose_observation(rows: list[Any], now: datetime) -> AvailabilityView | None:
    candidates = [v for row in rows if (v := observation_to_view(row, now)) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda v: (PRIORITY[v.type], v.observed_at or ""))


def predict_availability(
    *,
    flight_date: date,
    departure_time: str,
    remaining_flights: int,
    historical_tendency: int,
    reference_status: str | None = None,
) -> AvailabilityView:
    score = 0
    factors: list[dict[str, Any]] = []

    reference_points = {
        "AVAILABLE_MANY": 50,
        "AVAILABLE": 42,
        "AVAILABLE_FEW": 15,
        "WAITLIST": 8,
        "SOLD_OUT": 0,
    }
    if reference_status:
        points = reference_points.get(reference_status, 0)
        score += points
        factors.append({"name": "一般席空席参考", "points": points, "detail": STATUS_LABELS.get(reference_status, reference_status)})
    else:
        factors.append({"name": "一般席空席参考", "points": None, "detail": "未観測"})

    if remaining_flights >= 4:
        points = 20
    elif remaining_flights >= 2:
        points = 10
    else:
        points = 0
    score += points
    factors.append({"name": "当該便以降の便数", "points": points, "detail": f"{remaining_flights}便"})

    dep_hour = int(departure_time.split(":", 1)[0])
    weekend = flight_date.weekday() >= 5
    if weekend and (dep_hour < 10 or dep_hour >= 17):
        points = 4
        detail = "休日の朝夕"
    elif weekend:
        points = 8
        detail = "休日の日中"
    elif 10 <= dep_hour < 17:
        points = 15
        detail = "平日の日中"
    else:
        points = 10
        detail = "平日の朝夕"
    score += points
    factors.append({"name": "曜日・時間帯", "points": points, "detail": detail})

    tendency_points = max(0, min(15, historical_tendency))
    score += tendency_points
    factors.append({"name": "路線別デモ傾向", "points": tendency_points, "detail": "サンプル係数"})

    if score >= 70:
        level = "HIGH"
        status_label = "高"
    elif score >= 40:
        level = "MEDIUM"
        status_label = "中"
    else:
        level = "LOW"
        status_label = "低"

    confidence = "MEDIUM" if reference_status else "LOW"
    now = datetime.now(ZoneInfo(TIMEZONE))
    return AvailabilityView(
        type="PREDICTED",
        type_label=TYPE_LABELS["PREDICTED"],
        status="UNKNOWN",
        status_label=status_label,
        estimate_level=level,
        score=score,
        confidence=confidence,
        observed_at=now.isoformat(),
        expires_at=datetime.combine(flight_date, time(23, 59), tzinfo=ZoneInfo(TIMEZONE)).isoformat(),
        source_label="説明可能なルールベース予測（デモ）",
        message=_message("PREDICTED"),
        factors=factors,
    )


def unknown_availability() -> AvailabilityView:
    return AvailabilityView(
        type="UNKNOWN",
        type_label=TYPE_LABELS["UNKNOWN"],
        status="UNKNOWN",
        status_label=STATUS_LABELS["UNKNOWN"],
        estimate_level=None,
        score=None,
        confidence="NONE",
        observed_at=None,
        expires_at=None,
        source_label="取得元なし",
        message=_message("UNKNOWN"),
        factors=[],
    )
