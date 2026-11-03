# Free-first market data pipeline

This project downloads public daily candles, validates them, computes transparent screening metrics, and writes raw data plus daily snapshots locally.

## Scope

- US stocks: 100 Nasdaq-100 company names from a versioned 2026-05-01 Nasdaq factsheet, with one Alphabet share class omitted so the universe contains 100 companies, from Yahoo Finance's public chart endpoint. SPY is used as the benchmark.
- OKX USDT linear perpetual swaps: up to 252 live contracts ranked by 24-hour volume, with an honest partial-universe warning when fewer than 252 have at least 252 complete daily bars.
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

- `data/raw/*.csv`: source candles as received and normalized. GitHub Actions uploads these in the run artifact; it commits only the compact screening snapshots and validation report to avoid repository bloat.
- `data/market_data.sqlite3`: raw candles and screening snapshots.
- `data/us_screen.csv`, `data/crypto_screen.csv`: latest metrics.
- `validation_report.json`: per-instrument counts, date checks, source errors, freshness fields, summary gate, and overall status.

## Data and free-tier limitations

Yahoo Finance's public chart endpoint is an unofficial public web endpoint, can rate-limit or change without notice, and has no service-level guarantee. OKX's public market-data endpoints do not require an API key but are subject to exchange availability, regional access, and rate limits. GitHub Actions free minutes depend on account and repository policy; scheduled workflows can be delayed, disabled after repository inactivity, or fail when a provider blocks the runner. The workflow stores artifacts for inspection; it does not silently turn a failed run into a successful summary.

The canonical daily-summary source is `data/daily_summary_input.json`. The daily summary must read it from the GitHub project file page and check `generated_at`, `data_as_of`, `overall_status`, `passed`, `failed`, and `summary_gate` before using any rows. If the file is stale or fails the gate, it must not use old CSVs for technical conclusions. The workflow runs every day, retries public-data collection up to three times, and enforces a strict same-day Taiwan-time summary rule with a 12-hour report limit. It also enforces 4-day US-data and 2-day crypto-data limits.

## Metric definitions

- `sma_*`: simple moving average of daily close.
- `sma200_slope_20d`: current SMA200 minus the SMA200 value 20 sessions earlier.
- `high_52w` / `low_52w`: rolling 252-bar high/low including the current close.
- `volume_vs_avg50`: current volume divided by the 50-bar average volume.
- `rs_vs_spy_63d`: the stock's 63-session wealth multiple divided by SPY's 63-session wealth multiple, aligned on common dates. `1.0` means equal performance, above `1.0` means outperformance, and below `1.0` means underperformance. It is not a vendor-provided rating.
- `sepa_pass`: the explicit Trend Template checks in `market_pipeline.screen_us`: price/SMA ordering, rising SMA200, 52-week position, and RS outperformance. Current-day volume is reported separately for breakout/entry confirmation and is not a hard trend gate.
- Crypto trend is `up`, `down`, or `mixed` based only on close versus SMA20 and SMA20 versus SMA50.

