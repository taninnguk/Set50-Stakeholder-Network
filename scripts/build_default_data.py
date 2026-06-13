from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from network_analysis import records_to_dataframe
from set_scraper import SetScraper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the default shareholder snapshot for the Streamlit app.",
    )
    parser.add_argument("--index", default="SET50", choices=["SET50", "SET100"])
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--lang", default="th", choices=["th", "en"])
    parser.add_argument("--browser", default="chrome", choices=["chrome", "edge"])
    parser.add_argument("--headed", action="store_true", help="Run browser with UI.")
    parser.add_argument(
        "--output",
        default=str(ROOT_DIR / "data" / "default_shareholders.csv"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    records = []
    errors: list[str] = []

    with SetScraper(
        browser=args.browser,
        headless=not args.headed,
        lang=args.lang,
        delay_seconds=0.2,
    ) as scraper:
        stocks = scraper.get_index_symbols(args.index)[: args.limit]
        for index, stock in enumerate(stocks, start=1):
            print(f"[{index}/{len(stocks)}] {stock.symbol}", flush=True)
            try:
                records.extend(
                    scraper.get_shareholders(
                        stock.symbol,
                        company_name=stock.name,
                        top_n=args.top_n,
                    )
                )
            except Exception as exc:
                errors.append(f"{stock.symbol}: {exc}")

    df = records_to_dataframe(records)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(df)} rows to {output}")

    if errors:
        print("Errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
