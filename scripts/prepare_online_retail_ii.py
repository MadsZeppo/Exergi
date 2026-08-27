from pathlib import Path

from commercial_twin.online_retail_ii import prepare_online_retail_ii


def main() -> None:
    root = Path("data/raw/uci/online-retail-ii")
    provenance = prepare_online_retail_ii(
        root / "online_retail_II.xlsx",
        "data/processed/uci/online-retail-ii/transactions.parquet",
        "data/processed/uci/online-retail-ii/provenance.json",
        source_zip=root / "online-retail-ii.zip",
    )
    print(provenance)


if __name__ == "__main__":
    main()
