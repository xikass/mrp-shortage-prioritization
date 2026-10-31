-- sql/pareto.sql
-- Pareto (ABC) Analysis of Net Shortage Value across Components
-- Calculates cumulative shortage value, cumulative percentage share, and Pareto ranking.

WITH clean_lots AS (
    SELECT lot_id, component_id, qty_on_hand
    FROM inventory_lots
    WHERE status = 'RELEASED'
      AND qty_on_hand IS NOT NULL
      AND qty_on_hand > 0
      AND date(expiry_date) > '2026-11-01'
    GROUP BY lot_id
),
stock_on_hand AS (
    SELECT component_id, SUM(qty_on_hand) AS on_hand_qty
    FROM clean_lots
    GROUP BY component_id
),
clean_pos AS (
    SELECT po_id, component_id, qty, expected_date
    FROM purchase_orders
    WHERE status = 'OPEN'
    GROUP BY po_id
),
clean_boms AS (
    SELECT b.product_id, b.component_id, b.qty_per_batch, b.scrap_pct
    FROM boms b
    JOIN components c ON b.component_id = c.component_id
),
exploded_orders AS (
    SELECT
        o.order_id,
        o.product_id,
        o.due_date,
        b.component_id,
        c.unit_cost,
        date(o.due_date, '-' || c.lead_time_days || ' days') AS need_date,
        ROUND(o.qty_batches * b.qty_per_batch * (1.0 + b.scrap_pct), 2) AS gross_qty
    FROM production_orders o
    JOIN clean_boms b ON o.product_id = b.product_id
    JOIN components c ON b.component_id = c.component_id
    WHERE o.status = 'OPEN'
),
cumulative_demand AS (
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
order_shortages AS (
    SELECT
        cd.component_id,
        cd.unit_cost,
        MAX(0.0, ROUND(
            MAX(0.0, cd.cum_gross_qty - (cd.on_hand_stock + cd.eligible_po_qty)) -
            MAX(0.0, COALESCE(cd.prev_cum_gross_qty, 0.0) - (cd.on_hand_stock + cd.eligible_po_qty)),
            2
        )) AS net_shortage_qty
    FROM cumulative_demand cd
),
component_shortages AS (
    SELECT
        c.component_id,
        c.name AS component_name,
        c.supplier,
        c.lead_time_days,
        c.unit_cost,
        ROUND(SUM(os.net_shortage_qty), 2) AS total_shortage_qty,
        ROUND(SUM(os.net_shortage_qty * c.unit_cost), 2) AS total_shortage_value
    FROM components c
    JOIN order_shortages os ON c.component_id = os.component_id
    GROUP BY c.component_id
    HAVING total_shortage_value > 0
),
total_val AS (
    SELECT SUM(total_shortage_value) AS grand_total_shortage
    FROM component_shortages
)
SELECT
    cs.component_id,
    cs.component_name,
    cs.supplier,
    cs.lead_time_days,
    cs.unit_cost,
    cs.total_shortage_qty,
    cs.total_shortage_value,
    ROUND(cs.total_shortage_value * 100.0 / tv.grand_total_shortage, 2) AS share_pct,
    ROUND(SUM(cs.total_shortage_value) OVER (ORDER BY cs.total_shortage_value DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cum_shortage_value,
    ROUND(SUM(cs.total_shortage_value) OVER (ORDER BY cs.total_shortage_value DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) * 100.0 / tv.grand_total_shortage, 2) AS cum_share_pct,
    ROW_NUMBER() OVER (ORDER BY cs.total_shortage_value DESC) AS pareto_rank,
    CASE
        WHEN (SUM(cs.total_shortage_value) OVER (ORDER BY cs.total_shortage_value DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) * 100.0 / tv.grand_total_shortage) <= 80.0 THEN 'A'
        WHEN (SUM(cs.total_shortage_value) OVER (ORDER BY cs.total_shortage_value DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) * 100.0 / tv.grand_total_shortage) <= 95.0 THEN 'B'
        ELSE 'C'
    END AS pareto_class
FROM component_shortages cs
CROSS JOIN total_val tv
ORDER BY cs.total_shortage_value DESC;
