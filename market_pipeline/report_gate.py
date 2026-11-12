from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
US_TARGET = 100
CRYPTO_TARGET = 252


NEW_YORK = ZoneInfo("America/New_York")


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    holiday = date(year, month, day)
    if holiday.weekday() == 5:
        return holiday - timedelta(days=1)
    if holiday.weekday() == 6:
        return holiday + timedelta(days=1)
    return holiday


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    # Gregorian computus, sufficient for the current and future calendar years.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _us_market_holidays(year: int) -> set[date]:
    return {
        _observed_fixed_holiday(year, 1, 1),
        _nth_weekday(year, 1, 0, 3),   # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),   # Washington's Birthday
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),      # Memorial Day
        _observed_fixed_holiday(year, 6, 19),     # Juneteenth
        _observed_fixed_holiday(year, 7, 4),      # Independence Day
        _nth_weekday(year, 9, 0, 1),   # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving Day
        _observed_fixed_holiday(year, 12, 25),    # Christmas Day
    }


def latest_expected_us_trading_day(now: datetime | None = None) -> str:
    """Return the latest completed NYSE/Nasdaq session date.

    Veterans Day is intentionally not in the full-day holiday list because
    NYSE and Nasdaq trade normally on that date.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ny_now = now.astimezone(NEW_YORK)
    candidate = ny_now.date()
    if ny_now.time() < time(16, 0):
        candidate -= timedelta(days=1)
    holidays = set()
    for year in range(candidate.year - 1, candidate.year + 2):
        holidays.update(_us_market_holidays(year))
    while candidate.weekday() >= 5 or candidate in holidays:
        candidate -= timedelta(days=1)
    return candidate.isoformat()


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
        "sma200_slope_20d", "high_52w", "low_52w", "pivot_20d",
        "volume_vs_avg50", "rs_vs_spy_63d", "sepa_pass",
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
            "high_52w", "low_52w", "pivot_20d", "volume_vs_avg50",
            "rs_vs_spy_63d",
        ):
            if not _number(row, key):
                errors.append(f"US {row.get('asset')} has invalid {key}")
        if row.get("sepa_pass") not in {"True", "False"}:
            errors.append(f"US {row.get('asset')} has invalid sepa_pass")
        level_keys = ("recommended_entry", "stop_loss", "take_profit_2r")
        if row.get("sepa_pass") == "True":
            missing_levels = [key for key in (*level_keys, "entry_status") if not row.get(key)]
            if missing_levels:
                errors.append(
                    f"US {row.get('asset')} SEPA row missing entry levels: "
                    f"{', '.join(missing_levels)}"
                )
            else:
                for key in level_keys:
                    if not _number(row, key, positive=True):
                        errors.append(f"US {row.get('asset')} has invalid {key}")
                if row.get("entry_status") not in {"waiting_breakout", "triggered"}:
                    errors.append(f"US {row.get('asset')} has invalid entry_status")
                try:
                    entry = float(row["recommended_entry"])
                    stop = float(row["stop_loss"])
                    target = float(row["take_profit_2r"])
                    if not stop < entry < target:
                        errors.append(
                            f"US {row.get('asset')} entry levels are not ordered stop < entry < target"
                        )
                except (KeyError, TypeError, ValueError):
                    pass
        elif any(row.get(key) for key in (*level_keys, "entry_status")):
            errors.append(
                f"US {row.get('asset')} has entry levels despite sepa_pass=False"
            )
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
    expected_us_date = latest_expected_us_trading_day(now)
    if us_date and us_date != expected_us_date:
        errors.append(
            f"US data date {us_date} is not the latest completed NYSE/Nasdaq "
            f"trading day {expected_us_date}"
        )
    if benchmark_date and benchmark_date != expected_us_date:
        errors.append(
            f"SPY benchmark date {benchmark_date} is not the latest completed "
            f"NYSE/Nasdaq trading day {expected_us_date}"
        )
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
