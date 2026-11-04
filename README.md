# Free-first market data pipeline

This project downloads public daily candles, validates them, computes transparent screening metrics, and writes raw data plus daily snapshots locally.

## Scope

- US stocks: 100 Nasdaq-100 company names from a versioned 2026-05-01 Nasdaq factsheet, with one Alphabet share class omitted so the universe contains 100 companies, from Yahoo Finance's public chart endpoint. SPY is used as the benchmark.
- OKX USDT linear perpetual swaps: up to 252 live contracts ranked by 24-hour volume. The pipeline uses every eligible contract with at least 252 complete daily bars; a smaller live universe is a visible coverage warning, never an invented row. Daily candles use OKX `1Dutc` so the latest completed UTC day is available before the Taiwan 09:00 summary.
- Minimum history: 252 complete daily bars per instrument.
- US metrics: SMA50/150/200, SMA200 slope versus 20 sessions earlier, 52-week high/low, volume versus 50-day average, a price-relative-strength ratio versus SPY, and reference trade levels for SEPA-passing stocks.
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
- `data/daily_summary.md`: a human-readable Traditional Chinese summary generated directly by GitHub Actions; it includes validation, SEPA reference levels, and the complete validated OKX contract table.

## Data and free-tier limitations

Yahoo Finance's public chart endpoint is an unofficial public web endpoint, can rate-limit or change without notice, and has no service-level guarantee. OKX's public market-data endpoints do not require an API key but are subject to exchange availability, regional access, and rate limits. GitHub Actions free minutes depend on account and repository policy; scheduled workflows can be delayed, disabled after repository inactivity, or fail when a provider blocks the runner. The workflow stores artifacts for inspection; it does not silently turn a failed run into a successful summary.

The canonical daily-summary source is `data/daily_summary_input.json`. The zero-Work delivery is `data/daily_summary.md`: GitHub Actions renders it directly after the canonical JSON passes validation, so reading the daily report does not require a ChatGPT Work run. The daily summary must use it only when `summary_gate.status` is `ready` or `ready_with_warnings`, `overall_status=pass`, `failed=0`, the US rows are exactly 100 and share SPY's latest session date, and the crypto rows are fresh, validated, and equal to the selected OKX universe. `ready_with_warnings` is allowed only for a real coverage shortfall such as 249/252; the missing count must be shown. Any freshness, numeric, snapshot, or schema failure blocks the technical sections; old CSVs must never be used as a fallback. The workflow runs every day at 08:10 Asia/Taipei with recovery runs at 08:40 and 09:05 if an earlier schedule is delayed or missed. The recovery run skips itself when a valid snapshot for today already exists. Each collection attempt retries up to three times, requires all OKX futures snapshots, and publishes nothing as successful unless freshness, coverage, and row-level checks pass.

## Metric definitions

- `sma_*`: simple moving average of daily close.
- `sma200_slope_20d`: current SMA200 minus the SMA200 value 20 sessions earlier.
- `high_52w` / `low_52w`: rolling 252-bar high/low including the current close.
- `volume_vs_avg50`: current volume divided by the 50-bar average volume.
- `rs_vs_spy_63d`: the stock's 63-session wealth multiple divided by SPY's 63-session wealth multiple, aligned on common dates. `1.0` means equal performance, above `1.0` means outperformance, and below `1.0` means underperformance. It is not a vendor-provided rating.
- `sepa_pass`: the explicit Trend Template checks in `market_pipeline.screen_us`: price/SMA ordering, rising SMA200, 52-week position, and RS outperformance. Current-day volume is reported separately for breakout/entry confirmation and is not a hard trend gate.
- `pivot_20d`: the highest daily high in the latest 20 sessions.
- `recommended_entry`, `stop_loss`, `take_profit_2r`: emitted only when `sepa_pass=True`. The reference plan uses a 0.1% buffer above `pivot_20d`, an 8% loss cut below entry, and a 2R target. `entry_status` is `waiting_breakout` or `triggered`. These are educational reference levels, not orders, guarantees, or position-sizing advice.
- Crypto trend is `up`, `down`, or `mixed` based only on close versus SMA20 and SMA20 versus SMA50.



## Yesterday watchlist backtest

The first successful run after this feature is deployed reports \`no_previous_observation\` because it is creating the baseline. From the following successful run onward, GitHub Actions calculates the backtest automatically and commits both the JSON result and the history file. No ChatGPT Work run is required. If a collection or validation run fails, no new observation snapshot is written and the previous result is not presented as today's backtest.
