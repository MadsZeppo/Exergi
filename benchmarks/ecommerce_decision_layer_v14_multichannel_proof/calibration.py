from __future__ import annotations

import csv
import hashlib
import json
import stat
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
MANIFESTS = ROOT / "manifests"

DUNN_RAW = REPOSITORY / "data/raw/dunnhumby/complete-journey/completejourney_1.1.0.tar.gz"
DUNN_PROCESSED = (
    REPOSITORY / "data/processed/dunnhumby/complete-journey/transaction_data.parquet"
)
DUNN_PROVENANCE = (
    REPOSITORY / "data/processed/dunnhumby/complete-journey/provenance.json"
)
UCI_RAW = REPOSITORY / "data/raw/uci/online-retail-ii/online-retail-ii.zip"
UCI_PROCESSED = REPOSITORY / "data/processed/uci/online-retail-ii/transactions.parquet"
UCI_PROVENANCE = REPOSITORY / "data/processed/uci/online-retail-ii/provenance.json"

EXPECTED = {
    "completejourney": {
        "bytes": 3_451_145,
        "sha256": "3ab70c37cc1fae797ae4b135b29acada5b56eb7eec32e1631b9fbe7c5abd4b7b",
    },
    "online_retail_ii": {
        "bytes": 45_622_418,
        "sha256": "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readonly(path: Path) -> bool:
    return path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH) == 0


def verify_sources() -> dict[str, Any]:
    dunn_provenance = json.loads(DUNN_PROVENANCE.read_text(encoding="utf-8"))
    uci_provenance = json.loads(UCI_PROVENANCE.read_text(encoding="utf-8"))
    sources: dict[str, Any] = {
        "completejourney": {
            "authority": "CRAN package sourced from 84.51 Degrees Complete Journey 2.0",
            "authority_url": "https://cran.r-project.org/package=completejourney",
            "dataset_origin_url": "https://www.8451.com/area51",
            "license": "CC0",
            "local_archive": "data/raw/dunnhumby/complete-journey/completejourney_1.1.0.tar.gz",
            "retrieved_at": dunn_provenance["placement_or_retrieval_time"],
            "sha256": sha256(DUNN_RAW),
            "bytes": DUNN_RAW.stat().st_size,
            "read_only": _readonly(DUNN_RAW),
            "processed_rows": dunn_provenance["files"]["transaction_data"]["rows"],
            "independence_group": "84_51_COMPLETE_JOURNEY",
            "observed_schema": dunn_provenance["files"]["transaction_data"]["raw_schema"],
            "transaction_extract_sha256": dunn_provenance["files"]["transaction_data"][
                "sha256"
            ],
            "limitations": [
                "NO_COGS_OR_CONTRIBUTION_PROFIT",
                "NO_AUTHORITATIVE_RETURN_FIELD",
                "CAMPAIGN_RECEIPT_IS_NOT_RANDOMIZED_ASSIGNMENT",
                "ONE_GROCERY_RETAIL_CONTEXT",
                "CHANNEL_IDENTITY_NOT_OBSERVED",
            ],
        },
        "online_retail_ii": {
            "authority": "UCI Machine Learning Repository",
            "authority_url": "https://archive.ics.uci.edu/dataset/502/online+retail+ii",
            "doi": uci_provenance["doi"],
            "license": uci_provenance["license"],
            "local_archive": "data/raw/uci/online-retail-ii/online-retail-ii.zip",
            "retrieved_at": uci_provenance["retrieved_at"],
            "sha256": sha256(UCI_RAW),
            "bytes": UCI_RAW.stat().st_size,
            "read_only": _readonly(UCI_RAW),
            "processed_rows": uci_provenance["rows_written"],
            "independence_group": "UCI_UK_NONSTORE_RETAILER",
            "observed_schema": uci_provenance["raw_schema"],
            "xlsx_sha256": uci_provenance["xlsx_sha256"],
            "limitations": [
                "NO_COGS_OR_CONTRIBUTION_PROFIT",
                "CANCELLATION_IS_NOT_MATURE_PHYSICAL_RETURN",
                "NO_RANDOMIZED_ASSIGNMENT",
                "CUSTOMER_ID_MISSING_FOR_MANY_LINES",
                "CHANNEL_IDENTITY_NOT_OBSERVED",
            ],
        },
    }
    for name, expected in EXPECTED.items():
        source = sources[name]
        if source["sha256"] != expected["sha256"] or source["bytes"] != expected["bytes"]:
            raise RuntimeError(f"V14 source integrity failure: {name}")
        if not source["read_only"]:
            raise RuntimeError(f"V14 raw source is writable: {name}")
    if len({source["independence_group"] for source in sources.values()}) < 2:
        raise RuntimeError("V14 requires two independent commerce backbones")
    return {
        "qualification": "V14_REALITY_CALIBRATION_QUALIFIED",
        "qualified_backbones": 2,
        "retrieval_policy": "PREEXISTING_RAW_SNAPSHOT_NO_NETWORK_REDOWNLOAD",
        "schema_version": 1,
        "sources": sources,
    }


def _row(connection: duckdb.DuckDBPyConnection, query: str) -> dict[str, Any]:
    result = connection.execute(query)
    names = [column[0] for column in result.description]
    return dict(zip(names, result.fetchone(), strict=True))


def calibration_statistics() -> dict[str, Any]:
    connection = duckdb.connect()
    connection.execute("SET threads = 1")
    connection.execute("SET TimeZone = 'UTC'")
    dunn = str(DUNN_PROCESSED)
    uci = str(UCI_PROCESSED)
    dunn_base = _row(
        connection,
        f"""
        SELECT count(*) AS line_count,
               count(DISTINCT HOUSEHOLD_KEY) AS customer_count,
               count(DISTINCT BASKET_ID) AS order_count,
               count(DISTINCT PRODUCT_ID) AS product_count,
               min(WEEK_NO) AS min_week,
               max(WEEK_NO) AS max_week,
               sum(SALES_VALUE) AS sales_value,
               sum(RETAIL_DISC + COUPON_DISC + COUPON_MATCH_DISC) AS discount_value
        FROM read_parquet('{dunn}')
        """,
    )
    dunn_orders = _row(
        connection,
        f"""
        WITH orders AS (
          SELECT BASKET_ID, count(*) AS lines, sum(SALES_VALUE) AS value,
                 sum(RETAIL_DISC + COUPON_DISC + COUPON_MATCH_DISC) AS discount
          FROM read_parquet('{dunn}') GROUP BY BASKET_ID
        )
        SELECT avg(value) AS mean_order_value, median(value) AS median_order_value,
               quantile_cont(value, 0.10) AS p10_order_value,
               quantile_cont(value, 0.90) AS p90_order_value,
               quantile_cont(value, 0.99) AS p99_order_value,
               avg(lines) AS mean_lines, median(lines) AS median_lines,
               avg(discount / nullif(value + discount, 0)) AS mean_discount_share
        FROM orders
        """,
    )
    dunn_customers = _row(
        connection,
        f"""
        WITH customers AS (
          SELECT HOUSEHOLD_KEY, count(DISTINCT BASKET_ID) AS orders,
                 sum(SALES_VALUE) AS value
          FROM read_parquet('{dunn}') GROUP BY HOUSEHOLD_KEY
        )
        SELECT avg(orders) AS mean_orders, median(orders) AS median_orders,
               quantile_cont(orders, 0.10) AS p10_orders,
               quantile_cont(orders, 0.90) AS p90_orders,
               quantile_cont(orders, 0.99) AS p99_orders,
               avg(value) AS mean_customer_value, median(value) AS median_customer_value
        FROM customers
        """,
    )
    dunn_week = _row(
        connection,
        f"""
        WITH weekly AS (
          SELECT WEEK_NO, sum(SALES_VALUE) AS value
          FROM read_parquet('{dunn}') GROUP BY WEEK_NO
        )
        SELECT avg(value) AS mean_weekly_sales,
               stddev_samp(value) / avg(value) AS weekly_sales_cv,
               min(value) / avg(value) AS min_week_index,
               max(value) / avg(value) AS max_week_index
        FROM weekly
        """,
    )
    uci_base = _row(
        connection,
        f"""
        SELECT count(*) AS line_count,
               count(DISTINCT customer_id) FILTER (
                 WHERE customer_id IS NOT NULL AND customer_id <> ''
               ) AS customer_count,
               count(DISTINCT invoice_no) AS order_count,
               count(DISTINCT stock_code) AS product_count,
               min(invoice_time) AS min_timestamp,
               max(invoice_time) AS max_timestamp,
               avg(is_cancellation::INT) AS cancellation_invoice_line_share
        FROM read_parquet('{uci}')
        """,
    )
    uci_orders = _row(
        connection,
        f"""
        WITH orders AS (
          SELECT invoice_no, bool_or(is_cancellation) AS cancellation,
                 count(*) AS lines, sum(line_value) AS value
          FROM read_parquet('{uci}') GROUP BY invoice_no
        )
        SELECT avg(value) FILTER (WHERE NOT cancellation AND value > 0) AS mean_order_value,
               median(value) FILTER (WHERE NOT cancellation AND value > 0) AS median_order_value,
               quantile_cont(value, 0.10) FILTER (
                 WHERE NOT cancellation AND value > 0
               ) AS p10_order_value,
               quantile_cont(value, 0.90) FILTER (
                 WHERE NOT cancellation AND value > 0
               ) AS p90_order_value,
               quantile_cont(value, 0.99) FILTER (
                 WHERE NOT cancellation AND value > 0
               ) AS p99_order_value,
               avg(lines) FILTER (WHERE NOT cancellation) AS mean_lines,
               avg(cancellation::INT) AS cancellation_order_share
        FROM orders
        """,
    )
    uci_customers = _row(
        connection,
        f"""
        WITH customers AS (
          SELECT customer_id, count(DISTINCT invoice_no) AS orders,
                 sum(line_value) AS value
          FROM read_parquet('{uci}')
          WHERE customer_id IS NOT NULL AND customer_id <> ''
          GROUP BY customer_id
        )
        SELECT avg(orders) AS mean_orders, median(orders) AS median_orders,
               quantile_cont(orders, 0.10) AS p10_orders,
               quantile_cont(orders, 0.90) AS p90_orders,
               quantile_cont(orders, 0.99) AS p99_orders,
               avg(value) AS mean_customer_value, median(value) AS median_customer_value
        FROM customers
        """,
    )
    dunn_quality = _row(
        connection,
        f"""
        SELECT
          count(*) FILTER (WHERE HOUSEHOLD_KEY IS NULL OR HOUSEHOLD_KEY = '') AS missing_customer,
          count(*) FILTER (WHERE BASKET_ID IS NULL OR BASKET_ID = '') AS missing_order,
          count(*) FILTER (WHERE PRODUCT_ID IS NULL OR PRODUCT_ID = '') AS missing_product,
          count(*) FILTER (WHERE SALES_VALUE IS NULL) AS missing_sales_value,
          count(*) FILTER (WHERE QUANTITY IS NULL) AS missing_quantity,
          count(*) FILTER (WHERE TRANSACTION_TIMESTAMP IS NULL) AS missing_timestamp,
          count(*) FILTER (WHERE SALES_VALUE < 0) AS negative_sales_lines,
          count(*) FILTER (WHERE QUANTITY < 0) AS negative_quantity_lines,
          count(*) FILTER (WHERE SALES_VALUE = 0) AS zero_sales_lines,
          count(*) FILTER (WHERE QUANTITY = 0) AS zero_quantity_lines,
          count(*) FILTER (
            WHERE try_cast(TRANSACTION_TIMESTAMP AS TIMESTAMP) IS NULL
          ) AS unparseable_timestamps
        FROM read_parquet('{dunn}')
        """,
    )
    dunn_duplicates = _row(
        connection,
        f"""
        WITH groups AS (
          SELECT count(*) AS n
          FROM read_parquet('{dunn}')
          GROUP BY HOUSEHOLD_KEY, STORE_ID, BASKET_ID, PRODUCT_ID, QUANTITY,
                   SALES_VALUE, RETAIL_DISC, COUPON_DISC, COUPON_MATCH_DISC,
                   WEEK_NO, TRANSACTION_TIMESTAMP, DAY
          HAVING count(*) > 1
        )
        SELECT coalesce(sum(n - 1), 0) AS exact_duplicate_excess_rows,
               count(*) AS exact_duplicate_groups
        FROM groups
        """,
    )
    dunn_concentration = _row(
        connection,
        f"""
        WITH customer_value AS (
          SELECT HOUSEHOLD_KEY, sum(SALES_VALUE) AS value
          FROM read_parquet('{dunn}') GROUP BY HOUSEHOLD_KEY
        ), ranked AS (
          SELECT value, row_number() OVER (ORDER BY value DESC) AS rank,
                 count(*) OVER () AS customers, sum(value) OVER () AS total
          FROM customer_value
        )
        SELECT sum(value) FILTER (WHERE rank <= ceil(customers * 0.01)) / max(total)
                 AS top_1pct_sales_share,
               sum(value) FILTER (WHERE rank <= ceil(customers * 0.10)) / max(total)
                 AS top_10pct_sales_share
        FROM ranked
        """,
    )
    dunn_interpurchase = _row(
        connection,
        f"""
        WITH baskets AS (
          SELECT HOUSEHOLD_KEY, BASKET_ID,
                 min(try_cast(TRANSACTION_TIMESTAMP AS TIMESTAMP)) AS timestamp
          FROM read_parquet('{dunn}') GROUP BY HOUSEHOLD_KEY, BASKET_ID
        ), gaps AS (
          SELECT date_diff(
            'day', lag(timestamp) OVER (PARTITION BY HOUSEHOLD_KEY ORDER BY timestamp), timestamp
          ) AS days
          FROM baskets
        )
        SELECT median(days) AS median_days,
               quantile_cont(days, 0.10) AS p10_days,
               quantile_cont(days, 0.90) AS p90_days
        FROM gaps WHERE days IS NOT NULL AND days >= 0
        """,
    )
    uci_quality = _row(
        connection,
        f"""
        SELECT
          count(*) FILTER (WHERE customer_id IS NULL OR customer_id = '') AS missing_customer,
          count(*) FILTER (WHERE invoice_no IS NULL OR invoice_no = '') AS missing_order,
          count(*) FILTER (WHERE stock_code IS NULL OR stock_code = '') AS missing_product,
          count(*) FILTER (WHERE description IS NULL OR description = '') AS missing_description,
          count(*) FILTER (WHERE unit_price IS NULL) AS missing_unit_price,
          count(*) FILTER (WHERE quantity IS NULL) AS missing_quantity,
          count(*) FILTER (WHERE invoice_time IS NULL) AS missing_timestamp,
          count(*) FILTER (WHERE unit_price < 0) AS negative_price_lines,
          count(*) FILTER (WHERE quantity < 0) AS negative_quantity_lines,
          count(*) FILTER (WHERE unit_price = 0) AS zero_price_lines,
          count(*) FILTER (WHERE quantity = 0) AS zero_quantity_lines,
          count(*) FILTER (WHERE is_cancellation) AS cancellation_lines,
          count(DISTINCT invoice_no) FILTER (WHERE is_cancellation) AS cancellation_invoices
        FROM read_parquet('{uci}')
        """,
    )
    uci_duplicates = _row(
        connection,
        f"""
        WITH groups AS (
          SELECT count(*) AS n
          FROM read_parquet('{uci}')
          GROUP BY invoice_no, stock_code, description, quantity, invoice_time,
                   unit_price, customer_id, country, is_cancellation, line_value,
                   source_sheet
          HAVING count(*) > 1
        )
        SELECT coalesce(sum(n - 1), 0) AS exact_duplicate_excess_rows,
               count(*) AS exact_duplicate_groups
        FROM groups
        """,
    )
    uci_concentration = _row(
        connection,
        f"""
        WITH customer_value AS (
          SELECT customer_id, sum(line_value) AS value
          FROM read_parquet('{uci}')
          WHERE customer_id IS NOT NULL AND customer_id <> ''
          GROUP BY customer_id
        ), ranked AS (
          SELECT value, row_number() OVER (ORDER BY value DESC) AS rank,
                 count(*) OVER () AS customers, sum(value) OVER () AS total
          FROM customer_value
        )
        SELECT sum(value) FILTER (WHERE rank <= ceil(customers * 0.01)) / max(total)
                 AS top_1pct_net_value_share,
               sum(value) FILTER (WHERE rank <= ceil(customers * 0.10)) / max(total)
                 AS top_10pct_net_value_share
        FROM ranked
        """,
    )
    uci_interpurchase = _row(
        connection,
        f"""
        WITH invoices AS (
          SELECT customer_id, invoice_no, min(invoice_time) AS timestamp
          FROM read_parquet('{uci}')
          WHERE customer_id IS NOT NULL AND customer_id <> '' AND NOT is_cancellation
          GROUP BY customer_id, invoice_no
        ), gaps AS (
          SELECT date_diff(
            'day', lag(timestamp) OVER (PARTITION BY customer_id ORDER BY timestamp), timestamp
          ) AS days
          FROM invoices
        )
        SELECT median(days) AS median_days,
               quantile_cont(days, 0.10) AS p10_days,
               quantile_cont(days, 0.90) AS p90_days
        FROM gaps WHERE days IS NOT NULL AND days >= 0
        """,
    )
    connection.close()
    result_groups = (
        dunn_base,
        dunn_orders,
        dunn_customers,
        dunn_week,
        uci_base,
        uci_orders,
        uci_customers,
        dunn_quality,
        dunn_duplicates,
        dunn_concentration,
        dunn_interpurchase,
        uci_quality,
        uci_duplicates,
        uci_concentration,
        uci_interpurchase,
    )
    for item in result_groups:
        for key, value in item.items():
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
    return {
        "calibration_only_not_causal_truth": True,
        "completejourney": {
            "population": dunn_base,
            "orders": dunn_orders,
            "customers": dunn_customers,
            "seasonality": dunn_week,
            "quality": dunn_quality,
            "duplicates": dunn_duplicates,
            "customer_concentration": dunn_concentration,
            "interpurchase_time": dunn_interpurchase,
            "unit_of_observation": "ITEM_LINE_IN_RETAIL_BASKET",
            "time_semantics": "OBSERVED_TRANSACTION_TIMESTAMP_AND_WEEK_NUMBER",
            "monetary_authority": "OBSERVED_SALES_AND_DISCOUNTS_NOT_PROFIT",
            "return_authority": "NO_AUTHORITATIVE_RETURN_FIELD",
        },
        "online_retail_ii": {
            "population": uci_base,
            "orders": uci_orders,
            "customers": uci_customers,
            "quality": uci_quality,
            "duplicates": uci_duplicates,
            "customer_concentration": uci_concentration,
            "interpurchase_time": uci_interpurchase,
            "unit_of_observation": "ITEM_LINE_IN_INVOICE_OR_CANCELLATION",
            "time_semantics": "OBSERVED_INVOICE_TIMESTAMP_UTC_NORMALIZED",
            "monetary_authority": "OBSERVED_UNIT_PRICE_TIMES_QUANTITY_NOT_PROFIT",
            "return_authority": "CANCELLATION_PROXY_NOT_MATURE_PHYSICAL_RETURN",
        },
        "unsupported_calibrations": [
            "causal_treatment_effects",
            "channel_assignment_effects",
            "cogs",
            "payment_fees",
            "fulfilment_costs",
            "shipping_costs",
            "mature_physical_returns",
            "contribution_profit",
        ],
        "schema_version": 1,
    }


def write_calibration_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    source = verify_sources()
    statistics = calibration_statistics()
    (MANIFESTS / "V14_SOURCE_SNAPSHOT.json").write_text(
        json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ROOT / "calibration_reference_stats.json").write_text(
        json.dumps(statistics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    machine_artifact = {
        "authority": "AGGREGATE_REALITY_CALIBRATION_ONLY",
        "calibration_statistics": statistics,
        "causal_truth_imported": False,
        "cross_source_entities_joined": False,
        "qualified_backbones": source["qualified_backbones"],
        "schema_version": 1,
        "source_snapshot": source,
        "synthetic_outcomes_generated": False,
    }
    (ROOT / "V14_REALITY_CALIBRATION.json").write_text(
        json.dumps(machine_artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    qa = {
        "checks": {
            "aggregate_only": statistics["calibration_only_not_causal_truth"],
            "completejourney_row_count_matches_provenance": (
                statistics["completejourney"]["population"]["line_count"]
                == source["sources"]["completejourney"]["processed_rows"]
            ),
            "independent_backbones_gte_2": source["qualified_backbones"] >= 2,
            "no_causal_truth_imported": not machine_artifact["causal_truth_imported"],
            "no_cross_source_entity_join": not machine_artifact["cross_source_entities_joined"],
            "no_synthetic_outcomes": not machine_artifact["synthetic_outcomes_generated"],
            "online_retail_row_count_matches_provenance": (
                statistics["online_retail_ii"]["population"]["line_count"]
                == source["sources"]["online_retail_ii"]["processed_rows"]
            ),
            "raw_archives_read_only": all(
                item["read_only"] for item in source["sources"].values()
            ),
        },
        "input_hashes": {
            name: item["sha256"] for name, item in source["sources"].items()
        },
        "phase": "REALITY_CALIBRATION_ONLY",
        "schema_version": 1,
        "status": "PASS",
    }
    if not all(qa["checks"].values()):
        raise RuntimeError("V14 calibration QA failed")
    (ROOT / "V14_CALIBRATION_QA.json").write_text(
        json.dumps(qa, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    mapping = [
        ("order_value", "completejourney,online_retail_ii", "lognormal family and quantile bounds"),
        ("order_frequency", "completejourney,online_retail_ii", "lifecycle purchase intensity"),
        ("basket_lines", "completejourney,online_retail_ii", "compound order size"),
        ("discount_share", "completejourney", "promotion and cannibalization calibration"),
        ("cancellation_share", "online_retail_ii", "return/refund marginal proxy only"),
        ("weekly_seasonality", "completejourney", "observable demand index bounds"),
        ("treatment_effect", "none", "synthetic evaluator truth; never source-estimated"),
        ("cogs_and_fees", "none", "declared preregistered family-specific synthetic costs"),
    ]
    with (ROOT / "calibration_mapping.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["target", "source", "use"])
        writer.writerows(mapping)
    return source, statistics


if __name__ == "__main__":
    write_calibration_artifacts()
