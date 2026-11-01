# Free-first market data pipeline

This project downloads public daily candles, validates them, computes transparent screening metrics, and writes raw data plus daily snapshots locally.

## Scope

- US stocks: every run asks Yahoo Finance's public most-actives screener for a broad candidate list, ranks eligible equities by estimated daily dollar volume, and selects 100 symbols with at least 252 complete daily bars. A versioned Nasdaq-100-based list is used only as an explicit fallback if the dynamic Yahoo ranking fails or cannot produce 100 valid histories. SPY is used as the benchmark.
- Crypto: every run uses OKX's public USDT-margined linear SWAP market, ranks eligible perpetual swaps by 24-hour quote volume, targets 252 contracts, and accepts a smaller validated set when fewer than 252 contracts have at least 252 complete daily bars. The actual count and shortfall are recorded in the validation report.
- Futures-specific snapshot fields: mark price, index price, latest funding rate, next funding time, open interest, and open-interest value. If a snapshot call fails, the value is left empty and the validation report records the failure.
- Minimum history: 252 complete daily bars per instrument.
- US metrics: SMA50/150/200, SMA200 slope versus 20 sessions earlier, 52-week high/low, volume versus 50-day average, and a price-relative-strength ratio versus SPY.
- Crypto metrics: last close, 24-hour return from perpetual candles, 20-day annualized volatility, 20-day average quote volume, trend status from SMA20/SMA50, plus futures snapshot fields.

The pipeline deliberately does not invent missing values. A failed or incomplete instrument is recorded as failed and is excluded from screening calculations that require it. A shortfall in the OKX target is a warning, not a fabricated pass.

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
- `validation_report.json`: per-instrument counts, date checks, source errors, overall status, actual crypto count, target shortfall, and futures snapshot failures.

## Data and free-tier limitations

Yahoo Finance's public chart and screener endpoints are unofficial public web endpoints, can rate-limit or change without notice, and have no service-level guarantee. OKX's public market-data endpoints do not require an API key for these fields, but they are subject to exchange availability, regional access, rate limits, endpoint changes, and jurisdictional restrictions. If OKX is unavailable, the run is marked failed and does not silently fall back to spot data. If OKX has fewer than 252 contracts with the requested history, the run continues with the validated smaller set and records the shortfall. GitHub Actions free minutes depend on account and repository policy; scheduled workflows can be delayed, disabled after repository inactivity, or fail when a provider blocks the runner. The workflow stores artifacts for inspection; it does not silently turn a failed run into a successful summary.

This pipeline is market-data analysis, not order execution. It does not place trades, access account balances, or use API keys. Binance USDⓈ-M and Bybit support remain in the source module for reference; the daily primary source is OKX because the prior GitHub Actions region returned Binance HTTP 451 and Bybit HTTP 403.

The requested daily summary automation is not modified. Connecting this output to it requires a separate, authorized integration step: either have the summary process read the committed artifact/SQLite export, or publish the CSV/JSON to a storage location that the summary process can access.

## Metric definitions

- `sma_*`: simple moving average of daily close.
- `sma200_slope_20d`: current SMA200 minus the SMA200 value 20 sessions earlier.
- `high_52w` / `low_52w`: rolling 252-bar high/low including the current close.
- `volume_vs_avg50`: current volume divided by the 50-bar average volume.
- `rs_vs_spy_63d`: stock's 63-session return divided by SPY's 63-session return. It is a ratio, not a vendor-provided rating.
- `sepa_pass`: the explicit trend/price/volume checks in `market_pipeline.screen_us`; it is not investment advice and does not include unsupported discretionary rules.
- Crypto trend is `up`, `down`, or `mixed` based only on perpetual contract close versus SMA20 and SMA50.
- `mark_price`, `index_price`, `funding_rate`, `open_interest`, and `open_interest_value` come from OKX public SWAP market-data endpoints and are not fabricated when unavailable.

Universe selection: dynamic Yahoo most-active US equity ranking for 100 stocks, with explicit versioned fallback; dynamic OKX USDT linear perpetual SWAP ranking targeting 252 contracts with an honest validated shortfall warning when necessary.
