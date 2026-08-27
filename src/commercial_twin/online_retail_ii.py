"""Official UCI Online Retail II ingestion and semantics audit."""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import pyarrow as pa
import pyarrow.parquet as pq

UCI_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
UCI_DOI = "10.24432/C5CG6D"
UCI_LICENSE = "CC BY 4.0"
RAW_COLUMNS = (
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
)
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    with workbook.open("xl/sharedStrings.xml") as source:
        root = ET.parse(source).getroot()
    return ["".join(node.itertext()) for node in root.findall(f"{NS}si")]


def _excel_datetime(value: str) -> datetime:
    return datetime(1899, 12, 30, tzinfo=UTC) + timedelta(days=float(value))


def _cell_value(cell: ET.Element, shared: list[str]) -> str | None:
    value = cell.find(f"{NS}v")
    if value is None or value.text is None:
        return None
    if cell.attrib.get("t") == "s":
        return shared[int(value.text)]
    return value.text


def _rows(workbook: zipfile.ZipFile, sheet: str, shared: list[str]) -> Iterator[list[str | None]]:
    with workbook.open(sheet) as source:
        for _, row in ET.iterparse(source, events=("end",)):
            if row.tag != f"{NS}row":
                continue
            cells: list[str | None] = [None] * 8
            for cell in row.findall(f"{NS}c"):
                reference = cell.attrib.get("r", "A1")
                letters = "".join(char for char in reference if char.isalpha())
                index = 0
                for char in letters:
                    index = index * 26 + ord(char.upper()) - 64
                if 1 <= index <= 8:
                    cells[index - 1] = _cell_value(cell, shared)
            yield cells
            row.clear()


def prepare_online_retail_ii(
    xlsx_path: str | Path,
    output_path: str | Path,
    provenance_path: str | Path,
    *,
    source_zip: str | Path | None = None,
) -> dict[str, object]:
    """Stream both XLSX sheets into a typed Parquet without cleaning away semantics."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema(
        [
            ("invoice_no", pa.string()),
            ("stock_code", pa.string()),
            ("description", pa.string()),
            ("quantity", pa.float64()),
            ("invoice_time", pa.timestamp("us", tz="UTC")),
            ("unit_price", pa.float64()),
            ("customer_id", pa.string()),
            ("country", pa.string()),
            ("is_cancellation", pa.bool_()),
            ("line_value", pa.float64()),
            ("source_sheet", pa.string()),
        ]
    )
    rows_written = 0
    writer = pq.ParquetWriter(target, schema, compression="zstd")
    try:
        with zipfile.ZipFile(xlsx_path) as workbook:
            shared = _shared_strings(workbook)
            for sheet in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"):
                batch: list[dict[str, object]] = []
                iterator = _rows(workbook, sheet, shared)
                header = next(iterator)
                if tuple(header) != RAW_COLUMNS:
                    raise ValueError(f"unexpected Online Retail II schema: {header}")
                for values in iterator:
                    invoice, stock, description, quantity, date, price, customer, country = values
                    if not invoice or not date:
                        continue
                    qty = float(quantity) if quantity not in (None, "") else math.nan
                    unit_price = float(price) if price not in (None, "") else math.nan
                    batch.append(
                        {
                            "invoice_no": invoice,
                            "stock_code": stock,
                            "description": description,
                            "quantity": qty,
                            "invoice_time": _excel_datetime(date),
                            "unit_price": unit_price,
                            "customer_id": customer,
                            "country": country,
                            "is_cancellation": invoice.upper().startswith("C"),
                            "line_value": qty * unit_price,
                            "source_sheet": Path(sheet).stem,
                        }
                    )
                    if len(batch) >= 50_000:
                        writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                        rows_written += len(batch)
                        batch.clear()
                if batch:
                    writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                    rows_written += len(batch)
    finally:
        writer.close()
    provenance = {
        "dataset": "Online Retail II",
        "uci_dataset_id": 502,
        "source_url": UCI_URL,
        "doi": UCI_DOI,
        "license": UCI_LICENSE,
        "retrieved_at": datetime.fromtimestamp(Path(xlsx_path).stat().st_mtime, UTC).isoformat(),
        "xlsx_sha256": sha256_file(xlsx_path),
        "source_zip_sha256": sha256_file(source_zip) if source_zip else None,
        "raw_schema": list(RAW_COLUMNS),
        "rows_written": rows_written,
        "observed_fields": list(RAW_COLUMNS),
        "derived_fields": ["is_cancellation", "line_value", "source_sheet"],
    }
    Path(provenance_path).write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return provenance
