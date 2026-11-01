from __future__ import annotations

from .sources import (
    fetch_binance_futures_daily,
    fetch_binance_futures_json,
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


def fetch_top_binance_usdt_perpetuals(target: int = 252, min_bars: int = 252) -> dict[str, list[dict]]:
    exchange = fetch_binance_futures_json("/fapi/v1/exchangeInfo")
    allowed = {
        s["symbol"]
        for s in exchange.get("symbols", [])
        if s.get("status") == "TRADING"
        and s.get("contractType") == "PERPETUAL"
        and s.get("quoteAsset") == "USDT"
    }
    tickers = fetch_binance_futures_json("/fapi/v1/ticker/24hr")
    ranked = sorted(
        (t for t in tickers if t.get("symbol") in allowed),
        key=lambda t: float(t.get("quoteVolume", 0) or 0),
        reverse=True,
    )
    selected: dict[str, list[dict]] = {}
    for ticker in ranked:
        symbol = ticker["symbol"]
        try:
            selected[symbol] = fetch_binance_futures_daily(symbol, min_bars=min_bars)
        except Exception:
            continue
        if len(selected) >= target:
            break
    if len(selected) < target:
        raise RuntimeError(f"only {len(selected)} Binance USDⓈ-M USDT perpetuals had at least {min_bars} complete daily bars; need {target}")
    return selected
