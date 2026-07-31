from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.availability import choose_observation, predict_availability


class Row(dict):
    pass


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(ZoneInfo("Asia/Tokyo"))

    def row(self, source_type: str, status: str = "AVAILABLE", expires_delta: int = 60) -> Row:
        return Row({
            "source_type": source_type,
            "status": status,
            "source_label": "test",
            "observed_at": self.now.isoformat(),
            "expires_at": (self.now + timedelta(minutes=expires_delta)).isoformat(),
        })

    def test_exact_has_priority_over_general(self):
        view = choose_observation([
            self.row("GENERAL_CURRENT"),
            self.row("EXACT_SKYMATE", "SOLD_OUT"),
        ], self.now)
        self.assertIsNotNone(view)
        self.assertEqual(view.type, "EXACT_SKYMATE")
        self.assertEqual(view.status, "SOLD_OUT")

    def test_expired_observation_is_removed(self):
        view = choose_observation([self.row("EXACT_SKYMATE", expires_delta=-1)], self.now)
        self.assertIsNone(view)

    def test_prediction_is_explainable(self):
        view = predict_availability(
            flight_date=date.today(),
            departure_time="13:00",
            remaining_flights=4,
            historical_tendency=10,
            reference_status="AVAILABLE_MANY",
        )
        self.assertEqual(view.type, "PREDICTED")
        self.assertEqual(view.estimate_level, "HIGH")
        self.assertGreaterEqual(len(view.factors), 4)


if __name__ == "__main__":
    unittest.main()
