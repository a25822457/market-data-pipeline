import unittest
from datetime import date, timedelta
from market_pipeline.metrics import screen_crypto, screen_us
from market_pipeline.validation import validate_rows


def rows(n=260):
    start = date(2025, 1, 1)
    return [{"date": (start + timedelta(days=i)).isoformat(), "open": 100+i, "high": 101+i, "low": 99+i, "close": 100+i, "volume": 1000+i, "quote_volume": 100000+i} for i in range(n)]


class PipelineTests(unittest.TestCase):
    def test_validation_passes_complete_data(self):
        self.assertEqual(validate_rows(rows())["status"], "pass")

    def test_validation_rejects_short_data(self):
        self.assertEqual(validate_rows(rows(10))["status"], "fail")

    def test_metrics_are_computed(self):
        result = screen_us(rows(), rows())
        self.assertIsNotNone(result["sma200"]); self.assertIsNotNone(result["sma200_slope_20d"])
        crypto = screen_crypto(rows())
        self.assertIn(crypto["trend"], {"up", "down", "mixed"})


if __name__ == "__main__": unittest.main()

