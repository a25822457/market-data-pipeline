from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .metrics import screen_crypto, screen_us
from .sources import fetch_okx_futures_snapshot, fetch_okx_swap_tickers, fetch_yahoo_daily
from .storage import save_raw, save_snapshot, save_sqlite
from .universe import fetch_top_okx_usdt_perpetuals, fetch_top_us_stocks
from .validation import validate_rows


US_TARGET = 100
CRYPTO_TARGET = 252


def run(output_dir: Path, report_path: Path, min_bars: int = 252):
    output_dir.mkdir(parents=True, exist_ok=True)
    us, us_universe_mode = fetch_top_us_stocks(target=US_TARGET, min_bars=min_bars)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "minimum_bars": min_bars,
        "us_universe": {"target": US_TARGET, "selection": us_universe_mode},
        "crypto_universe": {
            "target": CRYPTO_TARGET,
            "market": "OKX USDT linear perpetual swaps",
            "candle_timezone": "UTC",
            "status": "pending",
            "selected": 0,
        },
        "us_benchmark": {},
        "warnings": [],
        "instruments": [],
    }
    raw: dict[str, list[dict]] = {}
    us_screen: list[dict] = []
    crypto_screen_rows: list[dict] = []

    try:
        crypto_rows = fetch_top_okx_usdt_perpetuals(
            target=CRYPTO_TARGET,
            min_bars=min_bars,
        )
        selected_count = len(crypto_rows)
        report["crypto_universe"]["selected"] = selected_count
        if selected_count < CRYPTO_TARGET:
            report["crypto_universe"]["status"] = "partial"
            report["warnings"].append(
                f"OKX supplied {selected_count}/{CRYPTO_TARGET} eligible USDT perpetuals "
                f"with at least {min_bars} complete daily bars; "
                f"missing {CRYPTO_TARGET - selected_count}."
            )
        else:
            report["crypto_universe"]["status"] = "pass"
    except Exception as exc:
        crypto_rows = {}
        report["crypto_universe"].update(
            {"status": "fail", "error": f"{type(exc).__name__}: {exc}"}
        )

    for symbol in us:
        item = {
            "asset": symbol,
            "market": "us_stock",
            "source": "Yahoo Finance chart API",
        }
        try:
            rows = fetch_yahoo_daily(symbol, min_bars=min_bars)
            validation = validate_rows(rows, min_bars)
            item.update(validation)
            if validation["status"] != "pass":
                raise RuntimeError("; ".join(validation["errors"]))
            raw[symbol] = rows
            save_raw(rows, output_dir / "raw" / f"{symbol}.csv")
        except Exception as exc:
            item.update(
                {
                    "status": "fail",
                    "bars": 0,
                    "errors": [f"{type(exc).__name__}: {exc}"],
                }
            )
        report["instruments"].append(item)

    spy: list[dict] = []
    try:
        spy = fetch_yahoo_daily("SPY", min_bars=min_bars)
        benchmark_validation = validate_rows(spy, min_bars)
        report["us_benchmark"] = {
            "asset": "SPY",
            "source": "Yahoo Finance chart API",
            **benchmark_validation,
        }
        if benchmark_validation["status"] == "pass":
            raw["SPY"] = spy
            save_raw(spy, output_dir / "raw" / "SPY.csv")
    except Exception as exc:
        report["us_benchmark"] = {
            "asset": "SPY",
            "source": "Yahoo Finance chart API",
            "status": "fail",
            "bars": 0,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }

    for symbol in us:
        if symbol in raw and spy and report["us_benchmark"].get("status") == "pass":
            us_screen.append({"asset": symbol, **screen_us(raw[symbol], spy)})

    okx_tickers: dict[str, dict] = {}
    ticker_error = None
    if crypto_rows:
        try:
            okx_tickers = fetch_okx_swap_tickers()
        except Exception as exc:
            ticker_error = f"{type(exc).__name__}: {exc}"

    for symbol, rows in crypto_rows.items():
        raw[symbol] = rows
        save_raw(rows, output_dir / "raw" / f"{symbol}.csv")
        snapshot = None
        snapshot_error = ticker_error
        if not snapshot_error:
            try:
                snapshot = fetch_okx_futures_snapshot(symbol, okx_tickers.get(symbol))
            except Exception as exc:
                snapshot_error = f"{type(exc).__name__}: {exc}"
        crypto_screen_rows.append(
            {"asset": symbol, **screen_crypto(rows, snapshot)}
        )
        item = {
            "asset": symbol,
            "market": "crypto_futures",
            "source": "OKX public SWAP market data",
            **validate_rows(rows, min_bars),
            "futures_snapshot_status": "pass" if snapshot else "fail",
        }
        if snapshot_error:
            item["futures_snapshot_error"] = snapshot_error
        if not snapshot:
            item["status"] = "fail"
            item.setdefault("errors", []).append(
                snapshot_error or "missing futures snapshot"
            )
        report["instruments"].append(item)

    report["futures_snapshot_failed"] = sum(
        item.get("futures_snapshot_status") == "fail"
        for item in report["instruments"]
    )
    save_snapshot(us_screen, output_dir / "us_screen.csv")
    save_snapshot(crypto_screen_rows, output_dir / "crypto_screen.csv")
    save_sqlite(
        output_dir / "market_data.sqlite3",
        raw,
        us_screen,
        crypto_screen_rows,
    )

    report["passed"] = sum(
        item.get("status") == "pass" for item in report["instruments"]
    )
    report["failed"] = len(report["instruments"]) - report["passed"]
    quality_ok = (
        report["failed"] == 0
        and report["us_benchmark"].get("status") == "pass"
        and report["crypto_universe"].get("status") == "pass"
        and len(crypto_rows) == CRYPTO_TARGET
        and report["futures_snapshot_failed"] == 0
    )
    report["overall_status"] = "pass" if quality_ok else "fail"
    if not quality_ok:
        report["failure_reasons"] = []
        if report["failed"]:
            report["failure_reasons"].append(
                f"{report['failed']} instrument validations failed"
            )
        if report["us_benchmark"].get("status") != "pass":
            report["failure_reasons"].append("SPY benchmark validation failed")
        if len(crypto_rows) != CRYPTO_TARGET:
            report["failure_reasons"].append(
                f"crypto coverage {len(crypto_rows)}/{CRYPTO_TARGET}"
            )
        if report["futures_snapshot_failed"]:
            report["failure_reasons"].append(
                f"futures snapshots failed={report['futures_snapshot_failed']}"
            )

    for item in report["instruments"]:
        print(
            json.dumps(
                {
                    "asset": item["asset"],
                    "market": item["market"],
                    "status": item["status"],
                    "bars": item.get("bars", 0),
                    "futures_snapshot_status": item.get("futures_snapshot_status"),
                    "errors": item.get("errors", []),
                },
                ensure_ascii=False,
            )
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("validation_report.json"),
    )
    parser.add_argument("--min-bars", type=int, default=252)
    args = parser.parse_args()
    report = run(args.output_dir, args.report_path, args.min_bars)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "overall_status",
                    "passed",
                    "failed",
                    "futures_snapshot_failed",
                    "minimum_bars",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
