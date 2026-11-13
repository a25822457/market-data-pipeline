from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truthy(value) -> bool:
    return value in {True, "True", "true", 1, "1"}


def _market_date(report: dict, market: str) -> str:
    value = report.get("data_as_of", {}).get(market)
    if value:
        return str(value)[:10]
    generated = report.get("generated_at_taipei") or report.get("generated_at") or ""
    return str(generated)[:10] or "unknown"


def _current_date(report: dict) -> str:
    dates = [
        _market_date(report, "us"),
        _market_date(report, "crypto"),
    ]
    return max(date for date in dates if date != "unknown") if any(
        date != "unknown" for date in dates
    ) else "unknown"


def _make_snapshot(report: dict, us_rows: list[dict], crypto_rows: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "date": _current_date(report),
        "generated_at_taipei": report.get("generated_at_taipei"),
        "data_as_of": report.get("data_as_of", {}),
        "us": [
            {
                "asset": row.get("asset"),
                "date": row.get("date"),
                "close": _float(row.get("close")),
                "rs_vs_spy_63d": _float(row.get("rs_vs_spy_63d")),
                "recommended_entry": _float(row.get("recommended_entry")),
                "stop_loss": _float(row.get("stop_loss")),
                "take_profit_2r": _float(row.get("take_profit_2r")),
                "entry_status": row.get("entry_status"),
            }
            for row in us_rows
            if _truthy(row.get("sepa_pass"))
        ],
        "crypto": [
            {
                "asset": row.get("asset"),
                "date": row.get("date"),
                "close": _float(row.get("close")),
                "trend": row.get("trend"),
            }
            for row in crypto_rows
        ],
    }


def _history_with_snapshot(history: dict, snapshot: dict) -> dict:
    current_date = snapshot["date"]
    snapshots = [
        item for item in history.get("snapshots", [])
        if item.get("date") != current_date
    ]
    snapshots.append(snapshot)
    snapshots.sort(key=lambda item: item.get("date", ""))
    return {
        "schema_version": 1,
        "retention_snapshots": 60,
        "snapshots": snapshots[-60:],
    }


def _previous_snapshot(history: dict, current_date: str):
    candidates = [
        item for item in history.get("snapshots", [])
        if item.get("date") and item.get("date") < current_date
    ]
    return max(candidates, key=lambda item: item["date"], default=None)


def _classify_us(previous: dict, current: dict | None) -> dict:
    if current is None:
        return {"result": "pending", "reason": "current instrument is missing"}

    entry = _float(previous.get("recommended_entry"))
    stop = _float(previous.get("stop_loss"))
    target = _float(previous.get("take_profit_2r"))
    high = _float(current.get("high"))
    low = _float(current.get("low"))
    if None in {entry, stop, target, high, low}:
        return {
            "result": "pending",
            "reason": "current OHLC or previous trade levels are missing",
        }

    entry_status = previous.get("entry_status")
    if entry_status == "waiting_breakout":
        # No position exists before the breakout. A move below the planned
        # stop invalidates the setup; it is not a stopped-out trade.
        if high < entry and low <= stop:
            return {"result": "invalidated_before_entry"}
        if high < entry:
            return {"result": "not_triggered"}
        if low <= stop and high >= target:
            return {"result": "both_levels_hit_same_day_unknown"}
        if low <= stop:
            return {"result": "triggered_and_stop"}
        if high >= target:
            return {"result": "target"}
        return {"result": "triggered_open"}

    if entry_status == "triggered":
        if low <= stop and high >= target:
            return {"result": "both_levels_hit_same_day_unknown"}
        if low <= stop:
            return {"result": "stop"}
        if high >= target:
            return {"result": "target"}
        return {"result": "open"}

    return {"result": "pending", "reason": "previous entry status is missing"}


def _backtest_us(
    previous: dict,
    current_rows: list[dict],
    current_date: str,
    current_data_date: str,
) -> dict:
    previous_data_date = (
        previous.get("data_as_of", {}).get("us") or previous.get("date") or "unknown"
    )
    if current_data_date <= previous_data_date:
        results = [
            {
                "asset": item.get("asset"),
                "previous_date": item.get("date") or previous.get("date"),
                "current_date": current_data_date,
                "previous_entry_status": item.get("entry_status"),
                "current_close": None,
                "result": "pending",
                "reason": (
                    f"US data date did not advance: {current_data_date} "
                    f"<= {previous_data_date}"
                ),
            }
            for item in previous.get("us", [])
        ]
        return {
            "results": results,
            "summary": {
                "watchlist": len(results),
                "evaluated": 0,
                "pending": len(results),
                "counts": {"pending": len(results)} if results else {},
            },
        }

    current_by_asset = {row.get("asset"): row for row in current_rows}
    results = []
    for item in previous.get("us", []):
        asset = item.get("asset")
        current = current_by_asset.get(asset)
        result = _classify_us(item, current)
        result.update(
            {
                "asset": asset,
                "previous_date": item.get("date") or previous.get("date"),
                "current_date": current.get("date") if current else current_date,
                "previous_entry_status": item.get("entry_status"),
                "current_close": _float(current.get("close")) if current else None,
            }
        )
        results.append(result)

    counts = Counter(item["result"] for item in results)
    pending = counts.get("pending", 0)
    return {
        "results": results,
        "summary": {
            "watchlist": len(results),
            "evaluated": len(results) - pending,
            "pending": pending,
            "counts": dict(counts),
        },
    }


def _backtest_crypto(
    previous: dict,
    current_rows: list[dict],
    current_date: str,
    current_data_date: str,
) -> dict:
    previous_data_date = (
        previous.get("data_as_of", {}).get("crypto")
        or previous.get("date")
        or "unknown"
    )
    if current_data_date <= previous_data_date:
        results = [
            {
                "asset": item.get("asset"),
                "previous_date": item.get("date") or previous.get("date"),
                "current_date": current_data_date,
                "previous_trend": item.get("trend"),
                "current_return_1d": None,
                "result": "pending",
                "reason": (
                    f"crypto data date did not advance: {current_data_date} "
                    f"<= {previous_data_date}"
                ),
            }
            for item in previous.get("crypto", [])
        ]
        return {
            "summary": {
                "watchlist": len(results),
                "evaluated": 0,
                "hits": 0,
                "misses": 0,
                "pending": len(results),
                "excluded_mixed": 0,
                "hit_rate": None,
            },
            "results": results,
        }

    current_by_asset = {row.get("asset"): row for row in current_rows}
    results = []
    for item in previous.get("crypto", []):
        asset = item.get("asset")
        current = current_by_asset.get(asset)
        current_return = _float(current.get("return_1d")) if current else None
        trend = item.get("trend")
        if current is None or current_return is None:
            result = "pending"
        elif trend == "up":
            result = "hit" if current_return > 0 else "miss"
        elif trend == "down":
            result = "hit" if current_return < 0 else "miss"
        else:
            result = "excluded_mixed"

        results.append(
            {
                "asset": asset,
                "previous_date": item.get("date") or previous.get("date"),
                "current_date": current.get("date") if current else current_date,
                "previous_trend": trend,
                "current_return_1d": current_return,
                "result": result,
            }
        )

    counts = Counter(item["result"] for item in results)
    hits = counts.get("hit", 0)
    misses = counts.get("miss", 0)
    pending = counts.get("pending", 0)
    evaluated = hits + misses
    return {
        "summary": {
            "watchlist": len(results),
            "evaluated": evaluated,
            "hits": hits,
            "misses": misses,
            "pending": pending,
            "excluded_mixed": counts.get("excluded_mixed", 0),
            "hit_rate": hits / evaluated if evaluated else None,
        },
        "results": results,
    }


def build_backtest(
    report: dict,
    us_rows: list[dict],
    crypto_rows: list[dict],
    history: dict,
) -> tuple[dict, dict, dict]:
    current_us_date = _market_date(report, "us")
    current_crypto_date = _market_date(report, "crypto")
    current_date = max(current_us_date, current_crypto_date)
    snapshot = _make_snapshot(report, us_rows, crypto_rows)
    updated_history = _history_with_snapshot(history, snapshot)
    previous = _previous_snapshot(history, current_date)

    if previous is None:
        result = {
            "schema_version": 1,
            "status": "no_previous_observation",
            "current_date": current_date,
            "previous_date": None,
            "message": "首次建立觀察名單；下一次執行會用這批名單回測。",
            "us": {"summary": {}, "results": []},
            "crypto": {"summary": {}, "results": []},
        }
        return result, snapshot, updated_history

    us = _backtest_us(previous, us_rows, current_date, current_us_date)
    crypto = _backtest_crypto(
        previous, crypto_rows, current_date, current_crypto_date
    )
    pending = us["summary"]["pending"] + crypto["summary"]["pending"]
    result = {
        "schema_version": 1,
        "status": "complete_with_pending" if pending else "complete",
        "current_date": current_date,
        "previous_date": previous.get("date"),
        "us": us,
        "crypto": crypto,
        "methodology": {
            "us": "以昨日參考進場、停損與2R止盈，使用今日高低價判定；同日同時觸及兩個價位標記為順序不明。",
            "crypto": "沿用昨日 up/down 趨勢，以今日單日報酬同方向視為 hit，mixed 不列入勝率。",
        },
    }
    return result, snapshot, updated_history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--report-path", type=Path, default=Path("validation_report.json"))
    parser.add_argument("--history-path", type=Path, default=Path("data/observation_history.json"))
    parser.add_argument("--output-path", type=Path, default=Path("data/backtest.json"))
    args = parser.parse_args()

    report = json.loads(args.report_path.read_text(encoding="utf-8"))
    us_rows = _read_csv(args.data_dir / "us_screen.csv")
    crypto_rows = _read_csv(args.data_dir / "crypto_screen.csv")
    history = (
        json.loads(args.history_path.read_text(encoding="utf-8"))
        if args.history_path.exists()
        else {"schema_version": 1, "snapshots": []}
    )
    result, snapshot, updated_history = build_backtest(
        report, us_rows, crypto_rows, history
    )
    args.history_path.parent.mkdir(parents=True, exist_ok=True)
    args.history_path.write_text(
        json.dumps(updated_history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "current_date": result["current_date"],
                "previous_date": result["previous_date"],
                "us_watchlist": len(snapshot["us"]),
                "crypto_watchlist": len(snapshot["crypto"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
