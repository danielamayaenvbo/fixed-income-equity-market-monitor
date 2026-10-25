"""Run a local Treasury and equity backfill with ``python -m app.ingestion``."""

from argparse import ArgumentParser
from datetime import date

from app.ingestion.service import run_ingestion


def main() -> None:
    parser = ArgumentParser(description="Ingest Treasury yields and daily equity bars.")
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        default=date(2015, 1, 1),
        help="Inclusive ISO-8601 backfill date (default: 2015-01-01).",
    )
    args = parser.parse_args()
    run_ingestion(start=args.start)


if __name__ == "__main__":
    main()
