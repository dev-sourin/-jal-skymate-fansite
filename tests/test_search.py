from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.config import DB_PATH
from backend.db import initialize_database
from backend.search import search_flights


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database(force=True)

    def test_hnd_reverse_search_returns_results(self):
        today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
        payload = search_flights(origin="HND", flight_date=today)
        self.assertIn("results", payload)
        self.assertGreater(len(payload["results"]), 0)
        self.assertEqual(payload["dataset"]["data_mode"], "DEMO_SAMPLE")

    def test_budget_filter(self):
        tomorrow = datetime.now(ZoneInfo("Asia/Tokyo")).date() + timedelta(days=1)
        payload = search_flights(origin="HND", flight_date=tomorrow, budget=8000)
        self.assertTrue(all(item["minimumTotal"] <= 8000 for item in payload["results"]))

    def test_future_date_has_unknown_without_observation(self):
        future = datetime.now(ZoneInfo("Asia/Tokyo")).date() + timedelta(days=4)
        payload = search_flights(origin="HND", destination="KMQ", flight_date=future)
        self.assertTrue(payload["results"])
        self.assertTrue(all(item["availability"]["type"] == "UNKNOWN" for item in payload["results"]))


if __name__ == "__main__":
    unittest.main()
