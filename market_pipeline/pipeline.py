from __future__ import annotations

import argparse, json
from pathlib import Path
from .metrics import screen_crypto, screen_us
from .sources import fetch_binance_futures_snapshot, fetch_yahoo_daily
from .storage import save_raw, save_snapshot, save_sqlite
from .universe import fetch_top_binance_usdt_perpetuals, fetch_top_us_stocks
from .validation import validate_rows


def run(output_dir: Path, report_path: Path, min_bars: int = 252):
    output_dir.mkdir(parents=True, exist_ok=True)
    us, us_universe_mode = fetch_top_us_stocks(target=100, min_bars=min_bars)
    raw, report, us_screen, crypto_screen_rows = {}, {"generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "minimum_bars": min_bars, "us_universe": {"target": 100, "selection": us_universe_mode}, "crypto_universe": {"target": 252, "market": "Binance USDⓈ-M USDT perpetuals"}, "instruments": []}, [], []
    crypto_rows = fetch_top_binance_usdt_perpetuals(target=252, min_bars=min_bars)
    for market, symbols, fetcher in (("us_stock", us, fetch_yahoo_daily),):
        for symbol in symbols:
            item = {"asset": symbol, "market": market, "source": "Yahoo Finance chart API"}
            try:
                rows = fetcher(symbol, min_bars=min_bars); validation = validate_rows(rows, min_bars); item.update(validation)
                if validation["status"] != "pass": raise RuntimeError("; ".join(validation["errors"]))
                raw[symbol] = rows; save_raw(rows, output_dir / "raw" / f"{symbol}.csv")
            except Exception as exc:
                item.update({"status": "fail", "bars": 0, "errors": [f"{type(exc).__name__}: {exc}"]})
            report["instruments"].append(item)
    spy = fetch_yahoo_daily("SPY", min_bars=min_bars)
    for symbol in us:
        if symbol in raw and spy:
            us_screen.append({"asset": symbol, **screen_us(raw[symbol], spy)})
    for symbol, rows in crypto_rows.items():
        raw[symbol] = rows
        save_raw(rows, output_dir / "raw" / f"{symbol}.csv")
        snapshot = None
        snapshot_error = None
        try:
            snapshot = fetch_binance_futures_snapshot(symbol)
        except Exception as exc:
            snapshot_error = f"{type(exc).__name__}: {exc}"
        crypto_screen_rows.append({"asset": symbol, **screen_crypto(rows, snapshot)})
        item = {"asset": symbol, "market": "crypto_futures", "source": "Binance USDⓈ-M futures public klines API", **validate_rows(rows, min_bars), "futures_snapshot_status": "pass" if snapshot else "fail"}
        if snapshot_error:
            item["futures_snapshot_error"] = snapshot_error
        report["instruments"].append(item)
    report["futures_snapshot_failed"] = sum(i.get("futures_snapshot_status") == "fail" for i in report["instruments"])
    save_snapshot(us_screen, output_dir / "us_screen.csv"); save_snapshot(crypto_screen_rows, output_dir / "crypto_screen.csv")
    save_sqlite(output_dir / "market_data.sqlite3", raw, us_screen, crypto_screen_rows)
    report["passed"] = sum(i["status"] == "pass" for i in report["instruments"]); report["failed"] = len(report["instruments"]) - report["passed"]; report["overall_status"] = "pass" if report["failed"] == 0 else "fail"
    for item in report["instruments"]:
        print(json.dumps({"asset": item["asset"], "market": item["market"], "status": item["status"], "bars": item.get("bars", 0), "futures_snapshot_status": item.get("futures_snapshot_status"), "errors": item.get("errors", [])}, ensure_ascii=False))
    report_path.parent.mkdir(parents=True, exist_ok=True); report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, default=Path("data")); parser.add_argument("--report-path", type=Path, default=Path("validation_report.json")); parser.add_argument("--min-bars", type=int, default=252); args = parser.parse_args()
    report = run(args.output_dir, args.report_path, args.min_bars); print(json.dumps({k: report[k] for k in ("overall_status", "passed", "failed", "futures_snapshot_failed", "minimum_bars")}, ensure_ascii=False)); return 0 if report["overall_status"] == "pass" else 1
