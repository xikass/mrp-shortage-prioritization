"""
doe/plots.py
Generates DoE visualization charts using matplotlib:
  - charts/05_doe_main_effects.png: Main effects plot for Binder, Compression, Lubrication
  - charts/06_doe_interaction.png: Binder x Compression interaction plot and response surface contour
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARTS_DIR = os.path.join(BASE_DIR, "charts")
DOE_DIR = os.path.join(BASE_DIR, "doe")

plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Helvetica", "Arial"]


def plot_main_effects(df_doe: pd.DataFrame):
    """
    Main effects plot: displays mean tablet hardness across factor levels (-1, 0, +1).
    """
    factors = [
        ("coded_A_binder", "Binder Concentration (% w/w)", ["2.0% (-1)", "4.0% (0)", "6.0% (+1)"]),
        ("coded_B_compression", "Compression Force (kN)", ["10.0 (-1)", "17.5 (0)", "25.0 (+1)"]),
        ("coded_C_lubrication", "Lubrication Time (min)", ["2.0 (-1)", "6.0 (0)", "10.0 (+1)"])
    ]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), dpi=150, sharey=True)
    overall_mean = df_doe["tablet_hardness_n"].mean()

    colors = ["#1f77b4", "#2ca02c", "#d62728"]

    for idx, (col, title, labels) in enumerate(factors):
        ax = axes[idx]
        means = df_doe.groupby(col)["tablet_hardness_n"].mean()
        levels = [-1, 0, 1]
        y_vals = [means.get(lvl, np.nan) for lvl in levels]

        ax.plot(levels, y_vals, marker="o", markersize=7, linewidth=2.2, color=colors[idx], label="Factor Mean")
        ax.axhline(overall_mean, color="#777777", linestyle="--", linewidth=1.2, label="Grand Mean")

        ax.set_xticks(levels)
        ax.set_xticklabels(labels, fontsize=9.5, fontweight="bold")
        ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
        ax.set_xlabel("Factor Level", fontsize=10, fontweight="bold")
        if idx == 0:
            ax.set_ylabel("Mean Tablet Hardness (N)", fontsize=11, fontweight="bold")
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.set_ylim(45, 135)

    axes[0].legend(loc="upper left", framealpha=0.9)
    plt.suptitle("DoE Main Effects Plot for Tablet Hardness (N = 11 runs)", fontsize=13, fontweight="bold", y=1.03)
    fig.tight_layout()

    out_path = os.path.join(CHARTS_DIR, "05_doe_main_effects.png")
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


def plot_interaction_and_contour(df_doe: pd.DataFrame, anova_results: dict):
    """
    Strongest interaction plot (Binder x Compression Force) and response surface contour.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5), dpi=150)

    # Left plot: Interaction plot of A * B
    # Filter factorial runs
    fact_df = df_doe[df_doe["run_type"] == "Factorial"].copy()

    # Compression low (-1) vs high (+1)
    comp_low = fact_df[fact_df["coded_B_compression"] == -1].groupby("coded_A_binder")["tablet_hardness_n"].mean()
    comp_high = fact_df[fact_df["coded_B_compression"] == 1].groupby("coded_A_binder")["tablet_hardness_n"].mean()

    ax1.plot([-1, 1], [comp_low[-1], comp_low[1]], marker="s", markersize=8, linewidth=2.4, color="#1f77b4", label="Compression Low (10 kN)")
    ax1.plot([-1, 1], [comp_high[-1], comp_high[1]], marker="^", markersize=8, linewidth=2.4, color="#d62728", label="Compression High (25 kN)")

    ax1.set_xticks([-1, 1])
    ax1.set_xticklabels(["Low (2.0%)", "High (6.0%)"], fontsize=10, fontweight="bold")
    ax1.set_xlabel("Binder Concentration (A)", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Tablet Hardness (N)", fontsize=11, fontweight="bold")
    ax1.set_title("Interaction Plot: Binder (A) × Compression (B)\n(Synergistic Hardness Enhancement)", fontsize=11, fontweight="bold", pad=10)
    ax1.legend(loc="upper left", framealpha=0.9)
    ax1.grid(True, linestyle="--", alpha=0.4)

    # Right plot: Contour plot of Binder vs Compression at Lubrication = Center (6 min)
    coeffs = anova_results["coefficients"]
    b0 = coeffs["Intercept"]
    bA = coeffs["Binder (A)"]
    bB = coeffs["Compression Force (B)"]
    bAB = coeffs["Binder * Compression (A*B)"]

    A_grid = np.linspace(-1, 1, 50)
    B_grid = np.linspace(-1, 1, 50)
    AA, BB = np.meshgrid(A_grid, B_grid)

    # Predicted Hardness at C = 0 (center point: 6 min)
    ZZ = b0 + bA * AA + bB * BB + bAB * (AA * BB)

    # Convert coordinates to natural units
    AA_natural = 4.0 + AA * 2.0
    BB_natural = 17.5 + BB * 7.5

    cs = ax2.contourf(AA_natural, BB_natural, ZZ, levels=12, cmap="viridis")
    cbar = fig.colorbar(cs, ax=ax2, fraction=0.046, pad=0.04)
    cbar.set_label("Predicted Hardness (N)", fontsize=10, fontweight="bold")

    lines = ax2.contour(AA_natural, BB_natural, ZZ, levels=12, colors="white", linewidths=0.7, alpha=0.6)
    ax2.clabel(lines, inline=True, fontsize=8, fmt="%1.0f N")

    # Plot experimental points
    ax2.scatter(fact_df["binder_pct"], fact_df["compression_force_kn"], color="red", edgecolors="white", s=50, zorder=5, label="Factorial Runs")
    ax2.scatter([4.0], [17.5], color="gold", edgecolors="black", s=80, marker="*", zorder=6, label="Center Points (3 reps)")

    ax2.set_xlabel("Binder Concentration (% w/w)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Compression Force (kN)", fontsize=11, fontweight="bold")
    ax2.set_title("Response Contour: Binder vs Compression\n(At Lubrication Time = 6.0 min)", fontsize=11, fontweight="bold", pad=10)
    ax2.legend(loc="upper left", framealpha=0.85, fontsize=8.5)

    fig.tight_layout()
    out_path = os.path.join(CHARTS_DIR, "06_doe_interaction.png")
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


def generate_all_doe_plots():
    os.makedirs(CHARTS_DIR, exist_ok=True)
    data_path = os.path.join(DOE_DIR, "doe_data.csv")
    json_path = os.path.join(DOE_DIR, "anova_results.json")

    if not os.path.exists(data_path):
        from doe.generate_doe import generate_doe_data
        generate_doe_data()

    if not os.path.exists(json_path):
        from doe.anova_analysis import run_anova
        run_anova()

    df_doe = pd.read_csv(data_path)
    with open(json_path, "r") as f:
        anova_results = json.load(f)

    plot_main_effects(df_doe)
    plot_interaction_and_contour(df_doe, anova_results)
    print("All DoE plots successfully generated.")


if __name__ == "__main__":
    generate_all_doe_plots()
