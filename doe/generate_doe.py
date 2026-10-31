"""
doe/generate_doe.py
Generates a 2^3 full factorial design with 3 center points (11 runs total)
investigating the effects of Binder %, Compression Force, and Lubrication Time
on Tablet Hardness (Breaking Force in Newtons).
Seed = 7 for deterministic reproducibility.
Outputs: doe/doe_data.csv
"""

import os
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOE_DIR = os.path.join(BASE_DIR, "doe")


def generate_doe_data(seed: int = 7):
    np.random.seed(seed)
    os.makedirs(DOE_DIR, exist_ok=True)

    # 2^3 Factorial design matrix (coded -1, +1)
    coded_factorial = [
        [-1, -1, -1],
        [ 1, -1, -1],
        [-1,  1, -1],
        [ 1,  1, -1],
        [-1, -1,  1],
        [ 1, -1,  1],
        [-1,  1,  1],
        [ 1,  1,  1]
    ]
    # 3 replicated center points (coded 0, 0, 0)
    coded_center = [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0]
    ]

    all_coded = np.array(coded_factorial + coded_center, dtype=float)
    run_order = list(range(1, len(all_coded) + 1))

    # Natural factor scales:
    # A - Binder concentration (% w/w): Low=2.0%, Center=4.0%, High=6.0%
    # B - Compression Force (kN):       Low=10.0 kN, Center=17.5 kN, High=25.0 kN
    # C - Lubrication Time (min):       Low=2.0 min, Center=6.0 min, High=10.0 min
    binder = 4.0 + all_coded[:, 0] * 2.0
    compression = 17.5 + all_coded[:, 1] * 7.5
    lubrication = 6.0 + all_coded[:, 2] * 4.0

    xA = all_coded[:, 0]
    xB = all_coded[:, 1]
    xC = all_coded[:, 2]
    xAB = xA * xB
    xAC = xA * xC
    xBC = xB * xC

    # Response: Tablet Hardness (N)
    # Underlying response model with noise
    noise = np.random.normal(0.0, 1.2, size=len(all_coded))
    hardness = (
        85.0
        + 14.0 * xA
        + 20.0 * xB
        - 7.0 * xC
        + 9.0 * xAB
        - 1.5 * xAC
        - 1.0 * xBC
        + noise
    )

    df_doe = pd.DataFrame({
        "run_id": run_order,
        "run_type": ["Factorial"] * 8 + ["CenterPoint"] * 3,
        "coded_A_binder": all_coded[:, 0].astype(int),
        "coded_B_compression": all_coded[:, 1].astype(int),
        "coded_C_lubrication": all_coded[:, 2].astype(int),
        "binder_pct": np.round(binder, 1),
        "compression_force_kn": np.round(compression, 1),
        "lubrication_time_min": np.round(lubrication, 1),
        "tablet_hardness_n": np.round(hardness, 2)
    })

    out_csv = os.path.join(DOE_DIR, "doe_data.csv")
    df_doe.to_csv(out_csv, index=False)
    print(f"Generated DoE dataset (11 runs) -> {out_csv}")
    return df_doe


if __name__ == "__main__":
    generate_doe_data(seed=7)
