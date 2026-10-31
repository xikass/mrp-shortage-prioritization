"""
Synthetic data generator for MRP Shortage Prioritization Case Study.
Seed = 42 for full reproducibility.
Generates SQLite database data/mrp.db and matching CSV files in data/.
Includes deliberate dirty data injection for pipeline auditing.
"""

import os
import sqlite3
import datetime
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "mrp.db")

SECTORS = ["COSMETICS", "HUMAN_PHARMA", "VETERINARY", "FOOD_SUPPLEMENT"]

SUPPLIERS = [
    "Apex BioChem",
    "Nordic Excipients",
    "Solvanta Pharma",
    "Vitasource Ingredients",
    "Boreal Botanicals",
    "Zenith Chemical",
    "Aegis Polymers",
    "Crestview Labs",
    "Helios Fine Chemicals",
    "Kestrel Supply",
    "Oceanic Extracts",
    "Valence Reagents",
]


def generate_all_data(seed: int = 42):
    np.random.seed(seed)
    os.makedirs(DATA_DIR, exist_ok=True)
    base_date = datetime.date(2026, 11, 1)

    # -------------------------------------------------------------
    # 1. PRODUCTS: 40 rows
    # -------------------------------------------------------------
    products = []
    abc_distribution = (
        ["A"] * 8 + ["B"] * 14 + ["C"] * 18
    )  # 20% A, 35% B, 45% C
    np.random.shuffle(abc_distribution)

    product_names = {
        "COSMETICS": [
            "Hydra-Calm Gel 50ml",
            "Anti-Age Night Serum 30ml",
            "Barrier Repair Cream 100ml",
            "Clarifying Facial Toner 200ml",
            "SunShield SPF50 Spray 150ml",
            "Revitalizing Eye Balm 15ml",
            "Peptide Firming Elixir 45ml",
            "Gentle Foaming Cleanser 150ml",
            "Lipid Restore Lotion 250ml",
            "Brightening C20 Boost 30ml",
        ],
        "HUMAN_PHARMA": [
            "Amoxicillin 500mg Caps",
            "Metformin XR 1000mg Tabs",
            "Atorvastatin 20mg Tabs",
            "Omeprazole DR 40mg Caps",
            "Paracetamol 500mg Tabs",
            "Ciprofloxacin 500mg Tabs",
            "Ibuprofen 400mg Film-Tabs",
            "Levothyroxine 100mcg Tabs",
            "Losartan K 50mg Tabs",
            "Azithromycin 250mg Caps",
        ],
        "VETERINARY": [
            "Vet-Amox Clav 250mg Tabs",
            "Canine Joint Mobility Chew",
            "Equine Electrolyte Paste 60ml",
            "Feline Renal Support Solution",
            "Bovine Multivitamin Inj 100ml",
            "Otic Flush Suspension 120ml",
            "Canine NSAID Chew 50mg",
            "Anthelmintic Drench 500ml",
            "Dermal Wound Spray 100ml",
            "Probiotic Powder 100g",
        ],
        "FOOD_SUPPLEMENT": [
            "Omega-3 Super EPA/DHA 1000mg",
            "Magnesium Glycinate 400mg",
            "Vitamin D3+K2 Drops 30ml",
            "Liposomal Vitamin C 1000mg",
            "Zinc Picolinate 50mg Caps",
            "Ashwagandha Root Ext 600mg",
            "CoQ10 Ubiquinol 200mg Softgel",
            "Collagen Peptides Powder 300g",
            "Probiotics 50 Billion CFU",
            "Iron Bisglycinate Complex 28mg",
        ],
    }

    prod_idx = 1
    for sector in SECTORS:
        names = product_names[sector]
        for name in names:
            pid = f"PRD-{prod_idx:03d}"
            abc = abc_distribution[prod_idx - 1]
            batch_size = int(
                np.random.choice([1000, 2000, 2500, 5000, 10000, 20000])
            )
            monthly_demand = int(batch_size * np.random.uniform(1.5, 4.0))
            products.append(
                {
                    "product_id": pid,
                    "name": name,
                    "sector": sector,
                    "abc_class": abc,
                    "batch_size": batch_size,
                    "monthly_demand": monthly_demand,
                }
            )
            prod_idx += 1

    df_products = pd.DataFrame(products)

    # -------------------------------------------------------------
    # 2. COMPONENTS: 120 rows
    # -------------------------------------------------------------
    comp_prefixes = [
        ("API", "Active Ingredient"),
        ("EXC", "Functional Excipient"),
        ("SOL", "Solvent / Vehicle"),
        ("PRV", "Preservative / Buffer"),
        ("PKG", "Primary Packaging"),
        ("SEC", "Secondary Packaging"),
    ]

    components = []
    for cidx in range(1, 121):
        cid = f"CMP-{cidx:03d}"
        prefix, cat = comp_prefixes[(cidx - 1) % len(comp_prefixes)]
        supplier = SUPPLIERS[(cidx - 1) % len(SUPPLIERS)]
        lead_time = int(np.random.choice([7, 14, 21, 30, 45, 60, 75, 90]))
        # Unit cost distribution: some cheap excipients, some costly APIs
        if prefix == "API":
            unit_cost = round(float(np.random.uniform(80.0, 450.0)), 2)
            moq = int(np.random.choice([10, 25, 50, 100]))
        elif prefix in ["EXC", "SOL"]:
            unit_cost = round(float(np.random.uniform(5.0, 40.0)), 2)
            moq = int(np.random.choice([50, 100, 250, 500]))
        elif prefix == "PRV":
            unit_cost = round(float(np.random.uniform(15.0, 95.0)), 2)
            moq = int(np.random.choice([25, 50, 100]))
        else:  # PKG, SEC
            unit_cost = round(float(np.random.uniform(0.80, 8.50)), 2)
            moq = int(np.random.choice([500, 1000, 2500, 5000]))

        name = f"{cat} Grade-{cidx:02d} ({prefix})"
        components.append(
            {
                "component_id": cid,
                "name": name,
                "supplier": supplier,
                "lead_time_days": lead_time,
                "unit_cost": unit_cost,
                "moq": moq,
            }
        )

    df_components = pd.DataFrame(components)

    # -------------------------------------------------------------
    # 3. BOMS: 2-4 components per product + 3 orphan BOM rows
    # -------------------------------------------------------------
    boms = []
    all_cids = df_components["component_id"].tolist()

    for p in products:
        pid = p["product_id"]
        # pick 3 to 4 distinct components
        n_comps = np.random.choice([3, 4])
        selected_comps = np.random.choice(all_cids, size=n_comps, replace=False)
        for cid in selected_comps:
            qty_per_batch = round(float(np.random.uniform(5.0, 120.0)), 2)
            scrap_pct = round(float(np.random.uniform(0.005, 0.030)), 3)
            boms.append(
                {
                    "product_id": pid,
                    "component_id": cid,
                    "qty_per_batch": qty_per_batch,
                    "scrap_pct": scrap_pct,
                }
            )

    # Inject 3 orphan BOM rows (component_id not in components)
    boms.append(
        {
            "product_id": "PRD-002",
            "component_id": "CMP-991",
            "qty_per_batch": 12.5,
            "scrap_pct": 0.02,
        }
    )
    boms.append(
        {
            "product_id": "PRD-015",
            "component_id": "CMP-992",
            "qty_per_batch": 35.0,
            "scrap_pct": 0.015,
        }
    )
    boms.append(
        {
            "product_id": "PRD-028",
            "component_id": "CMP-993",
            "qty_per_batch": 8.0,
            "scrap_pct": 0.01,
        }
    )

    df_boms = pd.DataFrame(boms)

    # -------------------------------------------------------------
    # 4. INVENTORY LOTS: ~300 rows
    # -------------------------------------------------------------
    # Inject:
    # - 3 duplicate lots
    # - 4 null-qty lots
    # - 5 negative-qty lots
    # - 8 expired lots still marked RELEASED
    lots = []
    lot_counter = 1

    # Base valid lots
    for i in range(285):
        lid = f"LOT-{lot_counter:04d}"
        lot_counter += 1
        cid = np.random.choice(all_cids)
        qty = round(float(np.random.uniform(20.0, 800.0)), 2)
        rec_offset = int(np.random.randint(-180, -10))
        rec_date = base_date + datetime.timedelta(days=rec_offset)

        # Normal status
        rand_st = np.random.random()
        if rand_st < 0.80:
            status = "RELEASED"
            exp_offset = int(np.random.randint(60, 540))
        elif rand_st < 0.92:
            status = "QUARANTINE"
            exp_offset = int(np.random.randint(30, 360))
        else:
            status = "EXPIRED"
            exp_offset = int(np.random.randint(-120, -5))

        exp_date = base_date + datetime.timedelta(days=exp_offset)
        lots.append(
            {
                "lot_id": lid,
                "component_id": cid,
                "qty_on_hand": qty,
                "expiry_date": exp_date.isoformat(),
                "status": status,
                "received_date": rec_date.isoformat(),
            }
        )

    # Injected 5 negative-qty lots
    for _ in range(5):
        lid = f"LOT-{lot_counter:04d}"
        lot_counter += 1
        cid = np.random.choice(all_cids)
        qty = round(float(np.random.uniform(-150.0, -10.0)), 2)
        lots.append(
            {
                "lot_id": lid,
                "component_id": cid,
                "qty_on_hand": qty,
                "expiry_date": (
                    base_date + datetime.timedelta(days=180)
                ).isoformat(),
                "status": "RELEASED",
                "received_date": (
                    base_date - datetime.timedelta(days=30)
                ).isoformat(),
            }
        )

    # Injected 4 null qty lots
    for _ in range(4):
        lid = f"LOT-{lot_counter:04d}"
        lot_counter += 1
        cid = np.random.choice(all_cids)
        lots.append(
            {
                "lot_id": lid,
                "component_id": cid,
                "qty_on_hand": None,
                "expiry_date": (
                    base_date + datetime.timedelta(days=120)
                ).isoformat(),
                "status": "RELEASED",
                "received_date": (
                    base_date - datetime.timedelta(days=45)
                ).isoformat(),
            }
        )

    # Injected 8 expired lots still marked RELEASED
    for i in range(8):
        lid = f"LOT-{lot_counter:04d}"
        lot_counter += 1
        cid = np.random.choice(all_cids)
        qty = round(float(np.random.uniform(50.0, 300.0)), 2)
        exp_past = base_date - datetime.timedelta(days=int(np.random.randint(10, 90)))
        lots.append(
            {
                "lot_id": lid,
                "component_id": cid,
                "qty_on_hand": qty,
                "expiry_date": exp_past.isoformat(),
                "status": "RELEASED",  # Dirty: expired but still marked RELEASED
                "received_date": (
                    exp_past - datetime.timedelta(days=365)
                ).isoformat(),
            }
        )

    # Injected 3 duplicate lots (copy existing lots)
    for dup_idx in [10, 25, 40]:
        dup_row = dict(lots[dup_idx])
        lots.append(dup_row)

    df_lots = pd.DataFrame(lots)

    # -------------------------------------------------------------
    # 5. PURCHASE ORDERS: ~50 open rows + 2 duplicates
    # -------------------------------------------------------------
    pos = []
    po_counter = 1
    for i in range(50):
        poid = f"PO-{po_counter:04d}"
        po_counter += 1
        cid = np.random.choice(all_cids)
        qty = round(float(np.random.uniform(50.0, 1000.0)), 2)
        # expected date within next 10 to 60 days
        exp_days = int(np.random.randint(10, 65))
        exp_date = base_date + datetime.timedelta(days=exp_days)
        pos.append(
            {
                "po_id": poid,
                "component_id": cid,
                "qty": qty,
                "expected_date": exp_date.isoformat(),
                "status": "OPEN",
            }
        )

    # Inject 2 duplicate POs
    pos.append(dict(pos[5]))
    pos.append(dict(pos[15]))

    df_pos = pd.DataFrame(pos)

    # -------------------------------------------------------------
    # 6. PRODUCTION ORDERS: ~60 open rows
    # -------------------------------------------------------------
    all_pids = df_products["product_id"].tolist()
    orders = []
    for oidx in range(1, 61):
        oid = f"ORD-{oidx:04d}"
        pid = np.random.choice(all_pids)
        qty_batches = int(np.random.choice([1, 2, 3, 4, 5]))
        # Due date spread across next 10 to 90 days
        due_days = int(np.random.randint(10, 91))
        due_date = base_date + datetime.timedelta(days=due_days)
        orders.append(
            {
                "order_id": oid,
                "product_id": pid,
                "qty_batches": qty_batches,
                "due_date": due_date.isoformat(),
                "status": "OPEN",
            }
        )

    df_orders = pd.DataFrame(orders)

    # -------------------------------------------------------------
    # Save CSVs and SQLite Database
    # -------------------------------------------------------------
    df_products.to_csv(os.path.join(DATA_DIR, "products.csv"), index=False)
    df_components.to_csv(os.path.join(DATA_DIR, "components.csv"), index=False)
    df_boms.to_csv(os.path.join(DATA_DIR, "boms.csv"), index=False)
    df_lots.to_csv(os.path.join(DATA_DIR, "inventory_lots.csv"), index=False)
    df_pos.to_csv(os.path.join(DATA_DIR, "purchase_orders.csv"), index=False)
    df_orders.to_csv(os.path.join(DATA_DIR, "production_orders.csv"), index=False)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    df_products.to_sql("products", conn, index=False)
    df_components.to_sql("components", conn, index=False)
    df_boms.to_sql("boms", conn, index=False)
    df_lots.to_sql("inventory_lots", conn, index=False)
    df_pos.to_sql("purchase_orders", conn, index=False)
    df_orders.to_sql("production_orders", conn, index=False)
    conn.close()

    print(f"Data generated successfully at seed={seed}.")
    print(f"Database: {DB_PATH}")
    print(f"Products: {len(df_products)} rows")
    print(f"Components: {len(df_components)} rows")
    print(f"BOMs: {len(df_boms)} rows (includes 3 orphans)")
    print(
        f"Inventory Lots: {len(df_lots)} rows (includes duplicates, nulls, negative, expired-released)"
    )
    print(f"Purchase Orders: {len(df_pos)} rows (includes 2 duplicates)")
    print(f"Production Orders: {len(df_orders)} rows")


if __name__ == "__main__":
    generate_all_data(seed=42)
