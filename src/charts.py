"""
src/charts.py
Generates decision-grade matplotlib visualizations for MRP Shortage Prioritization.
Outputs:
  - charts/01_pareto.png
  - charts/02_heatmap.png
  - charts/03_lead_time_vs_shortage.png
  - charts/04_supplier_exposure.png
"""

import os
import sqlite3
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARTS_DIR = os.path.join(BASE_DIR, "charts")
OUT_DIR = os.path.join(BASE_DIR, "out")
DATA_DIR = os.path.join(BASE_DIR, "data")

# Style configurations
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Helvetica", "Arial"]
plt.rcParams["axes.edgecolor"] = "#cccccc"
plt.rcParams["axes.linewidth"] = 0.8


def plot_pareto(df_pareto: pd.DataFrame):
    """
    1. Pareto Chart: Top 20 components by shortage value with cumulative % curve.
    """
    df_top20 = df_pareto.head(20).copy()

    fig, ax1 = plt.subplots(figsize=(12, 6), dpi=150)

    # Colors: dark teal for bars, deep coral for line
    bar_color = "#1f77b4"
    line_color = "#d62728"

    # Bar plot for shortage value
    bars = ax1.bar(
        range(len(df_top20)),
        df_top20["total_shortage_value"] / 1000.0,
        color=bar_color,
        alpha=0.85,
        edgecolor="#0f4c81",
        width=0.65,
        label="Shortage Value ($k)"
    )

    ax1.set_xlabel("Component Code", fontsize=11, fontweight="bold", labelpad=8)
    ax1.set_ylabel("Net Shortage Value ($k USD)", fontsize=11, fontweight="bold", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.set_xticks(range(len(df_top20)))
    ax1.set_xticklabels(df_top20["component_id"], rotation=45, ha="right", fontsize=9)
    ax1.grid(True, linestyle="--", alpha=0.4, axis="y")

    # Line plot for cumulative percentage
    ax2 = ax1.twinx()
    ax2.plot(
        range(len(df_top20)),
        df_top20["cum_share_pct"],
        color=line_color,
        marker="o",
        linewidth=2.2,
        markersize=5,
        label="Cumulative Share (%)"
    )
    ax2.axhline(80.0, color="#2ca02c", linestyle=":", linewidth=1.5, label="80% Pareto Cutoff")
    ax2.set_ylabel("Cumulative Value Share (%)", fontsize=11, fontweight="bold", color="#d62728")
    ax2.tick_params(axis="y", labelcolor="#d62728")
    ax2.set_ylim(0, 105)
    ax2.grid(False)

    plt.title(
        "Pareto Distribution: Top 20 Shortage Components (Value & Cumulative Share)",
        fontsize=13,
        fontweight="bold",
        pad=15
    )

    fig.tight_layout()
    out_path = os.path.join(CHARTS_DIR, "01_pareto.png")
    plt.savefig(out_path)
    plt.close()
    print(f"Saved: {out_path}")


def plot_heatmap(df_detail: pd.DataFrame):
    """
    2. Heatmap: Top 10 shortage components across 8 due-date weekly/bi-weekly buckets.
    """
    # Filter to demand lines with shortages
    df_short = df_detail[df_detail["shortage_qty"] > 0].copy()

    # Identify top 10 components by total shortage value
    top10_cids = (
        df_short.groupby("component_id")["shortage_value"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .index.tolist()
    )
    df_top10 = df_short[df_short["component_id"].isin(top10_cids)].copy()

    # Create 8 due-date horizon bins (10-day intervals from Day 10 to Day 90)
    bins = [10, 20, 30, 40, 50, 60, 70, 80, 95]
    labels = ["10-20d", "21-30d", "31-40d", "41-50d", "51-60d", "61-70d", "71-80d", "81-90d"]
    df_top10["due_bucket"] = pd.cut(df_top10["days_to_due"], bins=bins, labels=labels, right=True)

    # Pivot table: Component vs Due Bucket (sum of shortage quantity)
    pivot = df_top10.pivot_table(
        index="component_id",
        columns="due_bucket",
        values="shortage_qty",
        aggfunc="sum",
        fill_value=0.0,
        observed=False
    )

    # Reindex rows to match top 10 descending order
    pivot = pivot.reindex(top10_cids)

    fig, ax = plt.subplots(figsize=(11, 6), dpi=150)

    # Using YlOrRd or viridis colorblind-friendly colormap
    cax = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto")
    cbar = fig.colorbar(cax, ax=ax, fraction=0.035, pad=0.04)
    cbar.set_label("Shortage Quantity (units/kg)", fontsize=10, fontweight="bold")

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_yticks(range(len(top10_cids)))
    ax.set_yticklabels(top10_cids, fontsize=10, fontweight="bold")

    ax.set_xlabel("Production Order Due Date Horizon", fontsize=11, fontweight="bold", labelpad=8)
    ax.set_ylabel("Component ID (Ranked by Total Shortage)", fontsize=11, fontweight="bold")

    # Annotate cell numbers
    for i in range(len(top10_cids)):
        for j in range(len(labels)):
            val = pivot.values[i, j]
            if val > 0:
                color = "white" if val > pivot.values.max() * 0.55 else "black"
                ax.text(j, i, f"{val:,.0f}", ha="center", va="center", color=color, fontsize=8.5, fontweight="bold")

    plt.title(
        "Time-Phased Shortage Heatmap: Top 10 Components vs Demand Horizon",
        fontsize=13,
        fontweight="bold",
        pad=15
    )

    fig.tight_layout()
    out_path = os.path.join(CHARTS_DIR, "02_heatmap.png")
    plt.savefig(out_path)
    plt.close()
    print(f"Saved: {out_path}")


def plot_lead_time_vs_shortage(df_summary: pd.DataFrame):
    """
    3. Scatter / Bubble Plot: Supplier Lead Time vs Shortage Value.
       Bubble size corresponds to number of affected finished products.
    """
    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

    x = df_summary["lead_time_days"]
    y = df_summary["total_shortage_value"] / 1000.0  # in $k
    sizes = np.maximum(40, df_summary["affected_products"] * 80)

    scatter = ax.scatter(
        x,
        y,
        s=sizes,
        c=df_summary["total_sri"] / 1000.0,
        cmap="viridis",
        alpha=0.75,
        edgecolors="#222222",
        linewidth=1.2
    )

    cbar = fig.colorbar(scatter, ax=ax, fraction=0.035, pad=0.04)
    cbar.set_label("Total SRI ($k Risk Score)", fontsize=10, fontweight="bold")

    # Annotate top 5 shortage components
    top5 = df_summary.head(5)
    for _, row in top5.iterrows():
        ax.annotate(
            f"{row['component_id']}\n({row['supplier'][:12]})",
            (row["lead_time_days"], row["total_shortage_value"] / 1000.0),
            textcoords="offset points",
            xytext=(10, 5),
            ha="left",
            fontsize=8.5,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#888888", alpha=0.85)
        )

    ax.set_xlabel("Supplier Lead Time (Days)", fontsize=11, fontweight="bold", labelpad=8)
    ax.set_ylabel("Net Shortage Value ($k USD)", fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.4)

    plt.title(
        "Supply Chain Vulnerability: Lead Time vs Net Shortage Value\n(Bubble size = Number of affected finished drug products)",
        fontsize=12.5,
        fontweight="bold",
        pad=15
    )

    fig.tight_layout()
    out_path = os.path.join(CHARTS_DIR, "03_lead_time_vs_shortage.png")
    plt.savefig(out_path)
    plt.close()
    print(f"Saved: {out_path}")


def plot_supplier_exposure(df_detail: pd.DataFrame):
    """
    4. Supplier Exposure: Net Shortage Value aggregated by Supplier.
    """
    sup_agg = (
        df_detail.groupby("supplier")["shortage_value"]
        .sum()
        .sort_values(ascending=True)  # ascending for horizontal bar chart
        .rename("total_shortage_value")
        .reset_index()
    )

    fig, ax = plt.subplots(figsize=(10, 6), dpi=150)

    # Filter suppliers with positive shortage
    sup_short = sup_agg[sup_agg["total_shortage_value"] > 0].copy()

    y_pos = range(len(sup_short))
    vals = sup_short["total_shortage_value"] / 1000.0

    # Highlight top bottleneck supplier in dark orange, others in steel blue
    max_val = vals.max()
    colors = ["#d62728" if v == max_val else "#1f77b4" for v in vals]

    bars = ax.barh(y_pos, vals, color=colors, alpha=0.85, edgecolor="#333333", height=0.6)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(sup_short["supplier"], fontsize=10)
    ax.set_xlabel("Total Net Shortage Value ($k USD)", fontsize=11, fontweight="bold", labelpad=8)
    ax.set_ylabel("Supplier", fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.4, axis="x")

    # Annotate bar labels
    for bar in bars:
        w = bar.get_width()
        ax.text(
            w + (max_val * 0.015),
            bar.get_y() + bar.get_height() / 2.0,
            f"${w:,.1f}k",
            ha="left",
            va="center",
            fontsize=9,
            fontweight="bold",
            color="#222222"
        )

    ax.set_xlim(0, max_val * 1.18)

    plt.title(
        "Vendor Risk Profile: Cumulative Shortage Value Exposure by Supplier",
        fontsize=13,
        fontweight="bold",
        pad=15
    )

    fig.tight_layout()
    out_path = os.path.join(CHARTS_DIR, "04_supplier_exposure.png")
    plt.savefig(out_path)
    plt.close()
    print(f"Saved: {out_path}")


def generate_all_charts():
    os.makedirs(CHARTS_DIR, exist_ok=True)

    detail_path = os.path.join(OUT_DIR, "shortage_detail.csv")
    summary_path = os.path.join(OUT_DIR, "shortage_summary.csv")

    if not os.path.exists(detail_path) or not os.path.exists(summary_path):
        from src.pipeline import run_pipeline
        run_pipeline()

    df_detail = pd.read_csv(detail_path)
    df_summary = pd.read_csv(summary_path)

    plot_pareto(df_summary)
    plot_heatmap(df_detail)
    plot_lead_time_vs_shortage(df_summary)
    plot_supplier_exposure(df_detail)
    print("All 4 MRP charts successfully generated.")


if __name__ == "__main__":
    generate_all_charts()
