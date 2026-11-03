from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
US_TARGET = 100
CRYPTO_TARGET = 252


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def _read_rows(path: Path | None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _last_date(rows: list[dict[str, str]]) -> str | None:
    dates = [row.get("date") for row in rows if row.get("date")]
    return max(dates) if dates else None


def _number(row: dict[str, str], key: str, *, positive: bool = False) -> bool:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return False
    return math.isfinite(value) and (value > 0 if positive else True)


def _validate_us_rows(rows: list[dict[str, str]], as_of: str | None) -> list[str]:
    errors: list[str] = []
    required = (
        "asset", "date", "close", "sma50", "sma150", "sma200",
        "sma200_slope_20d", "high_52w", "low_52w", "volume_vs_avg50",
        "rs_vs_spy_63d", "sepa_pass",
    )
    if len(rows) != US_TARGET:
        errors.append(f"US screen has {len(rows)} rows; need exactly {US_TARGET}")
    assets = [row.get("asset") for row in rows]
    if len(set(assets)) != len(assets):
        errors.append("US screen has duplicate assets")
    for row in rows:
        missing = [key for key in required if not row.get(key)]
        if missing:
            errors.append(f"US {row.get('asset')} missing fields: {', '.join(missing)}")
            continue
        if as_of and row["date"] != as_of:
            errors.append(f"US {row['asset']} date {row['date']} differs from data_as_of.us {as_of}")
        for key in (
            "close", "sma50", "sma150", "sma200", "sma200_slope_20d",
            "high_52w", "low_52w", "volume_vs_avg50", "rs_vs_spy_63d",
        ):
            if not _number(row, key):
                errors.append(f"US {row.get('asset')} has invalid {key}")
        if row.get("sepa_pass") not in {"True", "False"}:
            errors.append(f"US {row.get('asset')} has invalid sepa_pass")
    return errors


def _validate_crypto_rows(rows: list[dict[str, str]], as_of: str | None) -> list[str]:
    errors: list[str] = []
    required = (
        "asset", "date", "close", "return_1d", "sma20", "sma50",
        "annualized_volatility_20d", "avg_quote_volume_20d", "trend",
        "mark_price", "index_price", "funding_rate", "open_interest",
    )
    if not rows:
        errors.append("crypto screen has no rows")
    if len(rows) > CRYPTO_TARGET:
        errors.append(f"crypto screen has {len(rows)} rows; cannot exceed target {CRYPTO_TARGET}")
    assets = [row.get("asset") for row in rows]
    if len(set(assets)) != len(assets):
        errors.append("crypto screen has duplicate assets")
    for row in rows:
        missing = [key for key in required if not row.get(key)]
        if missing:
            errors.append(f"crypto {row.get('asset')} missing fields: {', '.join(missing)}")
            continue
        if as_of and row["date"] != as_of:
            errors.append(f"crypto {row['asset']} date {row['date']} differs from data_as_of.crypto {as_of}")
        for key in (
            "close", "return_1d", "sma20", "sma50",
            "annualized_volatility_20d", "avg_quote_volume_20d", "funding_rate",
        ):
            if not _number(row, key):
                errors.append(f"crypto {row.get('asset')} has invalid {key}")
        for key in ("mark_price", "index_price", "open_interest"):
            if not _number(row, key, positive=True):
                errors.append(f"crypto {row.get('asset')} has invalid {key}")
        if row.get("trend") not in {"up", "down", "mixed"}:
            errors.append(f"crypto {row.get('asset')} has invalid trend")
    return errors


def validate_report(
    report: dict,
    *,
    us_path: Path | None = None,
    crypto_path: Path | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    errors: list[str] = []
    warnings: list[str] = []
    required = ("generated_at", "instruments", "passed", "failed", "overall_status")
    missing = [key for key in required if key not in report]
    if missing:
        errors.append(f"missing top-level fields: {', '.join(missing)}")
        report["summary_gate"] = {"status": "blocked", "errors": errors}
        return {"status": "fail", "errors": errors, "warnings": warnings}
    if report["overall_status"] != "pass":
        errors.append(f"overall_status={report['overall_status']}")
    if report["failed"] != 0:
        errors.append(f"failed={report['failed']}")
    if report["passed"] != len(report["instruments"]):
        errors.append("passed count does not match instrument count")
    try:
        generated_at = _parse_datetime(report["generated_at"])
        age_hours = (now - generated_at).total_seconds() / 3600
        if age_hours < -1:
            errors.append("generated_at is in the future")
        elif age_hours > 12:
            errors.append(f"report is {age_hours:.1f} hours old; must be <= 12 hours")
        report["generated_at_taipei"] = generated_at.astimezone(TAIPEI).isoformat()
    except (TypeError, ValueError, AttributeError):
        errors.append("generated_at is not a timezone-aware ISO-8601 timestamp")

    report["freshness_policy"] = {
        "timezone": "Asia/Taipei",
        "must_be_generated_today": True,
        "max_age_hours": 12,
        "crypto_requires_latest_completed_utc_day": True,
        "full_universe_required": True,
    }

    as_of = report.setdefault("data_as_of", {})
    us_rows = _read_rows(us_path)
    crypto_rows = _read_rows(crypto_path)
    if us_rows:
        as_of["us"] = _last_date(us_rows)
    if crypto_rows:
        as_of["crypto"] = _last_date(crypto_rows)

    us_date = as_of.get("us")
    crypto_date = as_of.get("crypto")
    if not us_date:
        errors.append("missing data_as_of.us")
    if not crypto_date:
        errors.append("missing data_as_of.crypto")

    benchmark = report.get("us_benchmark", {})
    benchmark_date = benchmark.get("last_date")
    if benchmark.get("status") != "pass":
        errors.append("SPY benchmark validation did not pass")
    if us_date and benchmark_date and us_date != benchmark_date:
        errors.append(f"US data date {us_date} differs from SPY date {benchmark_date}")
    if us_date:
        try:
            us_age_days = (now.date() - datetime.fromisoformat(us_date).date()).days
            if us_age_days > 4:
                errors.append(f"US data is {us_age_days} calendar days old")
        except ValueError:
            errors.append("data_as_of.us is not an ISO date")

    if crypto_date:
        try:
            expected_crypto_date = (
                now.astimezone(timezone.utc).date() - timedelta(days=1)
            ).isoformat()
            if crypto_date != expected_crypto_date:
                errors.append(
                    f"crypto data date {crypto_date} is not the latest completed UTC day "
                    f"{expected_crypto_date}"
                )
        except ValueError:
            errors.append("data_as_of.crypto is not an ISO date")

    crypto = report.get("crypto_universe", {})
    selected = int(crypto.get("selected", 0) or 0)
    target = int(crypto.get("target", CRYPTO_TARGET) or CRYPTO_TARGET)
    if selected != len(crypto_rows):
        errors.append(
            f"crypto universe selected={selected} but screen rows={len(crypto_rows)}"
        )
    if selected == 0:
        errors.append("crypto universe returned no eligible contracts")
    if target != CRYPTO_TARGET:
        errors.append(f"crypto target changed from {CRYPTO_TARGET} to {target}")
    if crypto.get("status") not in {"pass", "partial"}:
        errors.append(f"crypto_universe.status={crypto.get('status')}")
    if report.get("futures_snapshot_failed", 0):
        errors.append(f"futures snapshots failed={report['futures_snapshot_failed']}")

    errors.extend(_validate_us_rows(us_rows, us_date))
    errors.extend(_validate_crypto_rows(crypto_rows, crypto_date))

    report["report_schema_version"] = 3
    report["data_as_of"] = as_of
    report["summary_gate"] = {
        "freshness_required": True,
        "status": (
            "blocked"
            if errors
            else "ready"
            if selected == CRYPTO_TARGET
            else "ready_with_warnings"
        ),
        "us_use_csv": not errors,
        "crypto_use_csv": not errors and bool(crypto_rows),
        "crypto_coverage_complete": selected == CRYPTO_TARGET,
        "errors": errors,
        "warnings": warnings + list(report.get("warnings", [])),
    }
    return {"status": "pass" if not errors else "fail", "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path", type=Path, default=Path("validation_report.json"))
    parser.add_argument("--us-path", type=Path)
    parser.add_argument("--crypto-path", type=Path)
    args = parser.parse_args()
    report_path = args.report_path
    report = json.loads(report_path.read_text(encoding="utf-8"))
    result = validate_report(
        report,
        us_path=args.us_path,
        crypto_path=args.crypto_path,
    )
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
