import csv
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Union
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone

if TYPE_CHECKING:
    from ..trading.paper_engine import PaperEngine
    from ..trading.real import RealTradingEngine

def generate_risk_exposure(engine: Union["PaperEngine", "RealTradingEngine"]) -> str:
    """
    Generate a Risk Exposure report for the current portfolio state.
    """
    positions = [p for p in engine._positions.values() if not getattr(p, "resolved", False)]
    total_deployed = sum(getattr(p, "cost_basis", 0.0) for p in positions)
    balance = getattr(engine, "_balance", 0.0)

    market_exposure = defaultdict(float)
    max_loss_exposure = 0.0

    for p in positions:
        cost_basis = getattr(p, "cost_basis", 0.0)
        market_id = getattr(p, "market_id", "unknown")
        market_exposure[market_id] += cost_basis
        
        # Stop loss logic (if set)
        stop_loss = getattr(p, "stop_loss", None)
        shares = getattr(p, "shares", 0.0)
        if stop_loss is not None:
            # max loss = cost_basis - (stop_loss * shares)
            guaranteed_return = shares * stop_loss
            loss = cost_basis - guaranteed_return
            max_loss_exposure += loss
        else:
            # If no stop loss, we could lose the entire cost basis
            max_loss_exposure += cost_basis

    lines = []
    lines.append("=== RISK EXPOSURE REPORT ===")
    lines.append(f"Available Balance: ${balance:,.2f}")
    lines.append(f"Total Deployed:    ${total_deployed:,.2f}")
    lines.append(f"Total Exposure:    ${balance + total_deployed:,.2f}")
    lines.append(f"Max Loss Exposure: ${max_loss_exposure:,.2f} (assuming stop-losses fill exactly or 100% loss without)")
    lines.append("")
    lines.append("--- Concentration by Market ---")
    if not market_exposure:
        lines.append("No open positions.")
    else:
        for mkt, amt in sorted(market_exposure.items(), key=lambda x: x[1], reverse=True):
            pct = (amt / total_deployed * 100) if total_deployed > 0 else 0
            lines.append(f"{mkt}: ${amt:,.2f} ({pct:.1f}%)")
    
    return "\n".join(lines)


def export_tax_report(engine: Union["PaperEngine", "RealTradingEngine"], path: str) -> str:
    """
    Export a Tax Report (Cost Basis and Realized Gains) as CSV.
    """
    from .records import extract_trades
    trades = extract_trades(engine)
    
    out_path = Path(path).resolve()
    
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["TradeID", "Market", "Side", "Acquired", "Sold", "Proceeds", "CostBasis", "RealizedGain", "GainPercent"])
        
        total_proceeds = 0.0
        total_cost = 0.0
        total_gains = 0.0
        
        for t in trades:
            proceeds = (t.exit_price * t.shares) if t.outcome != "LOST" else 0.0
            cost_basis = t.amount_in  # amount_in includes fees, which is correct for cost basis
            gain = proceeds - cost_basis
            
            writer.writerow([
                t.trade_id,
                t.market_slug,
                t.side,
                t.entry_time.isoformat(),
                t.exit_time.isoformat(),
                f"{proceeds:.6f}",
                f"{cost_basis:.6f}",
                f"{gain:.6f}",
                f"{t.pnl_pct:.2f}%"
            ])
            
            total_proceeds += proceeds
            total_cost += cost_basis
            total_gains += gain
            
        writer.writerow([])
        writer.writerow(["TOTALS", "", "", "", "", f"{total_proceeds:.6f}", f"{total_cost:.6f}", f"{total_gains:.6f}", ""])
        
    return str(out_path)


def export_audit_trail(engine: Union["PaperEngine", "RealTradingEngine"], path: str) -> str:
    """
    Export an Audit Trail (detailed log of all positions and orders) as JSON.
    """
    out_path = Path(path).resolve()
    
    audit_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_type": engine.__class__.__name__,
        "positions": [],
        "orders": []
    }
    
    for pid, pos in getattr(engine, "_positions", {}).items():
        pos_data = {
            "id": pid,
            "market": getattr(pos, "slug", ""),
            "side": getattr(pos, "side", ""),
            "shares": getattr(pos, "shares", 0.0),
            "avg_price": getattr(pos, "avg_price", 0.0),
            "cost_basis": getattr(pos, "cost_basis", 0.0),
            "resolved": getattr(pos, "resolved", False),
            "outcome": getattr(pos, "outcome", None),
            "order_ids": getattr(pos, "order_ids", [])
        }
        if hasattr(pos, "entry_time") and pos.entry_time:
            pos_data["entry_time"] = pos.entry_time.isoformat()
        audit_data["positions"].append(pos_data)
        
    for oid, order in getattr(engine, "_orders", {}).items():
        ord_data = {
            "id": oid,
            "market": getattr(order, "slug", ""),
            "side": getattr(order, "side", ""),
            "price": getattr(order, "price", 0.0),
            "amount": getattr(order, "amount", 0.0),
            "shares": getattr(order, "shares", 0.0),
            "status": getattr(order, "status", "unknown"),
            "created_at": order.created_at.isoformat() if hasattr(order, "created_at") and order.created_at else None,
            "filled_at": order.filled_at.isoformat() if hasattr(order, "filled_at") and order.filled_at else None,
            "tx_hash": getattr(order, "tx_hash", None)
        }
        audit_data["orders"].append(ord_data)
        
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)
        
    return str(out_path)
