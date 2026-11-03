from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_input(report_path: Path, us_path: Path, crypto_path: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "source": "a25822457/market-data-pipeline",
        "generated_at": report.get("generated_at"),
        "data_as_of": report.get("data_as_of", {}),
        "overall_status": report.get("overall_status"),
        "passed": report.get("passed"),
        "failed": report.get("failed"),
        "crypto_universe": report.get("crypto_universe", {}),
        "summary_gate": report.get("summary_gate", {}),
        "warnings": report.get("warnings", []),
        "us_screen": read_csv(us_path),
        "crypto_screen": read_csv(crypto_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path", type=Path, required=True)
    parser.add_argument("--us-path", type=Path, required=True)
    parser.add_argument("--crypto-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    args = parser.parse_args()
    payload = build_input(args.report_path, args.us_path, args.crypto_path)
    args.output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output_path),
        "generated_at": payload["generated_at"],
        "us_rows": len(payload["us_screen"]),
        "crypto_rows": len(payload["crypto_screen"]),
        "summary_gate": payload["summary_gate"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
