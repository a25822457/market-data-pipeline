import csv
import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from market_pipeline.metrics import screen_crypto, screen_us
from market_pipeline.validation import validate_rows
from market_pipeline.report_gate import validate_report


def rows(n=260):
    start = date(2025, 1, 1)
    return [{"date": (start + timedelta(days=i)).isoformat(), "open": 100+i, "high": 101+i, "low": 99+i, "close": 100+i, "volume": 1000+i, "quote_volume": 100000+i} for i in range(n)]


class PipelineTests(unittest.TestCase):
    def test_validation_passes_complete_data(self):
        self.assertEqual(validate_rows(rows())["status"], "pass")

    def test_validation_rejects_short_data(self):
        self.assertEqual(validate_rows(rows(10))["status"], "fail")

    def test_report_gate_rejects_stale_or_incomplete_report(self):
        report = {
            "generated_at": "2026-10-31T01:00:00+00:00",
            "instruments": [{"status": "pass"}],
            "passed": 1,
            "failed": 0,
            "overall_status": "pass",
            "crypto_universe": {"status": "partial", "selected": 249, "target": 252},
        }
        result = validate_report(report, now=datetime(2026, 11, 3, 2, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "fail")

    def test_report_gate_rejects_fresh_but_partial_report(self):
        report = {
            "generated_at": "2026-11-03T01:00:00+00:00",
            "instruments": [{"status": "pass"}],
            "passed": 1,
            "failed": 0,
            "overall_status": "pass",
            "data_as_of": {"us": "2026-11-02", "crypto": "2026-11-02"},
            "crypto_universe": {"status": "partial", "selected": 249, "target": 252},
        }
        result = validate_report(report, now=datetime(2026, 11, 3, 2, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "fail")
        self.assertEqual(report["summary_gate"]["status"], "blocked")

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


    def test_report_gate_accepts_fresh_valid_partial_universe(self):
        us_fields = {
            "asset": "TEST", "date": "2026-11-02", "close": "100",
            "sma50": "99", "sma150": "98", "sma200": "97",
            "sma200_slope_20d": "1", "high_52w": "101", "low_52w": "50",
            "pivot_20d": "100", "volume_vs_avg50": "1.2", "rs_vs_spy_63d": "1.1",
            "sepa_pass": "True", "recommended_entry": "100.1",
            "stop_loss": "92.092", "take_profit_2r": "116.116",
            "entry_status": "triggered",
        }
        crypto_fields = {
            "asset": "TEST-USDT-SWAP", "date": "2026-11-02", "close": "100",
            "return_1d": "0.01", "sma20": "99", "sma50": "98",
            "annualized_volatility_20d": "0.5", "avg_quote_volume_20d": "1000",
            "trend": "up", "mark_price": "100", "index_price": "100",
            "funding_rate": "0.0001", "open_interest": "1000",
        }
        with tempfile.TemporaryDirectory() as tmp:
            us_path = Path(tmp) / "us.csv"
            crypto_path = Path(tmp) / "crypto.csv"
            with us_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(us_fields))
                writer.writeheader()
                for i in range(100):
                    row = dict(us_fields)
                    row["asset"] = f"US{i}"
                    writer.writerow(row)
            with crypto_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(crypto_fields))
                writer.writeheader()
                for i in range(249):
                    row = dict(crypto_fields)
                    row["asset"] = f"C{i}-USDT-SWAP"
                    writer.writerow(row)
            report = {
                "generated_at": "2026-11-03T01:00:00+00:00",
                "instruments": [{"status": "pass"}],
                "passed": 1,
                "failed": 0,
                "overall_status": "pass",
                "data_as_of": {"us": "2026-11-02", "crypto": "2026-11-02"},
                "us_benchmark": {"status": "pass", "last_date": "2026-11-02"},
                "crypto_universe": {"status": "partial", "selected": 249, "target": 252},
                "futures_snapshot_failed": 0,
            }
            result = validate_report(
                report,
                us_path=us_path,
                crypto_path=crypto_path,
                now=datetime(2026, 11, 3, 2, tzinfo=timezone.utc),
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual(report["summary_gate"]["status"], "ready_with_warnings")


if __name__ == "__main__": unittest.main()

