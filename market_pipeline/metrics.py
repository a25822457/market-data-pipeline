from __future__ import annotations

from statistics import mean, pstdev


def _sma(values, window, index):
    if index + 1 < window:
        return None
    return mean(values[index - window + 1:index + 1])


def _pct_return(values, window, index):
    if index < window or values[index - window] == 0:
        return None
    return values[index] / values[index - window] - 1


def _relative_strength_vs_spy(rows: list[dict], spy_rows: list[dict] | None, window: int = 63):
    """Return relative wealth ratio over a common date window.

    A plain stock_return / spy_return ratio becomes negative or explodes when
    SPY is down or close to flat.  The wealth ratio is stable and means 1.0 is
    equal performance, >1.0 outperformance, and <1.0 underperformance.
    """
    if not spy_rows:
        return None
    stock_by_date = {r["date"]: float(r["close"]) for r in rows}
    spy_by_date = {r["date"]: float(r["close"]) for r in spy_rows}
    dates = sorted(set(stock_by_date).intersection(spy_by_date))
    if len(dates) < window + 1:
        return None
    sample = dates[-(window + 1):]
    stock_start, stock_end = stock_by_date[sample[0]], stock_by_date[sample[-1]]
    spy_start, spy_end = spy_by_date[sample[0]], spy_by_date[sample[-1]]
    if min(stock_start, spy_start) <= 0:
        return None
    stock_return = stock_end / stock_start
    spy_return = spy_end / spy_start
    return stock_return / spy_return if spy_return > 0 else None


def screen_us(rows: list[dict], spy_rows: list[dict] | None = None) -> dict:
    closes = [float(r["close"]) for r in rows]
    volumes = [float(r["volume"]) for r in rows]
    i = len(rows) - 1
    sma50, sma150, sma200 = (_sma(closes, w, i) for w in (50, 150, 200))
    old_sma200 = _sma(closes, 200, i - 20) if i >= 219 else None
    lookback = rows[max(0, i - 251):i + 1]
    high52 = max(float(r["high"]) for r in lookback)
    low52 = min(float(r["low"]) for r in lookback)
    pivot20 = max(float(r["high"]) for r in rows[max(0, i - 19):i + 1])
    prior_volumes = volumes[max(0, i - 50):i]
    avg50 = mean(prior_volumes) if len(prior_volumes) == 50 else None
    rs = _relative_strength_vs_spy(rows, spy_rows, 63)
    conditions = {
        "close_above_sma50": sma50 is not None and closes[i] > sma50,
        "sma50_above_sma150": sma50 is not None and sma150 is not None and sma50 > sma150,
        "sma150_above_sma200": sma150 is not None and sma200 is not None and sma150 > sma200,
        "sma200_rising": old_sma200 is not None and sma200 > old_sma200,
        "near_52w_high": high52 > 0 and closes[i] / high52 >= 0.75,
        "above_52w_low": low52 > 0 and closes[i] / low52 >= 1.30,
        "rs_outperforms_spy": rs is not None and rs > 1.0,
        "volume_above_average": avg50 is not None and volumes[i] >= avg50,
    }
    # Volume is reported for entry/breakout confirmation, but is not a hard
    # Trend Template gate because a quiet latest day does not invalidate the
    # longer-term trend.
    trend_template = {k: v for k, v in conditions.items() if k != "volume_above_average"}
    sepa_pass = all(trend_template.values())
    recommended_entry = stop_loss = take_profit_2r = None
    entry_status = None
    if sepa_pass:
        # Reference plan: buy only after a 0.1% break above the recent 20-day
        # high, cut the position at -8%, and use a mechanical 2R target.
        recommended_entry = round(pivot20 * 1.001, 4)
        stop_loss = round(recommended_entry * 0.92, 4)
        take_profit_2r = round(
            recommended_entry + 2 * (recommended_entry - stop_loss), 4
        )
        entry_status = (
            "triggered" if closes[i] >= recommended_entry else "waiting_breakout"
        )
        # A waiting setup is not a position. If the close falls through the
        # planned stop before the breakout, invalidate the setup and remove it
        # from the actionable SEPA list instead of continuing to watch it.
        if entry_status == "waiting_breakout" and closes[i] <= stop_loss:
            entry_status = "invalidated_before_entry"
            sepa_pass = False
    return {
        "date": rows[i]["date"],
        "close": closes[i],
        "high": float(rows[i]["high"]),
        "low": float(rows[i]["low"]),
        "sma50": sma50,
        "sma150": sma150,
        "sma200": sma200,
        "sma200_slope_20d": None if old_sma200 is None else sma200 - old_sma200,
        "high_52w": high52,
        "low_52w": low52,
        "pivot_20d": pivot20,
        "volume_vs_avg50": None if avg50 is None else volumes[i] / avg50,
        "rs_vs_spy_63d": rs,
        "sepa_pass": sepa_pass,
        "recommended_entry": recommended_entry,
        "stop_loss": stop_loss,
        "take_profit_2r": take_profit_2r,
        "entry_status": entry_status,
        **conditions,
    }


def screen_crypto(rows: list[dict], futures_snapshot: dict | None = None) -> dict:
    closes = [float(r["close"]) for r in rows]
    quote_volumes = [float(r.get("quote_volume", 0)) for r in rows]
    i = len(rows) - 1
    sma20, sma50 = _sma(closes, 20, i), _sma(closes, 50, i)
    returns = [(closes[j] / closes[j - 1] - 1) for j in range(max(1, i - 19), i + 1) if closes[j - 1]]
    vol = pstdev(returns) * (365 ** 0.5) if len(returns) > 1 else None
    trend = "up" if sma20 and sma50 and closes[i] > sma20 > sma50 else "down" if sma20 and sma50 and closes[i] < sma20 < sma50 else "mixed"
    result = {"date": rows[i]["date"], "close": closes[i], "return_1d": None if i == 0 else closes[i] / closes[i - 1] - 1, "sma20": sma20, "sma50": sma50, "annualized_volatility_20d": vol, "avg_quote_volume_20d": mean(quote_volumes[max(0, i - 19):i + 1]), "trend": trend}
    if futures_snapshot:
        result.update(futures_snapshot)
    else:
        result.update({"mark_price": None, "index_price": None, "funding_rate": None, "next_funding_time": None, "open_interest": None, "snapshot_source": None})
    return result

