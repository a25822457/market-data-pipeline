# Free-first market data pipeline

This project downloads public daily candles, validates them, computes transparent screening metrics, and writes raw data plus daily snapshots locally.

## Scope

- US stocks: every run asks Yahoo Finance's public most-actives screener for a broad candidate list, ranks eligible equities by estimated daily dollar volume, and selects 100 symbols with at least 252 complete daily bars. A versioned Nasdaq-100-based list is used only as an explicit fallback if the dynamic Yahoo ranking fails or cannot produce 100 valid histories. SPY is used as the benchmark.
- Binance crypto: every run ranks eligible Binance USDⓈ-M USDT perpetual contracts by 24-hour quote volume, selects 252 contracts with at least 252 complete daily bars, and uses those perpetual candles as the primary crypto signal.
- Futures-specific snapshot fields: mark price, index price, latest funding rate, next funding time, and open interest. If a snapshot call fails, the value is left empty and the validation report records the failure.
- Minimum history: 252 complete daily bars per instrument.
- US metrics: SMA50/150/200, SMA200 slope versus 20 sessions earlier, 52-week high/low, volume versus 50-day average, and a price-relative-strength ratio versus SPY.
- Crypto metrics: last close, 24-hour return from perpetual candles, 20-day annualized volatility, 20-day average quote volume, trend status from SMA20/SMA50, plus futures snapshot fields.

The pipeline deliberately does not invent missing values. A failed or incomplete instrument is recorded as failed and is excluded from screening calculations that require it. The validation report records whether the US list came from the dynamic ranking and whether Binance futures access succeeded.

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
- `validation_report.json`: per-instrument counts, date checks, source errors, overall status, universe selection modes, and futures access/snapshot failures.

## Data and free-tier limitations

Yahoo Finance's public chart and screener endpoints are unofficial public web endpoints, can rate-limit or change without notice, and have no service-level guarantee. The dynamic US list is therefore a daily volume-based ranking, not a guaranteed market-cap ranking. Binance public USDⓈ-M futures market-data endpoints do not require an API key for these public fields, but they are subject to exchange availability, regional access, rate limits, endpoint changes, and regional HTTP 451 restrictions. If the futures endpoint is unavailable, the run is marked failed and does not silently fall back to spot data. GitHub Actions free minutes depend on account and repository policy; scheduled workflows can be delayed, disabled after repository inactivity, or fail when a provider blocks the runner. The workflow stores artifacts for inspection; it does not silently turn a failed run into a successful summary.

This pipeline is market-data analysis, not order execution. It does not place trades, access account balances, or use API keys.

The requested daily summary automation is not modified. Connecting this output to it requires a separate, authorized integration step: either have the summary process read the committed artifact/SQLite export, or publish the CSV/JSON to a storage location that the summary process can access.

## Metric definitions

- `sma_*`: simple moving average of daily close.
- `sma200_slope_20d`: current SMA200 minus the SMA200 value 20 sessions earlier.
- `high_52w` / `low_52w`: rolling 252-bar high/low including the current close.
- `volume_vs_avg50`: current volume divided by the 50-bar average volume.
- `rs_vs_spy_63d`: stock's 63-session return divided by SPY's 63-session return. It is a ratio, not a vendor-provided rating.
- `sepa_pass`: the explicit trend/price/volume checks in `market_pipeline.screen_us`; it is not investment advice and does not include unsupported discretionary rules.
- Crypto trend is `up`, `down`, or `mixed` based only on perpetual contract close versus SMA20 and SMA50.
- `mark_price`, `index_price`, `funding_rate`, and `open_interest` come from Binance USDⓈ-M public futures market-data endpoints and are not fabricated when unavailable.

Universe selection: dynamic Yahoo most-active US equity ranking for 100 stocks, with explicit versioned fallback; dynamic Binance USDⓈ-M USDT perpetual ranking for 252 contracts.
