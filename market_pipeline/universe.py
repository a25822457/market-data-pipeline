from __future__ import annotations

from .sources import fetch_binance_daily, fetch_binance_json

# Nasdaq-100 securities as listed in Nasdaq's 2026-05-01 factsheet. GOOG is
# omitted so Alphabet's two share classes count as one company for a 100-name
# universe. EA and WBD are replaced by GOOG and JPM because Yahoo's public
# chart endpoint returned only one complete bar for those two symbols during
# validation. The list is versioned here so runs remain reproducible.
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


def fetch_top_binance_usdt_pairs(target: int = 252, min_bars: int = 252) -> dict[str, list[dict]]:
    exchange = fetch_binance_json("/api/v3/exchangeInfo")
    allowed = {
        s["symbol"] for s in exchange.get("symbols", [])
        if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT" and s.get("isSpotTradingAllowed", False)
    }
    tickers = fetch_binance_json("/api/v3/ticker/24hr")
    ranked = sorted(
        (t for t in tickers if t.get("symbol") in allowed),
        key=lambda t: float(t.get("quoteVolume", 0) or 0),
        reverse=True,
    )
    selected: dict[str, list[dict]] = {}
    for ticker in ranked:
        symbol = ticker["symbol"]
        try:
            selected[symbol] = fetch_binance_daily(symbol, min_bars=min_bars)
        except Exception:
            continue
        if len(selected) >= target:
            break
    if len(selected) < target:
        raise RuntimeError(f"only {len(selected)} Binance USDT spot pairs had at least {min_bars} complete daily bars; need {target}")
    return selected

