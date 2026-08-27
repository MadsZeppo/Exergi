#!/usr/bin/env python3
"""Dataset acquisition guidance. This script never bypasses licensing or authentication."""

from pathlib import Path


def main() -> None:
    raw = Path("data/raw")
    raw.mkdir(parents=True, exist_ok=True)
    print("M5: place calendar.csv, sell_prices.csv, and sales_train_validation.csv in data/raw/m5")
    print("Hillstrom: place hillstrom.csv in data/raw/hillstrom (see README for canonical columns)")
    print(
        "Dominick's, Dunnhumby, and Criteo: obtain from their official "
        "distributors under their terms"
    )


if __name__ == "__main__":
    main()
