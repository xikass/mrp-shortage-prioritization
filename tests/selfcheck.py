"""
tests/selfcheck.py
Automated validation and integrity test suite for MRP Shortage Prioritization.
Asserts data dimensions, algorithmic sanity, dirty-data audit detections,
and output file sizes.
Exits 0 on success, non-zero on failure.
"""

import os
import sys
import json
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_DIR = os.path.join(BASE_DIR, "out")
CHARTS_DIR = os.path.join(BASE_DIR, "charts")
DB_PATH = os.path.join(DATA_DIR, "mrp.db")


def run_checks():
    print("Running self-check assertions...")

    # 1. Database & Table Dimensions
    assert os.path.exists(DB_PATH), f"Missing database: {DB_PATH}"
    conn = sqlite3.connect(DB_PATH)

    prods = pd.read_sql("SELECT * FROM products", conn)
    assert len(prods) == 40, f"Expected 40 products, got {len(prods)}"
    print("  [PASS] 40 products verified.")

    comps = pd.read_sql("SELECT * FROM components", conn)
    assert len(comps) >= 100, f"Expected >= 100 components, got {len(comps)}"
    print(f"  [PASS] >= 100 components verified ({len(comps)} found).")

    conn.close()

    # 2. Pipeline Output: No Negative Shortage
    detail_path = os.path.join(OUT_DIR, "shortage_detail.csv")
    assert os.path.exists(detail_path), f"Missing {detail_path}"
    df_detail = pd.read_csv(detail_path)

    assert (df_detail["shortage_qty"] >= 0).all(), "Found negative shortage quantity!"
    assert (df_detail["shortage_value"] >= 0).all(), "Found negative shortage value!"
    assert (df_detail["sri"] >= 0).all(), "Found negative Shortage Risk Index!"
    print("  [PASS] No negative shortages or risk scores.")

    # 3. Pareto Cumulative Final = 100 ± 0.01%
    summary_path = os.path.join(OUT_DIR, "shortage_summary.csv")
    assert os.path.exists(summary_path), f"Missing {summary_path}"
    df_summary = pd.read_csv(summary_path)

    final_cum_share = float(df_summary["cum_share_pct"].iloc[-1])
    assert abs(final_cum_share - 100.0) <= 0.01, f"Pareto final cumulative share {final_cum_share} != 100%"
    print(f"  [PASS] Pareto cumulative final is {final_cum_share:.2f}%.")

    # 4. Each Injected Dirty-Data Class Detected with Count > 0
    audit_path = os.path.join(OUT_DIR, "data_quality.csv")
    assert os.path.exists(audit_path), f"Missing {audit_path}"
    df_audit = pd.read_csv(audit_path)

    expected_issues = [
        "duplicate_inventory_lots",
        "duplicate_purchase_orders",
        "null_quantity_lots",
        "negative_quantity_lots",
        "expired_released_lots",
        "orphan_bom_components"
    ]
    detected_issues = dict(zip(df_audit["issue_type"], df_audit["detected_count"]))
    for issue in expected_issues:
        assert issue in detected_issues, f"Missing issue type: {issue}"
        assert detected_issues[issue] > 0, f"Issue {issue} count must be > 0, got {detected_issues[issue]}"
    print(f"  [PASS] All 6 dirty data classes successfully detected with count > 0.")

    # 5. All 4 Charts Exist and > 10KB
    expected_charts = [
        "01_pareto.png",
        "02_heatmap.png",
        "03_lead_time_vs_shortage.png",
        "04_supplier_exposure.png"
    ]
    for ch in expected_charts:
        ch_path = os.path.join(CHARTS_DIR, ch)
        assert os.path.exists(ch_path), f"Missing chart: {ch_path}"
        size_kb = os.path.getsize(ch_path) / 1024.0
        assert size_kb > 10.0, f"Chart {ch} too small: {size_kb:.1f} KB <= 10 KB"
    print(f"  [PASS] All 4 decision-grade charts exist and exceed 10 KB threshold.")

    # 6. results.json Has Required Keys
    results_path = os.path.join(OUT_DIR, "results.json")
    assert os.path.exists(results_path), f"Missing {results_path}"
    with open(results_path, "r") as f:
        results = json.load(f)

    required_keys = [
        "total_shortage_value",
        "short_components_count",
        "top_20pct_share_of_value",
        "worst_supplier",
        "median_days_of_cover",
        "sri_top10",
        "sensitivity_metrics"
    ]
    for rk in required_keys:
        assert rk in results, f"Missing key in results.json: {rk}"
    assert len(results["sri_top10"]) == 10, f"Expected 10 items in sri_top10, got {len(results['sri_top10'])}"
    assert "summary" in results["sensitivity_metrics"], "Missing summary in sensitivity_metrics"
    assert "scenarios" in results["sensitivity_metrics"], "Missing scenarios in sensitivity_metrics"
    print("  [PASS] results.json schema and required metrics validated.")

    print("\nALL VERIFICATION CHECKS PASSED (100%).")


if __name__ == "__main__":
    try:
        run_checks()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n[FAIL] Assertion Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(2)
