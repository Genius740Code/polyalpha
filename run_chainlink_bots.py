"""
Runner script for BTC 5min Chainlink Bots

Runs multiple Chainlink-based trading strategies simultaneously:
- Breakout: Volatility expansion UP/DOWN strategy
- Momentum: Higher-frequency BUY-ONLY strategy
- Reversal: Mean-reversion UP/DOWN strategy
- Sniper: High-winrate BUY-ONLY strategy

Usage:
    python run_chainlink_bots.py
"""
import subprocess
import sys
import signal
import time
from pathlib import Path

# Bot scripts to run
BOTS = [
    "btc_5min_chainlink_breakout.py",
    "btc_5min_chainlink_momentum.py",
    "btc_5min_chainlink_reversal.py",
    "btc_5min_chainlink_sniper.py",
]

# Store subprocesses as (bot_name, proc) tuples
processes = []


def signal_handler(sig, frame):
    """Handle Ctrl+C to gracefully shutdown all bots."""
    print("\n\n🛑 Shutting down all bots...")
    for _, proc in processes:
        if proc.poll() is None:
            proc.terminate()
    sys.exit(0)


def main():
    """Run all Chainlink bots concurrently."""
    signal.signal(signal.SIGINT, signal_handler)
    
    script_dir = Path(__file__).parent
    
    print("=" * 72)
    print("  🚀 BTC 5min Chainlink Bots Runner")
    print("=" * 72)
    print(f"  Running {len(BOTS)} bots concurrently:")
    for i, bot in enumerate(BOTS, 1):
        print(f"    {i}. {bot}")
    print("=" * 72)
    print("  Press Ctrl+C to stop all bots")
    print("=" * 72)
    print()
    
    # Start all bots
    for bot in BOTS:
        bot_path = script_dir / bot
        if not bot_path.exists():
            print(f"❌ Bot not found: {bot}")
            continue
        
        print(f"🚀 Starting {bot}...")
        proc = subprocess.Popen(
            [sys.executable, str(bot_path)],
            cwd=str(script_dir),
        )
        processes.append((bot, proc))
        time.sleep(1)  # Stagger starts slightly
    
    print("\n✅ All bots started. Monitoring...")
    print("-" * 72)
    
    while True:
        for name, proc in processes:
            if proc.poll() is not None:
                print(f"⚠️  {name} exited with code {proc.returncode}")
        time.sleep(5)


if __name__ == "__main__":
    main()
