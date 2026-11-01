from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _get_json(url: str, timeout: int = 30) -> dict | list:
    request = Request(url, headers={"User-Agent": "free-market-pipeline/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_binance_json(path: str) -> dict | list:
    last_error = None
    for host in ("api.binance.com", "data-api.binance.vision", "api1.binance.com", "api2.binance.com", "api3.binance.com", "api4.binance.com"):
        try:
            return _get_json(f"https://{host}{path}")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"all Binance spot endpoints failed for {path}; last error: {last_error}")


def fetch_binance_futures_json(path: str) -> dict | list:
    last_error = None
    for host in ("fapi.binance.com", "fapi1.binance.com", "fapi2.binance.com", "fapi3.binance.com", "fapi4.binance.com"):
        try:
            return _get_json(f"https://{host}{path}")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"all Binance USDⓈ-M futures endpoints failed for {path}; last error: {last_error}")


def fetch_yahoo_json(path: str) -> dict:
    last_error = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            return _get_json(f"https://{host}{path}")
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"all Yahoo public endpoints failed for {path}; last error: {last_error}")


def fetch_yahoo_most_active_candidates(limit: int = 250) -> list[str]:
    payload = fetch_yahoo_json(f"/v1/finance/screener/predefined/saved?{urlencode({'scrIds': 'most_actives', 'count': limit})}")
    results = payload.get("finance", {}).get("result") or []
    quotes = results[0].get("quotes", []) if results else []
    eligible = []
    for quote in quotes:
        if quote.get("quoteType") not in (None, "EQUITY"):
            continue
        symbol = quote.get("symbol")
        price = quote.get("regularMarketPrice") or quote.get("regularMarketPreviousClose") or 0
        volume = quote.get("regularMarketVolume") or 0
        if symbol and price and volume:
            eligible.append((symbol, float(price) * float(volume)))
    if not eligible:
        raise RuntimeError("Yahoo most-actives response contained no eligible equities")
    return [symbol for symbol, _ in sorted(eligible, key=lambda item: item[1], reverse=True)]


def fetch_yahoo_daily(symbol: str, min_bars: int = 252) -> list[dict]:
    period2 = int(time.time()) + 86400
    period1 = period2 - 500 * 86400
    query = urlencode({"period1": period1, "period2": period2, "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    last_error = None
    payload = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            payload = _get_json(f"https://{host}/v8/finance/chart/{symbol}?{query}")
            if payload.get("chart", {}).get("result"):
                break
        except Exception as exc:
            last_error = exc
    if payload is None:
        raise RuntimeError(f"all Yahoo public endpoints failed; last error: {last_error}")
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
    payload = fetch_binance_json(f"/api/v3/klines?{query}")
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


def fetch_binance_futures_daily(symbol: str, min_bars: int = 252) -> list[dict]:
    query = urlencode({"symbol": symbol, "interval": "1d", "limit": 1000})
    payload = fetch_binance_futures_json(f"/fapi/v1/klines?{query}")
    if not isinstance(payload, list):
        raise RuntimeError(f"Binance futures returned an error: {payload}")
    rows = []
    now_ms = int(time.time() * 1000)
    for item in payload:
        open_time, o, h, low, close, volume, close_time, quote_volume = item[:8]
        if close_time > now_ms:
            continue
        rows.append({"date": datetime.fromtimestamp(open_time / 1000, timezone.utc).date().isoformat(), "open": float(o), "high": float(h), "low": float(low), "close": float(close), "volume": float(volume), "quote_volume": float(quote_volume), "taker_buy_volume": float(item[9]), "taker_buy_quote_volume": float(item[10])})
    if len(rows) < min_bars:
        raise RuntimeError(f"Binance futures returned {len(rows)} complete bars; need at least {min_bars}")
    return rows


def fetch_binance_futures_snapshot(symbol: str) -> dict:
    premium = fetch_binance_futures_json(f"/fapi/v1/premiumIndex?{urlencode({'symbol': symbol})}")
    open_interest = fetch_binance_futures_json(f"/fapi/v1/openInterest?{urlencode({'symbol': symbol})}")
    if not isinstance(premium, dict) or not isinstance(open_interest, dict):
        raise RuntimeError(f"Binance futures snapshot returned an unexpected response for {symbol}")
    return {
        "mark_price": float(premium["markPrice"]),
        "index_price": float(premium["indexPrice"]),
        "funding_rate": float(premium["lastFundingRate"]) if premium.get("lastFundingRate") not in (None, "") else None,
        "next_funding_time": premium.get("nextFundingTime"),
        "open_interest": float(open_interest["openInterest"]),
        "snapshot_source": "Binance USDⓈ-M futures public market data",
    }
