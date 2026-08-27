from __future__ import annotations

import argparse
from pathlib import Path

from decision_engine.datasets.dunnhumby import DunnhumbyDataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare authorized local Dunnhumby Complete Journey files"
    )
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/dunnhumby/complete-journey"),
    )
    parser.add_argument("--source", required=True, help="Authorized source or placement reference")
    parser.add_argument("--license-terms", required=True, help="Applicable license/terms reference")
    args = parser.parse_args()
    provenance = DunnhumbyDataset(args.raw_dir).prepare(
        args.output_dir,
        source=args.source,
        license_terms=args.license_terms,
    )
    print(args.output_dir / "provenance.json")
    print(f"prepared {len(provenance['files'])} source files")


if __name__ == "__main__":
    main()
