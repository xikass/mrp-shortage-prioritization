"""
doe/anova_analysis.py
Performs Ordinary Least Squares (OLS) regression and Analysis of Variance (ANOVA)
on the 2^3 factorial DoE design using pure numpy and scipy.stats (no statsmodels).
Outputs: doe/anova_results.json
"""

import os
import json
import numpy as np
import pandas as pd
from scipy.stats import f as f_dist

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOE_DIR = os.path.join(BASE_DIR, "doe")


def run_anova():
    data_path = os.path.join(DOE_DIR, "doe_data.csv")
    if not os.path.exists(data_path):
        from doe.generate_doe import generate_doe_data
        df_doe = generate_doe_data(seed=7)
    else:
        df_doe = pd.read_csv(data_path)

    xA = df_doe["coded_A_binder"].values.astype(float)
    xB = df_doe["coded_B_compression"].values.astype(float)
    xC = df_doe["coded_C_lubrication"].values.astype(float)
    y = df_doe["tablet_hardness_n"].values.astype(float)
    n = len(y)

    # Interaction terms
    xAB = xA * xB
    xAC = xA * xC
    xBC = xB * xC

    # Design matrix: Intercept, A, B, C, A*B, A*C, B*C
    terms = [
        ("Intercept", np.ones(n)),
        ("Binder (A)", xA),
        ("Compression Force (B)", xB),
        ("Lubrication Time (C)", xC),
        ("Binder * Compression (A*B)", xAB),
        ("Binder * Lubrication (A*C)", xAC),
        ("Compression * Lubrication (B*C)", xBC),
    ]

    X = np.column_stack([t[1] for t in terms])
    p_terms = X.shape[1] - 1  # 6 model terms excluding intercept

    # OLS estimation: beta = (X'X)^-1 X'y
    beta, residuals, rank, s = np.linalg.lstsq(X, y, rcond=None)
    y_pred = X @ beta
    resid = y - y_pred

    ss_total = float(np.sum((y - np.mean(y)) ** 2))
    ss_resid = float(np.sum(resid ** 2))
    ss_model = ss_total - ss_resid

    df_total = n - 1
    df_resid = n - p_terms - 1
    df_model = p_terms

    ms_resid = ss_resid / df_resid if df_resid > 0 else 1.0
    ms_model = ss_model / df_model

    f_model = ms_model / ms_resid
    p_model = float(f_dist.sf(f_model, df_model, df_resid))

    r2 = ss_model / ss_total
    adj_r2 = 1.0 - (1.0 - r2) * (df_total / df_resid)

    # Individual term ANOVA (Sequential / Type I SS for orthogonal design)
    anova_table = []
    significant_effects = []

    for i in range(1, len(terms)):
        name = terms[i][0]
        col = X[:, i]
        # For orthogonal columns: SS_i = (col' y)^2 / (col' col)
        ss_i = float((col @ y) ** 2 / (col @ col))
        df_i = 1
        ms_i = ss_i / df_i
        f_i = float(ms_i / ms_resid)
        p_i = float(f_dist.sf(f_i, df_i, df_resid))
        coeff = float(beta[i])

        is_sig = bool(p_i < 0.05)
        if is_sig:
            significant_effects.append(name)

        anova_table.append({
            "term": name,
            "coefficient": round(coeff, 3),
            "effect_size": round(coeff * 2.0, 3),
            "df": df_i,
            "sum_of_squares": round(ss_i, 3),
            "mean_square": round(ms_i, 3),
            "f_statistic": round(f_i, 3),
            "p_value": round(p_i, 6),
            "significant_at_005": is_sig
        })

    results = {
        "model_summary": {
            "n_runs": n,
            "r_squared": round(r2, 4),
            "adjusted_r_squared": round(adj_r2, 4),
            "f_statistic": round(f_model, 3),
            "p_value": round(p_model, 6),
            "residual_standard_error": round(float(np.sqrt(ms_resid)), 3)
        },
        "coefficients": {
            terms[i][0]: round(float(beta[i]), 3) for i in range(len(terms))
        },
        "anova_table": anova_table,
        "significant_effects": significant_effects
    }

    out_json = os.path.join(DOE_DIR, "anova_results.json")
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)

    print("ANOVA Analysis Completed.")
    print(f"R² = {results['model_summary']['r_squared']}, Adj R² = {results['model_summary']['adjusted_r_squared']}")
    print(f"Significant Effects (p < 0.05): {significant_effects}")
    return results


if __name__ == "__main__":
    run_anova()
