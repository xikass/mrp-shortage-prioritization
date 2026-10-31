"""
analysis.py
Main entry point to execute the MRP shortage prioritization pipeline and display headline findings.
"""

from src.pipeline import run_pipeline


def main():
    print("=" * 70)
    print("MRP SHORTAGE PRIORITIZATION & SHORTAGE RISK INDEX (SRI) ANALYSIS")
    print("=" * 70)

    results = run_pipeline()

    print("\nHEADLINE METRICS:")
    print(f"  - Total Net Shortage Value:   ${results['total_shortage_value']:,.2f}")
    print(f"  - Affected Components:         {results['short_components_count']} of 120 components")
    print(f"  - Top-20% Concentration:       {results['top_20pct_share_of_value']}% of value in top {results['top_20pct_components_count']} components")
    print(f"  - Primary Supplier Bottleneck: {results['worst_supplier']['supplier_name']} (${results['worst_supplier']['shortage_value']:,.2f} / {results['worst_supplier']['share_of_total_pct']}%)")
    print(f"  - Median Days of Inventory Cover: {results['median_days_of_cover']} days")

    print("\nTOP 5 SHORTAGE RISK INDEX (SRI) PRIORITIES:")
    for i, item in enumerate(results["sri_top10"][:5], 1):
        print(f"  {i}. {item['component_id']} ({item['component_name']}) | Supplier: {item['supplier']} | SRI: {item['sri']:,.2f} | Shortage: ${item['shortage_value']:,.2f}")

    print("\nSENSITIVITY ROBUSTNESS:")
    print(f"  - {results['sensitivity_metrics']['summary']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
