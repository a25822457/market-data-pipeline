from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path


FIELDS = ["date", "open", "high", "low", "close", "volume", "quote_volume"]


def save_raw(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(FIELDS + [k for r in rows for k in r]))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save_snapshot(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save_sqlite(
    db_path: Path,
    raw: dict[str, list[dict]],
    us: list[dict],
    crypto: list[dict],
):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS raw_daily "
            "(asset TEXT, market TEXT, date TEXT, open REAL, high REAL, "
            "low REAL, close REAL, volume REAL, quote_volume REAL, "
            "PRIMARY KEY(asset,date))"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS screening_snapshot "
            "(run_at TEXT, asset TEXT, market TEXT, metrics_json TEXT)"
        )
        for asset, rows in raw.items():
            market = (
                "crypto"
                if "-USDT-" in asset or asset.endswith("USDT")
                else "us_stock"
            )
            db.executemany(
                "INSERT OR REPLACE INTO raw_daily VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (
                        asset,
                        market,
                        r["date"],
                        r["open"],
                        r["high"],
                        r["low"],
                        r["close"],
                        r["volume"],
                        r.get("quote_volume"),
                    )
                    for r in rows
                ],
            )
        import datetime

        run_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for market, items in (("us_stock", us), ("crypto", crypto)):
            db.executemany(
                "INSERT INTO screening_snapshot VALUES (?,?,?,?)",
                [
                    (run_at, r["asset"], market, json.dumps(r, ensure_ascii=False))
                    for r in items
                ],
            )
