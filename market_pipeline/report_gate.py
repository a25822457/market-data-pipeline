from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path


def _last_date(path: Path) -> str | None:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        dates = [row.get("date") for row in rows if row.get("date")]
    return max(dates) if dates else None


def validate_report(report: dict, *, us_path: Path | None = None, crypto_path: Path | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    errors: list[str] = []
    warnings: list[str] = []
    required = ("generated_at", "instruments", "passed", "failed", "overall_status")
    missing = [key for key in required if key not in report]
    if missing:
        errors.append(f"missing top-level fields: {', '.join(missing)}")
        return {"status": "fail", "errors": errors, "warnings": warnings}
    if report["overall_status"] != "pass":
        errors.append(f"overall_status={report['overall_status']}")
    if report["failed"] != 0:
        errors.append(f"failed={report['failed']}")
    if report["passed"] != len(report["instruments"]):
        errors.append("passed count does not match instrument count")
    try:
        generated_at = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
        age_hours = (now - generated_at).total_seconds() / 3600
        if age_hours < -1:
            errors.append("generated_at is in the future")
        elif age_hours > 30:
            errors.append(f"report is {age_hours:.1f} hours old")
    except (TypeError, ValueError, AttributeError):
        errors.append("generated_at is not a valid ISO-8601 timestamp")

    try:
        generated_at_taipei = generated_at.astimezone(ZoneInfo("Asia/Taipei"))
        report["generated_at_taipei"] = generated_at_taipei.isoformat()
        report["freshness_policy"] = {
            "timezone": "Asia/Taipei",
            "must_be_generated_today": True,
            "max_age_hours": 12,
        }
    except UnboundLocalError:
        pass

    as_of = report.setdefault("data_as_of", {})
    if us_path and us_path.exists():
        as_of["us"] = _last_date(us_path)
    if crypto_path and crypto_path.exists():
        as_of["crypto"] = _last_date(crypto_path)
    for label, max_days in (("us", 4), ("crypto", 2)):
        value = as_of.get(label)
        if not value:
            errors.append(f"missing data_as_of.{label}")
            continue
        try:
            age_days = (now.date() - datetime.fromisoformat(value).date()).days
            if age_days > max_days:
                errors.append(f"{label} data is {age_days} days old")
        except (TypeError, ValueError):
            errors.append(f"data_as_of.{label} is not an ISO date")

    crypto = report.get("crypto_universe", {})
    selected = int(crypto.get("selected", 0) or 0)
    target = int(crypto.get("target", 252) or 252)
    if crypto.get("status") == "partial":
        warnings.append(f"crypto universe is partial: {selected}/{target}")
    coverage_complete = crypto.get("status") == "pass" and selected >= target
    report["report_schema_version"] = 2
    report["data_as_of"] = as_of
    report["summary_gate"] = {
        "freshness_required": True,
        "status": "blocked" if errors else "ready" if coverage_complete else "ready_with_warnings",
        "us_use_csv": not errors,
        "crypto_use_csv": not errors and selected > 0,
        "crypto_coverage_complete": coverage_complete,
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
    result = validate_report(report, us_path=args.us_path, crypto_path=args.crypto_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
