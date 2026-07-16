"""
Portfolio analytics example.

Demonstrates the portfolio-level analytics features including:
- Portfolio-level P&L tracking
- Time-based performance analysis (daily/weekly/monthly)
- Performance metrics (Sharpe, Sortino, Calmar, etc.)
- Trade history analytics
- Win rate and profit factor calculations

Usage
-----
    python examples/portfolio_analytics.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import polyalpha

def main():
    """Run portfolio analytics demonstration."""
    
    # Initialize client with paper trading
    client = polyalpha.Client(balance=1000.0, log_level="INFO")
    
    print("=" * 80)
    print("  PORTFOLIO ANALYTICS DEMONSTRATION")
    print("=" * 80)
    print()
    
    # Simulate some trades for demonstration
    print("Simulating sample trades...")
    print()
    
    # Get a market to trade
    try:
        market = client.markets.latest("BTC", "5m")
        print(f"Trading market: {market.question}")
        print(f"  UP price: {market.up_price:.4f}")
        print(f"  DOWN price: {market.down_price:.4f}")
        print()
    except Exception as e:
        print(f"Could not fetch market: {e}")
        print("Using mock data for demonstration...")
        print()
        
        # Create some mock resolved positions for demonstration
        from datetime import datetime, timedelta, timezone
        from polyalpha.trading.paper import PaperPosition
        
        # Mock resolved positions
        mock_positions = [
            PaperPosition(
                market_id="mock1",
                slug="BTC-5m-UP",
                question="Will BTC go up?",
                side="UP",
                shares=10.0,
                avg_price=0.50,
                current_price=1.0,
                resolved=True,
                outcome="WON",
                order_ids=["order1"],
            ),
            PaperPosition(
                market_id="mock2",
                slug="ETH-5m-DOWN",
                question="Will ETH go down?",
                side="DOWN",
                shares=15.0,
                avg_price=0.45,
                current_price=0.0,
                resolved=True,
                outcome="WON",
                order_ids=["order2"],
            ),
            PaperPosition(
                market_id="mock3",
                slug="SOL-5m-UP",
                question="Will SOL go up?",
                side="UP",
                shares=8.0,
                avg_price=0.60,
                current_price=0.0,
                resolved=True,
                outcome="LOST",
                order_ids=["order3"],
            ),
        ]
        
        # Add mock positions to engine
        for pos in mock_positions:
            key = f"{pos.market_id}:{pos.side}"
            client.paper._positions[key] = pos
        
        # Update balance to reflect mock trades
        client.paper._balance = 1025.0
    
    # Access portfolio analytics
    analytics = client.paper.portfolio_analytics
    
    # 1. Portfolio-level P&L tracking
    print("1. Portfolio-level P&L Tracking")
    print("-" * 40)
    portfolio_pnl = analytics.get_portfolio_pnl()
    print(f"Total P&L:           ${portfolio_pnl.total_pnl:>10.2f} ({portfolio_pnl.total_pnl_pct:>6.2f}%)")
    print(f"Realized P&L:        ${portfolio_pnl.realized_pnl:>10.2f}")
    print(f"Unrealized P&L:      ${portfolio_pnl.unrealized_pnl:>10.2f}")
    print(f"Current Balance:     ${portfolio_pnl.current_balance:>10.2f}")
    print(f"Peak Balance:        ${portfolio_pnl.peak_balance:>10.2f}")
    print(f"Max Drawdown:        ${portfolio_pnl.max_drawdown:>10.2f} ({portfolio_pnl.max_drawdown_pct:>6.2f}%)")
    print(f"Total Fees:          ${portfolio_pnl.total_fees:>10.2f}")
    print(f"Net Fees:            ${portfolio_pnl.net_fees:>10.2f}")
    print()
    
    # 2. Time-based performance analysis
    print("2. Time-based Performance Analysis")
    print("-" * 40)
    
    daily_perf = analytics.get_daily_performance()
    print(f"Daily Performance:")
    print(f"  Best Day:            {daily_perf.best_period[0]:>12} ${daily_perf.best_period[1]:>8.2f}")
    print(f"  Worst Day:           {daily_perf.worst_period[0]:>12} ${daily_perf.worst_period[1]:>8.2f}")
    print(f"  Daily Win Rate:      {daily_perf.win_rate:>10.2%}")
    print()
    
    weekly_perf = analytics.get_weekly_performance()
    print(f"Weekly Performance:")
    print(f"  Best Week:           {weekly_perf.best_period[0]:>12} ${weekly_perf.best_period[1]:>8.2f}")
    print(f"  Worst Week:          {weekly_perf.worst_period[0]:>12} ${weekly_perf.worst_period[1]:>8.2f}")
    print(f"  Weekly Win Rate:     {weekly_perf.win_rate:>10.2%}")
    print()
    
    monthly_perf = analytics.get_monthly_performance()
    print(f"Monthly Performance:")
    print(f"  Best Month:          {monthly_perf.best_period[0]:>12} ${monthly_perf.best_period[1]:>8.2f}")
    print(f"  Worst Month:         {monthly_perf.worst_period[0]:>12} ${monthly_perf.worst_period[1]:>8.2f}")
    print(f"  Monthly Win Rate:    {monthly_perf.win_rate:>10.2%}")
    print()
    
    # 3. Performance metrics
    print("3. Performance Metrics")
    print("-" * 40)
    perf_metrics = analytics.get_performance_metrics()
    print(f"Sharpe Ratio:        {perf_metrics.sharpe_ratio:>10.4f}")
    print(f"Sortino Ratio:       {perf_metrics.sortino_ratio:>10.4f}")
    print(f"Calmar Ratio:        {perf_metrics.calmar_ratio:>10.4f}")
    print(f"Omega Ratio:         {perf_metrics.omega_ratio:>10.4f}")
    print(f"Expectancy:         {perf_metrics.expectancy:>10.6f}")
    print(f"Kelly Fraction:      {perf_metrics.kelly_fraction:>10.4f}")
    print(f"Skew:               {perf_metrics.skew:>10.4f}")
    print(f"Kurtosis:           {perf_metrics.kurtosis:>10.4f}")
    print(f"VaR (95%):           {perf_metrics.var_95:>10.6f}")
    print(f"VaR (99%):           {perf_metrics.var_99:>10.6f}")
    print(f"CVaR (95%):          {perf_metrics.cvar_95:>10.6f}")
    print(f"CVaR (99%):          {perf_metrics.cvar_99:>10.6f}")
    print()
    
    # 4. Trade history analytics
    print("4. Trade History Analytics")
    print("-" * 40)
    trade_summary = analytics.get_trade_history_summary()
    print(f"Total Trades:        {trade_summary.total_trades:>10}")
    print(f"Winning Trades:      {trade_summary.winning_trades:>10}")
    print(f"Losing Trades:       {trade_summary.losing_trades:>10}")
    print(f"Win Rate:            {trade_summary.win_rate:>10.2%}")
    print(f"Profit Factor:       {trade_summary.profit_factor:>10.2f}")
    print(f"Avg Win:             ${trade_summary.avg_win:>10.2f}")
    print(f"Avg Loss:            ${trade_summary.avg_loss:>10.2f}")
    print(f"Largest Win:         ${trade_summary.largest_win:>10.2f}")
    print(f"Largest Loss:        ${trade_summary.largest_loss:>10.2f}")
    print(f"Avg Holding Time:    {trade_summary.avg_holding_time:>10.1f}s")
    print()
    
    # 5. Hourly and weekday performance
    print("5. Hourly and Weekday Performance")
    print("-" * 40)
    hourly_perf = analytics.get_hourly_performance()
    if hourly_perf:
        print("P&L by Hour (UTC):")
        for hour in sorted(hourly_perf.keys()):
            print(f"  Hour {hour:02d}: ${hourly_perf[hour]:>8.2f}")
    print()
    
    weekday_perf = analytics.get_weekday_performance()
    if weekday_perf:
        print("P&L by Weekday:")
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for day_idx in sorted(weekday_perf.keys()):
            print(f"  {days[day_idx]}: ${weekday_perf[day_idx]:>8.2f}")
    print()
    
    # 6. Comprehensive summary report
    print("6. Comprehensive Summary Report")
    print("-" * 40)
    analytics.print_summary()
    
    print()
    print("Portfolio analytics demonstration complete!")
    print()
    print("Key Features Demonstrated:")
    print("  ✓ Portfolio-level P&L tracking with realized/unrealized breakdown")
    print("  ✓ Time-based performance analysis (daily/weekly/monthly)")
    print("  ✓ Advanced performance metrics (Sharpe, Sortino, Calmar, etc.)")
    print("  ✓ Trade history analytics with win rate and profit factor")
    print("  ✓ Hourly and weekday performance breakdown")
    print("  ✓ Comprehensive summary report generation")

if __name__ == "__main__":
    main()
