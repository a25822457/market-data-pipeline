from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _get_json(url: str, timeout: int = 30) -> dict:
    request = Request(url, headers={"User-Agent": "free-market-pipeline/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_yahoo_daily(symbol: str, min_bars: int = 252) -> list[dict]:
    period2 = int(time.time()) + 86400
    period1 = period2 - 500 * 86400
    query = urlencode({"period1": period1, "period2": period2, "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    payload = _get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}")
    result = payload.get("chart", {}).get("result")
    error = payload.get("chart", {}).get("error")
    if not result:
        raise RuntimeError(f"Yahoo returned no result: {error}")
    block = result[0]
    timestamps = block.get("timestamp", [])
    quote = block.get("indicators", {}).get("quote", [{}])[0]
    rows = []
    for i, stamp in enumerate(timestamps):
        vals = {key: (quote.get(key) or [None] * len(timestamps))[i] for key in ("open", "high", "low", "close", "volume")}
        if all(v is not None for v in vals.values()):
            rows.append({"date": datetime.fromtimestamp(stamp, timezone.utc).date().isoformat(), "open": vals["open"], "high": vals["high"], "low": vals["low"], "close": vals["close"], "volume": vals["volume"]})
    if len(rows) < min_bars:
        raise RuntimeError(f"Yahoo returned {len(rows)} complete bars; need at least {min_bars}")
    return rows


def fetch_binance_daily(symbol: str, min_bars: int = 252) -> list[dict]:
    query = urlencode({"symbol": symbol, "interval": "1d", "limit": 1000})
    payload = _get_json(f"https://api.binance.com/api/v3/klines?{query}")
    if not isinstance(payload, list):
        raise RuntimeError(f"Binance returned an error: {payload}")
    rows = []
    now_ms = int(time.time() * 1000)
    for item in payload:
        open_time, o, h, low, close, volume, close_time, quote_volume = item[:8]
        if close_time > now_ms:
            continue
        rows.append({"date": datetime.fromtimestamp(open_time / 1000, timezone.utc).date().isoformat(), "open": float(o), "high": float(h), "low": float(low), "close": float(close), "volume": float(volume), "quote_volume": float(quote_volume)})
    if len(rows) < min_bars:
        raise RuntimeError(f"Binance returned {len(rows)} complete bars; need at least {min_bars}")
    return rows

