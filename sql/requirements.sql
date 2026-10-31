-- sql/requirements.sql
-- Time-phased MRP Gross and Net Requirements Explosion with Sequential Inventory Allocation
-- Uses CTEs and window functions to allocate on-hand released inventory and lead-time-eligible POs.

WITH clean_lots AS (
    -- Filter out negative, null, expired lots, and deduplicate by lot_id
    SELECT lot_id, component_id, qty_on_hand
    FROM inventory_lots
    WHERE status = 'RELEASED'
      AND qty_on_hand IS NOT NULL
      AND qty_on_hand > 0
      AND date(expiry_date) > '2026-11-01'
    GROUP BY lot_id
),
stock_on_hand AS (
    -- Usable warehouse stock per component
    SELECT component_id, SUM(qty_on_hand) AS on_hand_qty
    FROM clean_lots
    GROUP BY component_id
),
clean_pos AS (
    -- Deduplicate open purchase orders
    SELECT po_id, component_id, qty, expected_date
    FROM purchase_orders
    WHERE status = 'OPEN'
    GROUP BY po_id
),
clean_boms AS (
    -- Prune unmapped / orphan BOM components
    SELECT b.product_id, b.component_id, b.qty_per_batch, b.scrap_pct
    FROM boms b
    JOIN components c ON b.component_id = c.component_id
),
exploded_orders AS (
    -- Explode open production orders across BOM lines
    SELECT
        o.order_id,
        o.product_id,
        p.name AS product_name,
        p.sector,
        p.abc_class,
        o.due_date,
        CAST(julianday(o.due_date) - julianday('2026-11-01') AS INTEGER) AS days_to_due,
        b.component_id,
        c.name AS component_name,
        c.supplier,
        c.lead_time_days,
        c.unit_cost,
        date(o.due_date, '-' || c.lead_time_days || ' days') AS need_date,
        ROUND(o.qty_batches * b.qty_per_batch * (1.0 + b.scrap_pct), 2) AS gross_qty,
        CASE p.abc_class
            WHEN 'A' THEN 3.0
            WHEN 'B' THEN 2.0
            ELSE 1.0
        END AS priority_weight,
        ROUND(1.0 + MAX(0.0, (30.0 - CAST(julianday(o.due_date) - julianday('2026-11-01') AS REAL)) / 30.0), 3) AS urgency_factor
    FROM production_orders o
    JOIN products p ON o.product_id = p.product_id
    JOIN clean_boms b ON o.product_id = b.product_id
    JOIN components c ON b.component_id = c.component_id
    WHERE o.status = 'OPEN'
),
cumulative_demand AS (
    -- Calculate cumulative gross requirement per component and match against lead-time-aware supply
    SELECT
        e.*,
        COALESCE(s.on_hand_qty, 0.0) AS on_hand_stock,
        COALESCE((
            SELECT SUM(p.qty)
            FROM clean_pos p
            WHERE p.component_id = e.component_id
              AND date(p.expected_date) <= date(e.need_date)
        ), 0.0) AS eligible_po_qty,
        SUM(e.gross_qty) OVER (
            PARTITION BY e.component_id
            ORDER BY e.need_date, e.order_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cum_gross_qty,
        SUM(e.gross_qty) OVER (
            PARTITION BY e.component_id
            ORDER BY e.need_date, e.order_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS prev_cum_gross_qty
    FROM exploded_orders e
    LEFT JOIN stock_on_hand s ON e.component_id = s.component_id
),
allocated_requirements AS (
    -- Time-phased sequential allocation of available stock & POs
    SELECT
        cd.*,
        (cd.on_hand_stock + cd.eligible_po_qty) AS effective_supply,
        MAX(0.0, ROUND(
            MAX(0.0, cd.cum_gross_qty - (cd.on_hand_stock + cd.eligible_po_qty)) -
            MAX(0.0, COALESCE(cd.prev_cum_gross_qty, 0.0) - (cd.on_hand_stock + cd.eligible_po_qty)),
            2
        )) AS net_shortage_qty
    FROM cumulative_demand cd
)
SELECT
    order_id,
    product_id,
    product_name,
    sector,
    abc_class,
    due_date,
    days_to_due,
    component_id,
    component_name,
    supplier,
    lead_time_days,
    need_date,
    gross_qty,
    ROUND(gross_qty - net_shortage_qty, 2) AS allocated_supply,
    net_shortage_qty,
    net_shortage_qty AS shortage_qty,
    unit_cost,
    ROUND(net_shortage_qty * unit_cost, 2) AS shortage_value,
    priority_weight,
    urgency_factor,
    ROUND(net_shortage_qty * unit_cost * priority_weight * urgency_factor, 2) AS sri,
    ROW_NUMBER() OVER (ORDER BY (net_shortage_qty * unit_cost * priority_weight * urgency_factor) DESC) AS sri_rank
FROM allocated_requirements
ORDER BY sri DESC;
