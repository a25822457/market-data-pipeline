# Free-first market data pipeline

This project downloads public daily candles, validates them, computes transparent screening metrics, and writes raw data plus daily snapshots locally.

## Scope

- US stocks: every run asks Yahoo Finance's public most-actives screener for a broad candidate list, ranks eligible equities by estimated daily dollar volume, and selects 100 symbols with at least 252 complete daily bars. A versioned Nasdaq-100-based list is used only as an explicit fallback if the dynamic Yahoo ranking fails or cannot produce 100 valid histories. SPY is used as the benchmark.
- Binance spot pairs: the top 252 eligible USDT spot pairs by 24-hour quote volume, selected from Binance public exchange metadata and ticker data, then validated with daily klines.
- Minimum history: 252 complete daily bars per instrument.
- US metrics: SMA50/150/200, SMA200 slope versus 20 sessions earlier, 52-week high/low, volume versus 50-day average, and a price-relative-strength ratio versus SPY.
- Crypto metrics: last close, 24-hour return from daily candles, 20-day annualized volatility, 20-day average quote volume, and trend status from SMA20/SMA50.

The pipeline deliberately does not invent missing values. A failed or incomplete instrument is recorded as failed and is excluded from screening calculations that require it. The validation report records whether the US list came from the dynamic ranking or the versioned fallback.

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

- `data/raw/*.csv`: source candles as received and normalized. GitHub Actions uploads these in the run artifact; it commits only the compact screening snapshots and validation report to avoid repository bloat.
- `data/market_data.sqlite3`: raw candles and screening snapshots.
- `data/us_screen.csv`, `data/crypto_screen.csv`: latest metrics.
- `validation_report.json`: per-instrument counts, date checks, source errors, overall status, and US universe selection mode.

## Data and free-tier limitations

Yahoo Finance's public chart and screener endpoints are unofficial public web endpoints, can rate-limit or change without notice, and have no service-level guarantee. The dynamic US list is therefore a daily volume-based ranking, not a guaranteed market-cap ranking. If Yahoo's screener is unavailable, the report explicitly shows the versioned fallback list was used. Binance's public market-data endpoints do not require an API key but are subject to exchange availability, regional access, and rate limits. GitHub Actions free minutes depend on account and repository policy; scheduled workflows can be delayed, disabled after repository inactivity, or fail when a provider blocks the runner. The workflow stores artifacts for inspection; it does not silently turn a failed run into a successful summary.

The requested daily summary automation is not modified. Connecting this output to it requires a separate, authorized integration step: either have the summary process read the committed artifact/SQLite export, or publish the CSV/JSON to a storage location that the summary process can access.

## Metric definitions

- `sma_*`: simple moving average of daily close.
- `sma200_slope_20d`: current SMA200 minus the SMA200 value 20 sessions earlier.
- `high_52w` / `low_52w`: rolling 252-bar high/low including the current close.
- `volume_vs_avg50`: current volume divided by the 50-bar average volume.
- `rs_vs_spy_63d`: stock's 63-session return divided by SPY's 63-session return. It is a ratio, not a vendor-provided rating.
- `sepa_pass`: the explicit trend/price/volume checks in `market_pipeline.screen_us`; it is not investment advice and does not include unsupported discretionary rules.
- Crypto trend is `up`, `down`, or `mixed` based only on close versus SMA20 and SMA20 versus SMA50.

Universe selection: dynamic Yahoo most-active US equity ranking for 100 stocks, with explicit versioned fallback; top-252 Binance USDT spot scan.
