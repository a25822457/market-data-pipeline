# Free-first market data pipeline

This project downloads public daily candles, validates them, computes transparent screening metrics, and writes raw data plus daily snapshots locally.

## Scope

- US stocks: `SPY`, `QQQ`, `NVDA`, `AMD`, `GOOGL`, `AMZN` from Yahoo Finance's public chart endpoint.
- Binance spot pairs: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT` from Binance's public klines endpoint.
- Minimum history: 252 complete daily bars per instrument.
- US metrics: SMA50/150/200, SMA200 slope versus 20 sessions earlier, 52-week high/low, volume versus 50-day average, and a price-relative-strength ratio versus SPY.
- Crypto metrics: last close, 24-hour return from daily candles, 20-day annualized volatility, 20-day average quote volume, and trend status from SMA20/SMA50.

The pipeline deliberately does not invent missing values. A failed or incomplete instrument is recorded as failed and is excluded from screening calculations that require it.

## Run locally

Python 3.11+ is recommended. The runtime uses only the Python standard library.

```powershell
python -m market_pipeline --output-dir data --report-path validation_report.json
```

For an offline smoke test:

```powershell
python -m unittest discover -s tests -v
```

Outputs include:

- `data/raw/*.csv`: source candles as received and normalized.
- `data/market_data.sqlite3`: raw candles and screening snapshots.
- `data/us_screen.csv`, `data/crypto_screen.csv`: latest metrics.
- `validation_report.json`: per-instrument counts, date checks, source errors, and overall status.

## Data and free-tier limitations

Yahoo Finance's public chart endpoint is an unofficial public web endpoint, can rate-limit or change without notice, and has no service-level guarantee. Binance's public market-data endpoints do not require an API key but are subject to exchange availability, regional access, and rate limits. GitHub Actions free minutes depend on account and repository policy; scheduled workflows can be delayed, disabled after repository inactivity, or fail when a provider blocks the runner. The workflow stores artifacts for inspection; it does not silently turn a failed run into a successful summary.

The requested daily summary automation is not modified. Connecting this output to it requires a separate, authorized integration step: either have the summary process read the committed artifact/SQLite export, or publish the CSV/JSON to a storage location that the summary process can access.

## Metric definitions

- `sma_*`: simple moving average of daily close.
- `sma200_slope_20d`: current SMA200 minus the SMA200 value 20 sessions earlier.
- `high_52w` / `low_52w`: rolling 252-bar high/low including the current close.
- `volume_vs_avg50`: current volume divided by the 50-bar average volume.
- `rs_vs_spy_63d`: stock's 63-session return divided by SPY's 63-session return. It is a ratio, not a vendor-provided rating.
- `sepa_pass`: the explicit trend/price/volume checks in `market_pipeline.screen_us`; it is not investment advice and does not include unsupported discretionary rules.
- Crypto trend is `up`, `down`, or `mixed` based only on close versus SMA20 and SMA20 versus SMA50.

