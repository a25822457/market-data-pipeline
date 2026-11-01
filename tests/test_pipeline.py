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

    def test_rs_is_date_aligned_wealth_ratio(self):
        spy = rows()
        stock = rows()
        stock[-1]["close"] *= 1.10
        stock[-1]["high"] = stock[-1]["close"]
        result = screen_us(stock, spy)
        self.assertIsNotNone(result["rs_vs_spy_63d"])
        self.assertGreater(result["rs_vs_spy_63d"], 1.0)
        self.assertTrue(result["rs_outperforms_spy"])

    def test_sepa_does_not_require_latest_day_volume(self):
        stock = rows()
        spy = rows()
        for row in stock:
            row["high"] = row["close"]
            row["low"] = row["close"]
        stock[-1]["close"] *= 1.10
        stock[-1]["high"] = stock[-1]["close"]
        stock[-1]["volume"] = 1
        result = screen_us(stock, spy)
        self.assertFalse(result["volume_above_average"])
        self.assertTrue(result["sepa_pass"])


if __name__ == "__main__": unittest.main()

