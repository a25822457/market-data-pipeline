import unittest

from market_pipeline.backtest import build_backtest


def report_for(day: str) -> dict:
    return {
        "generated_at_taipei": f"{day}T09:00:00+08:00",
        "data_as_of": {"us": day, "crypto": day},
    }


class BacktestTests(unittest.TestCase):
    def test_first_run_saves_baseline_then_next_run_evaluates_it(self):
        first_us = [
            {
                "asset": "TEST",
                "date": "2026-11-01",
                "close": "99",
                "high": "100",
                "low": "98",
                "sepa_pass": "True",
                "recommended_entry": "100",
                "stop_loss": "92",
                "take_profit_2r": "116",
                "entry_status": "waiting_breakout",
            }
        ]
        first_crypto = [
            {"asset": "TEST-USDT-SWAP", "date": "2026-11-01", "close": "10", "trend": "up"}
        ]
        first, _, history = build_backtest(
            report_for("2026-11-01"), first_us, first_crypto, {"snapshots": []}
        )
        self.assertEqual(first["status"], "no_previous_observation")
        self.assertEqual(len(history["snapshots"]), 1)

        next_us = [
            {
                "asset": "TEST",
                "date": "2026-11-02",
                "close": "105",
                "high": "117",
                "low": "101",
                "sepa_pass": "False",
            }
        ]
        next_crypto = [
            {
                "asset": "TEST-USDT-SWAP",
                "date": "2026-11-02",
                "close": "10.2",
                "return_1d": "0.02",
                "trend": "up",
            }
        ]
        result, _, _ = build_backtest(
            report_for("2026-11-02"), next_us, next_crypto, history
        )
        self.assertEqual(result["us"]["summary"]["counts"]["target"], 1)
        self.assertEqual(result["crypto"]["summary"]["hits"], 1)


if __name__ == "__main__":
    unittest.main()
