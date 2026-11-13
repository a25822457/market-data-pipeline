from __future__ import annotations

import argparse
import json
from pathlib import Path


def _value(row: dict, key: str, digits: int = 4) -> str:
    value = row.get(key)
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _percent(row: dict, key: str, digits: int = 2) -> str:
    value = row.get(key)
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def _ratio(row: dict, key: str) -> str:
    value = row.get(key)
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value):,.2f}x"
    except (TypeError, ValueError):
        return "—"


def _date(payload: dict) -> str:
    value = payload.get("generated_at_taipei") or payload.get("generated_at") or ""
    return str(value)[:10] or "unknown"


def _is_sepa(row: dict) -> bool:
    return row.get("sepa_pass") in {True, "True", "true", 1, "1"}




def _backtest_section(backtest: dict) -> list[str]:
    lines = ["## 三、昨日觀察名單回測", ""]
    status = backtest.get("status")
    if status == "no_previous_observation":
        lines.extend(
            [
                "這是第一次保存觀察名單；下一次成功執行會自動用本次名單回測。",
                "",
                "已保存：美股 SEPA 名單，以及 252 檔 OKX 合約的昨日趨勢。",
                "",
            ]
        )
        return lines
    if status in {None, "not_available"}:
        lines.extend(["目前沒有可驗證的回測檔案。", ""])
        return lines

    lines.extend(
        [
            f"回測區間：{backtest.get('previous_date', '—')} → {backtest.get('current_date', '—')}",
            "",
            "### 美股觀察名單",
            "",
            "| 項目 | 數量 |",
            "|---|---:|",
        ]
    )
    us_summary = backtest.get("us", {}).get("summary", {})
    lines.extend(
        [
            f"| 昨日 SEPA 名單 | {us_summary.get('watchlist', 0)} |",
            f"| 已判定 | {us_summary.get('evaluated', 0)} |",
            f"| 待補資料 | {us_summary.get('pending', 0)} |",
            "",
            "| 股票 | 結果 | 今日收盤 |",
            "|---|---|---:|",
        ]
    )
    result_labels = {
        "not_triggered": "未觸發",
        "invalidated_before_entry": "未進場、跌破失效位",
        "triggered_open": "已觸發、持續觀察",
        "open": "持倉中、未觸及目標或停損",
        "target": "達到 2R 止盈",
        "stop": "觸及停損",
        "triggered_and_stop": "觸發後觸及停損",
        "both_levels_hit_same_day_unknown": "同日同時穿越停損/止盈，順序不明",
        "pending": "待補資料",
    }
    for row in backtest.get("us", {}).get("results", []):
        lines.append(
            f"| {row.get('asset', '—')} | "
            f"{result_labels.get(row.get('result'), row.get('result', '—'))} | "
            f"{_value(row, 'current_close')} |"
        )
    if not backtest.get("us", {}).get("results"):
        lines.append("| — | 無昨日 SEPA 名單 | — |")

    crypto_summary = backtest.get("crypto", {}).get("summary", {})
    hit_rate = crypto_summary.get("hit_rate")
    hit_rate_text = "—" if hit_rate is None else f"{hit_rate * 100:.2f}%"
    lines.extend(
        [
            "",
            "### OKX 合約方向回測",
            "",
            "| 項目 | 數量 |",
            "|---|---:|",
            f"| 昨日方向名單 | {crypto_summary.get('watchlist', 0)} |",
            f"| 已判定 | {crypto_summary.get('evaluated', 0)} |",
            f"| 同方向 | {crypto_summary.get('hits', 0)} |",
            f"| 反方向 | {crypto_summary.get('misses', 0)} |",
            f"| mixed 排除 | {crypto_summary.get('excluded_mixed', 0)} |",
            f"| 待補資料 | {crypto_summary.get('pending', 0)} |",
            f"| 方向命中率（只計 up/down） | {hit_rate_text} |",
            "",
            "定義：美股未進場前跌破失效位記為「未進場、跌破失效位」；已進場才用昨日參考價位對今日高低價判定停損/止盈；若同一日同時穿越停損與止盈，不擅自猜測先後。合約只檢查昨日 up/down 方向與今日報酬同向，不等同實際損益。",
            "",
            "[查看完整回測 JSON](https://github.com/a25822457/market-data-pipeline/blob/main/data/backtest.json)　"
            "[查看觀察名單歷史](https://github.com/a25822457/market-data-pipeline/blob/main/data/observation_history.json)",
            "",
        ]
    )
    return lines

def render_summary(payload: dict) -> str:
    generated = payload.get("generated_at_taipei") or payload.get("generated_at") or "unknown"
    data_as_of = payload.get("data_as_of", {})
    gate = payload.get("summary_gate", {})
    crypto_universe = payload.get("crypto_universe", {})
    us_rows = payload.get("us_screen", [])
    crypto_rows = payload.get("crypto_screen", [])
    sepa_rows = sorted(
        [row for row in us_rows if _is_sepa(row)],
        key=lambda row: float(row.get("rs_vs_spy_63d") or 0),
        reverse=True,
    )
    lines = [
        f"# 每日市場摘要｜{_date(payload)}",
        "",
        f"產生時間（台灣）：{generated}",
        "",
        "## 一、資料驗收",
        "",
        "| 項目 | 結果 |",
        "|---|---|",
        f"| overall_status | {payload.get('overall_status', 'unknown')} |",
        f"| failed | {payload.get('failed', 'unknown')} |",
        f"| summary_gate | {gate.get('status', 'unknown')} |",
        f"| 美股資料日期 | {data_as_of.get('us', 'unknown')} |",
        f"| OKX 日 K 日期 | {data_as_of.get('crypto', 'unknown')} |",
        f"| 美股檔數 | {len(us_rows)} |",
        f"| OKX 合約檔數 | {len(crypto_rows)} / {crypto_universe.get('target', 252)} |",
        "",
    ]

    warnings = list(payload.get("warnings", [])) + list(gate.get("warnings", []))
    if warnings:
        lines.extend(["**警告：**", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    errors = list(gate.get("errors", []))
    if errors or gate.get("status") not in {"ready", "ready_with_warnings"}:
        lines.extend(["**技術資料未通過驗收，以下篩選結果不應視為今日訊號。**", ""])
        lines.extend(f"- {error}" for error in errors)
        lines.append("")
        return "\n".join(lines)

    lines.extend([
        "## 二、美股 SEPA",
        "",
        f"符合 SEPA：**{len(sepa_rows)} 檔**（掃描總數 {len(us_rows)} 檔）",
        "",
        "| 股票 | 收盤 | RS／SPY | 量／50日均量 | 進場狀態 | 參考進場 | 停損 | 2R止盈 |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
    ])
    if sepa_rows:
        for row in sepa_rows:
            lines.append(
                f"| {row.get('asset', '—')} | {_value(row, 'close')} | "
                f"{_ratio(row, 'rs_vs_spy_63d')} | {_ratio(row, 'volume_vs_avg50')} | "
                f"{row.get('entry_status', '—')} | {_value(row, 'recommended_entry')} | "
                f"{_value(row, 'stop_loss')} | {_value(row, 'take_profit_2r')} |"
            )
    else:
        lines.append("| — | — | — | — | 無 | — | — | — |")
    lines.extend([
        "",
        "以上進場、停損、2R 止盈為規則計算的參考價位，不是下單指令或獲利保證。",
        "",
    ])
    lines.extend(_backtest_section(payload.get("backtest", {"status": "not_available"})))
    lines.extend([
        "## 四、OKX USDT 線性永續合約",
        "",
        f"以下列出本次驗證後的全部 {len(crypto_rows)} 檔，不混入現貨或其他交易所。",
        "",
        "| 合約 | 日 K 日期 | 收盤 | 趨勢 | 單日報酬 | 20日年化波動 | 平均報價量 | Mark | Index | Funding | OI |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    trend_order = {"up": 0, "down": 1, "mixed": 2}
    sorted_crypto = sorted(
        crypto_rows,
        key=lambda row: (
            trend_order.get(str(row.get("trend", "mixed")), 3),
            -float(row.get("avg_quote_volume_20d") or 0),
        ),
    )
    for row in sorted_crypto:
        lines.append(
            f"| {row.get('asset', '—')} | {row.get('date', '—')} | {_value(row, 'close')} | "
            f"{row.get('trend', '—')} | {_percent(row, 'return_1d')} | "
            f"{_percent(row, 'annualized_volatility_20d')} | "
            f"{_value(row, 'avg_quote_volume_20d', 0)} | {_value(row, 'mark_price')} | "
            f"{_value(row, 'index_price')} | {_percent(row, 'funding_rate', 4)} | "
            f"{_value(row, 'open_interest', 0)} |"
        )
    lines.extend([
        "",
        "本檔案由 GitHub Actions 直接產生；未包含新聞、財報文字或宏觀事件。",
        "昨日觀察名單與回測結果由 GitHub 保存，不依賴聊天記憶。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input_path.read_text(encoding="utf-8"))
    args.output_path.write_text(render_summary(payload), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output_path),
        "date": _date(payload),
        "us_rows": len(payload.get("us_screen", [])),
        "sepa_rows": sum(_is_sepa(row) for row in payload.get("us_screen", [])),
        "crypto_rows": len(payload.get("crypto_screen", [])),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
