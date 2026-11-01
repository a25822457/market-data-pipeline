from __future__ import annotations

from datetime import date, timedelta


def validate_rows(rows, min_bars=252):
    errors = []
    dates = [r.get("date") for r in rows]
    if len(rows) < min_bars: errors.append(f"only {len(rows)} complete bars; need {min_bars}")
    if len(set(dates)) != len(dates): errors.append("duplicate dates")
    if dates != sorted(dates): errors.append("dates are not ascending")
    for r in rows:
        try:
            if not all(float(r[k]) > 0 for k in ("open", "high", "low", "close", "volume")): errors.append(f"non-positive OHLCV on {r.get('date')}")
            if not (float(r["low"]) <= float(r["open"]) <= float(r["high"]) and float(r["low"]) <= float(r["close"]) <= float(r["high"])): errors.append(f"OHLC relationship invalid on {r.get('date')}")
        except (KeyError, TypeError, ValueError): errors.append(f"missing/non-numeric OHLCV on {r.get('date')}")
    gaps = 0
    for a, b in zip(dates, dates[1:]):
        try:
            if date.fromisoformat(b) - date.fromisoformat(a) > timedelta(days=10): gaps += 1
        except (TypeError, ValueError): pass
    return {"status": "pass" if not errors else "fail", "bars": len(rows), "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None, "large_calendar_gaps": gaps, "errors": errors}

