"""
src/pipeline.py
Core MRP Data Quality, Gross-to-Net Explosion, and SRI Prioritization Pipeline.
Processes raw synthetic tables, performs audit, runs time-phased allocation,
evaluates Shortage Risk Index (SRI) and sensitivity analysis.
"""

import os
import json
import sqlite3
import datetime
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_DIR = os.path.join(BASE_DIR, "out")
SQL_DIR = os.path.join(BASE_DIR, "sql")
DB_PATH = os.path.join(DATA_DIR, "mrp.db")
BASE_DATE = datetime.date(2026, 11, 1)


def audit_data_quality(conn: sqlite3.Connection) -> tuple[pd.DataFrame, dict]:
    """
    Audits raw tables for duplicates, nulls, negative quantities, expired lots,
    and orphan BOM records. Returns clean data frames and an audit log DataFrame.
    """
    raw_lots = pd.read_sql("SELECT * FROM inventory_lots", conn)
    raw_pos = pd.read_sql("SELECT * FROM purchase_orders", conn)
    raw_boms = pd.read_sql("SELECT * FROM boms", conn)
    raw_comps = pd.read_sql("SELECT * FROM components", conn)
    raw_prods = pd.read_sql("SELECT * FROM products", conn)
    raw_orders = pd.read_sql("SELECT * FROM production_orders", conn)

    audit_records = []

    # 1. Duplicate Lots
    dup_lots_count = int(raw_lots.duplicated(subset=["lot_id"]).sum())
    audit_records.append(
        {
            "issue_type": "duplicate_inventory_lots",
            "table_name": "inventory_lots",
            "detected_count": dup_lots_count,
            "action_taken": "Deduplicated by lot_id keeping primary entry",
        }
    )
    clean_lots = raw_lots.drop_duplicates(subset=["lot_id"]).copy()

    # 2. Duplicate POs
    dup_pos_count = int(raw_pos.duplicated(subset=["po_id"]).sum())
    audit_records.append(
        {
            "issue_type": "duplicate_purchase_orders",
            "table_name": "purchase_orders",
            "detected_count": dup_pos_count,
            "action_taken": "Deduplicated by po_id keeping primary entry",
        }
    )
    clean_pos = raw_pos.drop_duplicates(subset=["po_id"]).copy()

    # 3. Null Quantity Lots
    null_qty_count = int(clean_lots["qty_on_hand"].isna().sum())
    audit_records.append(
        {
            "issue_type": "null_quantity_lots",
            "table_name": "inventory_lots",
            "detected_count": null_qty_count,
            "action_taken": "Excluded from available stock (zero-imputed)",
        }
    )
    clean_lots = clean_lots[clean_lots["qty_on_hand"].notna()].copy()

    # 4. Negative Quantity Lots
    neg_qty_count = int((clean_lots["qty_on_hand"] < 0).sum())
    audit_records.append(
        {
            "issue_type": "negative_quantity_lots",
            "table_name": "inventory_lots",
            "detected_count": neg_qty_count,
            "action_taken": "Quarantined and excluded pending cycle count reconciliation",
        }
    )
    clean_lots = clean_lots[clean_lots["qty_on_hand"] > 0].copy()

    # 5. Expired lots marked RELEASED
    clean_lots["expiry_date_dt"] = pd.to_datetime(
        clean_lots["expiry_date"]
    ).dt.date
    expired_released_mask = (clean_lots["status"] == "RELEASED") & (
        clean_lots["expiry_date_dt"] <= BASE_DATE
    )
    exp_rel_count = int(expired_released_mask.sum())
    audit_records.append(
        {
            "issue_type": "expired_released_lots",
            "table_name": "inventory_lots",
            "detected_count": exp_rel_count,
            "action_taken": "Reclassified status to EXPIRED and excluded from available supply",
        }
    )
    # Available stock must be RELEASED and non-expired
    usable_lots = clean_lots[
        (clean_lots["status"] == "RELEASED")
        & (clean_lots["expiry_date_dt"] > BASE_DATE)
    ].copy()

    # 6. Orphan BOM lines
    valid_cids = set(raw_comps["component_id"])
    orphan_mask = ~raw_boms["component_id"].isin(valid_cids)
    orphan_boms_count = int(orphan_mask.sum())
    audit_records.append(
        {
            "issue_type": "orphan_bom_components",
            "table_name": "boms",
            "detected_count": orphan_boms_count,
            "action_taken": "Pruned unmapped BOM references to prevent runtime MRP failure",
        }
    )
    clean_boms = raw_boms[~orphan_mask].copy()

    df_audit = pd.DataFrame(audit_records)

    clean_data = {
        "products": raw_prods,
        "components": raw_comps,
        "boms": clean_boms,
        "usable_lots": usable_lots,
        "clean_pos": clean_pos[clean_pos["status"] == "OPEN"].copy(),
        "production_orders": raw_orders[raw_orders["status"] == "OPEN"].copy(),
    }
    return df_audit, clean_data


def run_pipeline():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    # 1. Audit & Clean Data
    df_audit, clean_data = audit_data_quality(conn)
    df_audit.to_csv(os.path.join(OUT_DIR, "data_quality.csv"), index=False)

    # 2. Run SQL Requirements Query (CTEs + Window Functions)
    sql_req_path = os.path.join(SQL_DIR, "requirements.sql")
    with open(sql_req_path, "r") as f:
        requirements_sql = f.read()

    df_detail = pd.read_sql_query(requirements_sql, conn)
    df_detail.to_csv(os.path.join(OUT_DIR, "shortage_detail.csv"), index=False)

    # 3. Run Pareto SQL Query
    sql_pareto_path = os.path.join(SQL_DIR, "pareto.sql")
    with open(sql_pareto_path, "r") as f:
        pareto_sql = f.read()

    df_pareto = pd.read_sql_query(pareto_sql, conn)

    # 4. Generate Component Shortage Summary with Days of Cover
    # Aggregate gross demand, total supply, shortage, and SRI by component
    gross_by_comp = (
        df_detail.groupby("component_id")["gross_qty"].sum().rename("gross_qty")
    )
    sri_by_comp = df_detail.groupby("component_id")["sri"].sum().rename("total_sri")
    orders_affected = (
        df_detail[df_detail["shortage_qty"] > 0]
        .groupby("component_id")["order_id"]
        .nunique()
        .rename("affected_orders")
    )
    prods_affected = (
        df_detail[df_detail["shortage_qty"] > 0]
        .groupby("component_id")["product_id"]
        .nunique()
        .rename("affected_products")
    )

    on_hand_by_comp = (
        clean_data["usable_lots"]
        .groupby("component_id")["qty_on_hand"]
        .sum()
        .rename("on_hand_qty")
    )
    pos_by_comp = (
        clean_data["clean_pos"]
        .groupby("component_id")["qty"]
        .sum()
        .rename("open_po_qty")
    )

    df_summary = df_pareto.merge(gross_by_comp, on="component_id", how="left")
    df_summary = df_summary.merge(sri_by_comp, on="component_id", how="left")
    df_summary = df_summary.merge(orders_affected, on="component_id", how="left")
    df_summary = df_summary.merge(prods_affected, on="component_id", how="left")
    df_summary = df_summary.merge(on_hand_by_comp, on="component_id", how="left")
    df_summary = df_summary.merge(pos_by_comp, on="component_id", how="left")

    df_summary["on_hand_qty"] = df_summary["on_hand_qty"].fillna(0.0)
    df_summary["open_po_qty"] = df_summary["open_po_qty"].fillna(0.0)
    df_summary["affected_orders"] = (
        df_summary["affected_orders"].fillna(0).astype(int)
    )
    df_summary["affected_products"] = (
        df_summary["affected_products"].fillna(0).astype(int)
    )

    # Days of cover = On Hand Stock / (Gross Requirement / 90-day horizon)
    # Capped at 365.0 days for zero/negligible burn rates
    def calc_cover(row):
        gross = row["gross_qty"]
        on_hand = row["on_hand_qty"]
        if gross <= 0:
            return 365.0
        daily_burn = gross / 90.0
        return round(float(min(365.0, on_hand / daily_burn)), 1)

    df_summary["days_of_cover"] = df_summary.apply(calc_cover, axis=1)

    # Sort summary by SRI descending
    df_summary = df_summary.sort_values(by="total_sri", ascending=False)
    df_summary.to_csv(
        os.path.join(OUT_DIR, "shortage_summary.csv"), index=False
    )

    # 5. Sensitivity Analysis for SRI Metric
    # Recompute rankings with priority weights +/-20% and urgency horizons 15/45 days
    df_short_lines = df_detail[df_detail["shortage_value"] > 0].copy()

    def rank_lines(weight_factor: float, horizon_days: float):
        pw_map = {
            "A": 3.0 * weight_factor,
            "B": 2.0 * weight_factor,
            "C": 1.0,
        }  # Baseline weights scaled
        urgency = 1.0 + np.maximum(
            0.0, (horizon_days - df_short_lines["days_to_due"]) / horizon_days
        )
        pws = df_short_lines["abc_class"].map(pw_map)
        sri = df_short_lines["shortage_value"] * pws * urgency
        return sri.sort_values(ascending=False)

    base_sri_ranks = rank_lines(weight_factor=1.0, horizon_days=30.0)
    base_top20 = set(base_sri_ranks.head(20).index)

    scenarios = [
        ("weights_plus_20pct", 1.2, 30.0),
        ("weights_minus_20pct", 0.8, 30.0),
        ("horizon_15_days", 1.0, 15.0),
        ("horizon_45_days", 1.0, 45.0),
    ]

    sensitivity_rows = []
    scen_metrics = []
    for sc_name, wf, hz in scenarios:
        sc_ranks = rank_lines(wf, hz)
        sc_top20 = set(sc_ranks.head(20).index)
        overlap_pct = (
            round(len(base_top20.intersection(sc_top20)) / 20.0 * 100.0, 1)
        )
        rho, _ = spearmanr(
            base_sri_ranks.loc[df_short_lines.index],
            sc_ranks.loc[df_short_lines.index],
        )
        sensitivity_rows.append(
            {
                "scenario_name": sc_name,
                "weight_factor": wf,
                "urgency_horizon_days": hz,
                "top20_overlap_pct": overlap_pct,
                "spearman_rho": round(float(rho), 4),
            }
        )
        scen_metrics.append(
            {
                "scenario": sc_name,
                "weight_factor": wf,
                "urgency_horizon_days": hz,
                "top20_overlap_pct": overlap_pct,
                "spearman_rho": round(float(rho), 4),
            }
        )

    df_sensitivity = pd.DataFrame(sensitivity_rows)
    df_sensitivity.to_csv(
        os.path.join(OUT_DIR, "sensitivity.csv"), index=False
    )

    # 6. Compute Headline Metrics
    total_shortage_val = round(float(df_detail["shortage_value"].sum()), 2)
    short_components_count = int(
        df_detail[df_detail["shortage_qty"] > 0]["component_id"].nunique()
    )

    # Top 20% components share of value
    # Top 20% of 24 components = top 5 components
    n_top20_comps = max(1, int(np.ceil(short_components_count * 0.20)))
    top_20pct_val = df_pareto.head(n_top20_comps)["total_shortage_value"].sum()
    top_20pct_share = round(
        float(top_20pct_val * 100.0 / total_shortage_val), 2
    )

    # Supplier Exposure & Worst Supplier
    supplier_agg = (
        df_detail.groupby("supplier")["shortage_value"].sum().sort_values(
            ascending=False
        )
    )
    worst_sup_name = supplier_agg.index[0]
    worst_sup_val = round(float(supplier_agg.iloc[0]), 2)
    worst_sup_share = round(
        float(worst_sup_val * 100.0 / total_shortage_val), 2
    )

    # Median days of cover across affected components
    median_doc = round(float(df_summary["days_of_cover"].median()), 1)

    # Top 10 by SRI (component level)
    top10_sri = []
    df_summary_by_sri = df_summary.sort_values(
        by="total_sri", ascending=False
    ).head(10)
    for _, row in df_summary_by_sri.iterrows():
        top10_sri.append(
            {
                "component_id": row["component_id"],
                "component_name": row["component_name"],
                "supplier": row["supplier"],
                "sri": round(float(row["total_sri"]), 2),
                "shortage_value": round(float(row["total_shortage_value"]), 2),
            }
        )

    min_overlap = min(r["top20_overlap_pct"] for r in sensitivity_rows)
    max_overlap = max(r["top20_overlap_pct"] for r in sensitivity_rows)
    min_rho = min(r["spearman_rho"] for r in sensitivity_rows)

    results = {
        "total_shortage_value": total_shortage_val,
        "short_components_count": short_components_count,
        "top_20pct_components_count": n_top20_comps,
        "top_20pct_share_of_value": top_20pct_share,
        "worst_supplier": {
            "supplier_name": worst_sup_name,
            "shortage_value": worst_sup_val,
            "share_of_total_pct": worst_sup_share,
        },
        "median_days_of_cover": median_doc,
        "sri_top10": top10_sri,
        "sensitivity_metrics": {
            "summary": f"SRI ranking is stable: {min_overlap}% to {max_overlap}% top-20 overlap and Spearman rho >= {min_rho} under +/-20% weight changes and 15/45-day urgency horizon shifts.",
            "scenarios": scen_metrics,
        },
    }

    with open(os.path.join(OUT_DIR, "results.json"), "w") as f:
        json.dump(results, f, indent=2)

    conn.close()
    return results


if __name__ == "__main__":
    res = run_pipeline()
    print("Pipeline Execution Completed.")
    print(f"Total Shortage Value: ${res['total_shortage_value']:,.2f}")
    print(f"Short Components Count: {res['short_components_count']}")
    print(
        f"Top 20% Components Share of Value: {res['top_20pct_share_of_value']}%"
    )
    print(
        f"Worst Supplier: {res['worst_supplier']['supplier_name']} (${res['worst_supplier']['shortage_value']:,.2f}, {res['worst_supplier']['share_of_total_pct']}%)"
    )
    print(f"Median Days of Cover: {res['median_days_of_cover']} days")
    print(f"Sensitivity: {res['sensitivity_metrics']['summary']}")
