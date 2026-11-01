from __future__ import annotations

from urllib.parse import urlencode

from .sources import (
    fetch_bybit_daily,
    fetch_bybit_json,
    fetch_yahoo_daily,
    fetch_yahoo_most_active_candidates,
)

# Versioned fallback list used only when Yahoo's dynamic most-actives endpoint
# is unavailable or returns too few valid 252-bar histories.
US_TOP100 = [
    "ADBE", "AMD", "ABNB", "ALNY", "GOOGL", "AMZN", "AEP", "AMGN", "ADI", "AAPL",
    "AMAT", "APP", "ARM", "ASML", "ADSK", "ADP", "AXON", "BKR", "BKNG", "AVGO",
    "CDNS", "CHTR", "CTAS", "CSCO", "CCEP", "CTSH", "CMCSA", "CEG", "CPRT", "CSGP",
    "COST", "CRWD", "CSX", "DDOG", "DXCM", "FANG", "DASH", "GOOG", "EXC", "FAST",
    "FER", "FTNT", "GEHC", "GILD", "HON", "IDXX", "INSM", "INTC", "INTU", "ISRG",
    "KDP", "KLAC", "KHC", "LRCX", "LIN", "MAR", "MRVL", "MELI", "META", "MCHP",
    "MU", "MSFT", "MDLZ", "MPWR", "MNST", "NFLX", "NVDA", "NXPI", "ORLY", "ODFL",
    "PCAR", "PLTR", "PANW", "PAYX", "PYPL", "PDD", "PEP", "QCOM", "REGN", "ROP",
    "ROST", "SNDK", "STX", "SHOP", "SBUX", "MSTR", "SNPS", "TMUS", "TTWO", "TSLA",
    "TXN", "TRI", "VRSK", "VRTX", "WMT", "WDC", "WDAY", "XEL", "ZS", "JPM",
]


def fetch_top_us_stocks(target: int = 100, min_bars: int = 252) -> tuple[list[str], str]:
    try:
        candidates = fetch_yahoo_most_active_candidates(limit=max(250, target * 2))
        mode = "Yahoo most-actives by estimated daily dollar volume"
    except Exception as exc:
        candidates = []
        mode = f"versioned fallback; dynamic Yahoo ranking failed: {type(exc).__name__}: {exc}"

    selected: list[str] = []
    seen: set[str] = set()
    for symbol in [*candidates, *US_TOP100]:
        if symbol in seen or symbol == "SPY":
            continue
        seen.add(symbol)
        try:
            fetch_yahoo_daily(symbol, min_bars=min_bars)
        except Exception:
            continue
        selected.append(symbol)
        if len(selected) >= target:
            break
    if len(selected) < target:
        raise RuntimeError(f"only {len(selected)} US equities had at least {min_bars} complete daily bars; need {target}")
    return selected, mode


def fetch_top_bybit_usdt_perpetuals(target: int = 252, min_bars: int = 252) -> dict[str, list[dict]]:
    instruments = []
    cursor = None
    while True:
        query = {"category": "linear", "status": "Trading", "limit": 1000}
        if cursor:
            query["cursor"] = cursor
        payload = fetch_bybit_json(f"/v5/market/instruments-info?{urlencode(query)}")
        result = payload.get("result", {})
        instruments.extend(result.get("list", []))
        cursor = result.get("nextPageCursor")
        if not cursor:
            break
    allowed = {
        item["symbol"]
        for item in instruments
        if item.get("status") == "Trading"
        and item.get("contractType") == "LinearPerpetual"
        and item.get("settleCoin") == "USDT"
    }
    ticker_payload = fetch_bybit_json("/v5/market/tickers?category=linear")
    tickers = ticker_payload.get("result", {}).get("list", [])
    ranked = sorted(
        (t for t in tickers if t.get("symbol") in allowed),
        key=lambda t: float(t.get("turnover24h", 0) or 0),
        reverse=True,
    )
    selected: dict[str, list[dict]] = {}
    for ticker in ranked:
        symbol = ticker["symbol"]
        try:
            selected[symbol] = fetch_bybit_daily(symbol, min_bars=min_bars)
        except Exception:
            continue
        if len(selected) >= target:
            break
    if len(selected) < target:
        raise RuntimeError(f"only {len(selected)} Bybit USDT linear perpetuals had at least {min_bars} complete daily bars; need {target}")
    return selected
