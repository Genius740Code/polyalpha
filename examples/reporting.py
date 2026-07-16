"""
Reporting example.

Demonstrates the comprehensive reporting system including:
- Portfolio summary reports (HTML/JSON/CSV)
- Trade execution quality reports
- Risk exposure reports
- Tax reporting (cost basis, realized gains)
- Audit trail for compliance

Usage
-----
    python examples/reporting.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

def main():
    """Run reporting demonstration."""
    
    # Initialize client with paper trading
    client = polyalpha.Client(balance=1000.0, log_level="INFO")
    
    print("=" * 80)
    print("  REPORTING SYSTEM DEMONSTRATION")
    print("=" * 80)
    print()
    
    # Simulate some trades for demonstration
    print("Simulating sample trades for reporting...")
    print()
    
    try:
        # Get a market to trade
        market = client.markets.latest("BTC", "5m")
        print(f"Trading market: {market.question}")
        print(f"  UP price: {market.up_price:.4f}")
        print(f"  DOWN price: {market.down_price:.4f}")
        print()
        
        # Place some sample trades
        print("Placing sample trades...")
        order1 = client.paper.buy(market, side="UP", amount=50.0)
        print(f"  Order 1: {order1.id[:8]} - {order1.status} - ${order1.amount:.2f}")
        
        order2 = client.paper.buy(market, side="DOWN", amount=30.0)
        print(f"  Order 2: {order2.id[:8]} - {order2.status} - ${order2.amount:.2f}")
        print()
        
        # Simulate some resolution for tax reporting
        from datetime import datetime, timezone
        from polyalpha.trading.paper import PaperPosition
        
        # Create some resolved positions
        resolved_positions = [
            PaperPosition(
                market_id="resolved1",
                slug="ETH-5m-UP",
                question="Will ETH go up?",
                side="UP",
                shares=20.0,
                avg_price=0.40,
                current_price=1.0,
                resolved=True,
                outcome="WON",
                order_ids=["resolved_order1"],
            ),
            PaperPosition(
                market_id="resolved2",
                slug="SOL-5m-DOWN",
                question="Will SOL go down?",
                side="DOWN",
                shares=15.0,
                avg_price=0.55,
                current_price=0.0,
                resolved=True,
                outcome="LOST",
                order_ids=["resolved_order2"],
            ),
        ]
        
        for pos in resolved_positions:
            key = f"{pos.market_id}:{pos.side}"
            client.paper._positions[key] = pos
        
        # Add corresponding orders
        from polyalpha.trading.paper import PaperOrder
        client.paper._orders["resolved_order1"] = PaperOrder(
            id="resolved_order1",
            market_id="resolved1",
            slug="ETH-5m-UP",
            side="UP",
            price=0.40,
            amount=8.0,
            shares=20.0,
            fee=0.16,
            status="filled",
            is_limit=False,
            filled_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        client.paper._orders["resolved_order2"] = PaperOrder(
            id="resolved_order2",
            market_id="resolved2",
            slug="SOL-5m-DOWN",
            side="DOWN",
            price=0.55,
            amount=8.25,
            shares=15.0,
            fee=0.165,
            status="filled",
            is_limit=False,
            filled_at=datetime.now(timezone.utc) - timedelta(hours=3),
        )
        
    except Exception as e:
        print(f"Could not fetch market: {e}")
        print("Using existing data for demonstration...")
        print()
    
    # Access reporting engine
    reporting = client.paper.reporting
    
    # 1. Portfolio Summary Report
    print("1. Portfolio Summary Report")
    print("-" * 40)
    try:
        html_path = reporting.portfolio_summary("portfolio_summary.html", format="html")
        print(f"✓ HTML report generated: {html_path}")
        
        json_path = reporting.portfolio_summary("portfolio_summary.json", format="json")
        print(f"✓ JSON report generated: {json_path}")
        
        csv_path = reporting.portfolio_summary("portfolio_summary.csv", format="csv")
        print(f"✓ CSV report generated: {csv_path}")
    except Exception as e:
        print(f"✗ Error generating portfolio summary: {e}")
    print()
    
    # 2. Execution Quality Report
    print("2. Execution Quality Report")
    print("-" * 40)
    try:
        html_path = reporting.execution_quality("execution_quality.html", format="html")
        print(f"✓ HTML report generated: {html_path}")
        
        json_path = reporting.execution_quality("execution_quality.json", format="json")
        print(f"✓ JSON report generated: {json_path}")
        
        csv_path = reporting.execution_quality("execution_quality.csv", format="csv")
        print(f"✓ CSV report generated: {csv_path}")
    except Exception as e:
        print(f"✗ Error generating execution quality report: {e}")
    print()
    
    # 3. Risk Exposure Report
    print("3. Risk Exposure Report")
    print("-" * 40)
    try:
        html_path = reporting.risk_exposure("risk_exposure.html", format="html")
        print(f"✓ HTML report generated: {html_path}")
        
        json_path = reporting.risk_exposure("risk_exposure.json", format="json")
        print(f"✓ JSON report generated: {json_path}")
        
        csv_path = reporting.risk_exposure("risk_exposure.csv", format="csv")
        print(f"✓ CSV report generated: {csv_path}")
    except Exception as e:
        print(f"✗ Error generating risk exposure report: {e}")
    print()
    
    # 4. Tax Report
    print("4. Tax Report")
    print("-" * 40)
    try:
        csv_path = reporting.tax_report("tax_report.csv", format="csv")
        print(f"✓ CSV report generated: {csv_path}")
        
        json_path = reporting.tax_report("tax_report.json", format="json")
        print(f"✓ JSON report generated: {json_path}")
    except Exception as e:
        print(f"✗ Error generating tax report: {e}")
    print()
    
    # 5. Audit Trail
    print("5. Audit Trail")
    print("-" * 40)
    try:
        json_path = reporting.audit_trail("audit_trail.json", format="json")
        print(f"✓ JSON audit trail generated: {json_path}")
        
        csv_path = reporting.audit_trail("audit_trail.csv", format="csv")
        print(f"✓ CSV audit trail generated: {csv_path}")
    except Exception as e:
        print(f"✗ Error generating audit trail: {e}")
    print()
    
    print("=" * 80)
    print("  REPORTING DEMONSTRATION COMPLETE")
    print("=" * 80)
    print()
    print("Generated Reports:")
    print("  ✓ Portfolio Summary (HTML/JSON/CSV)")
    print("  ✓ Execution Quality (HTML/JSON/CSV)")
    print("  ✓ Risk Exposure (HTML/JSON/CSV)")
    print("  ✓ Tax Report (CSV/JSON)")
    print("  ✓ Audit Trail (JSON/CSV)")
    print()
    print("Key Features Demonstrated:")
    print("  ✓ Portfolio summary with comprehensive metrics")
    print("  ✓ Trade execution quality analysis")
    print("  ✓ Risk exposure and concentration analysis")
    print("  ✓ Tax reporting with cost basis and realized gains")
    print("  ✓ Audit trail for compliance")
    print("  ✓ Multiple output formats (HTML, JSON, CSV)")
    print()
    print("Open the HTML files in a browser to view interactive reports.")

if __name__ == "__main__":
    main()
