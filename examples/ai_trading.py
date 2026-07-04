"""
AI-Powered Trading Example for BTC Markets

This example demonstrates how to use OpenRouter AI integration for:
- Market analysis with structured JSON responses
- Trading signal generation
- Automated paper trading based on AI recommendations
- Real-time streaming with AI decision-making

Usage:
    # Set your OpenRouter API key as environment variable
    export OPENROUTER_API_KEY="your-api-key"
    
    # Or pass it directly
    python examples/ai_trading.py --api-key your-key
    
    # Run different modes
    python examples/ai_trading.py --mode analysis
    python examples/ai_trading.py --mode signal
    python examples/ai_trading.py --mode auto-trade
"""

import os
import sys
import argparse
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import polyalpha


def get_api_key() -> str:
    """Get OpenRouter API key from environment or prompt."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set")
        print("Get your API key from: https://openrouter.ai/keys")
        print("\nSet it with:")
        print("  export OPENROUTER_API_KEY='your-key'  # Linux/Mac")
        print("  set OPENROUTER_API_KEY=your-key      # Windows")
        sys.exit(1)
    return api_key


def basic_chat_example(client: polyalpha.Client) -> None:
    """Simple AI chat example."""
    print("\n" + "="*60)
    print("BASIC AI CHAT EXAMPLE")
    print("="*60)
    
    response = client.ai.chat(
        "What are the key factors to consider when trading BTC prediction markets?",
        temperature=0.7
    )
    
    print(f"\nModel: {response.model}")
    print(f"Tokens: {response.total_tokens}")
    print(f"Cost: ${response.cost or 'N/A'}")
    print(f"\nResponse:\n{response.content}")


def market_analysis_example(client: polyalpha.Client, asset: str = "BTC", timeframe: str = "5m") -> None:
    """AI-powered market analysis example."""
    print("\n" + "="*60)
    print(f"MARKET ANALYSIS EXAMPLE - {asset} {timeframe}")
    print("="*60)
    
    # Get the latest market
    market = client.markets.latest(asset, timeframe)
    print(f"\nMarket: {market.question}")
    print(f"UP Price: {market.up_price:.4f}")
    print(f"DOWN Price: {market.down_price:.4f}")
    print(f"Volume: ${market.volume:,.2f}")
    print(f"Liquidity: ${market.liquidity:,.2f}")
    
    # Prepare market data for AI
    market_data = {
        "question": market.question,
        "asset": asset,
        "timeframe": timeframe,
        "up_price": market.up_price,
        "down_price": market.down_price,
        "volume": market.volume,
        "liquidity": market.liquidity,
        "end_time": market.end_time,
        "url": market.url,
    }
    
    # Get AI analysis
    print("\nAnalyzing market with AI...")
    analysis = client.ai.analyze_market(market_data)
    
    print(f"\n📊 Sentiment: {analysis.sentiment.upper()}")
    print(f"🎯 Confidence: {analysis.confidence:.1%}")
    print(f"\n💭 Reasoning:")
    print(f"  {analysis.reasoning}")
    
    if analysis.risk_factors:
        print(f"\n⚠️  Risk Factors:")
        for factor in analysis.risk_factors:
            print(f"  - {factor}")
    
    if analysis.key_indicators:
        print(f"\n📈 Key Indicators:")
        for key, value in analysis.key_indicators.items():
            print(f"  {key}: {value}")


def trading_signal_example(client: polyalpha.Client, asset: str = "BTC", timeframe: str = "5m") -> None:
    """AI trading signal generation example."""
    print("\n" + "="*60)
    print(f"TRADING SIGNAL EXAMPLE - {asset} {timeframe}")
    print("="*60)
    
    # Get the latest market
    market = client.markets.latest(asset, timeframe)
    print(f"\nMarket: {market.question}")
    print(f"UP Price: {market.up_price:.4f}")
    print(f"DOWN Price: {market.down_price:.4f}")
    
    # Prepare market data
    market_data = {
        "question": market.question,
        "asset": asset,
        "timeframe": timeframe,
        "up_price": market.up_price,
        "down_price": market.down_price,
        "volume": market.volume,
        "liquidity": market.liquidity,
    }
    
    current_prices = {
        "up": market.up_price,
        "down": market.down_price,
    }
    
    # Get trading signal
    print("\nGenerating trading signal with AI...")
    signal = client.ai.generate_trading_signal(market_data, current_prices)
    
    print(f"\n🎯 Action: {signal.action}")
    if signal.side:
        print(f"📊 Side: {signal.side}")
    if signal.amount:
        print(f"💰 Amount: ${signal.amount:.2f}")
    print(f"🎲 Confidence: {signal.confidence:.1%}")
    print(f"\n💭 Reasoning:")
    print(f"  {signal.reasoning}")
    
    if signal.entry_price:
        print(f"\n📍 Entry Price: {signal.entry_price:.4f}")
    if signal.stop_loss:
        print(f"🛑 Stop Loss: {signal.stop_loss:.4f}")
    if signal.take_profit:
        print(f"🎯 Take Profit: {signal.take_profit:.4f}")


def auto_trade_example(client: polyalpha.Client, asset: str = "BTC", timeframe: str = "5m", 
                       max_trades: int = 5) -> None:
    """Automated trading with AI decisions."""
    print("\n" + "="*60)
    print(f"AUTO-TRADING EXAMPLE - {asset} {timeframe}")
    print("="*60)
    
    # Get the market
    market = client.markets.latest(asset, timeframe)
    print(f"\nMarket: {market.question}")
    print(f"Starting Balance: ${client.paper.balance:.2f}")
    print(f"Max Trades: {max_trades}")
    
    trade_count = 0
    
    def on_ai_decision(up: float, down: float) -> Optional[polyalpha.PaperOrder]:
        """Generate AI trading decision based on current prices."""
        nonlocal trade_count
        
        if trade_count >= max_trades:
            print(f"\n✅ Max trades ({max_trades}) reached. Stopping.")
            return None
        
        # Prepare market data
        market_data = {
            "question": market.question,
            "asset": asset,
            "timeframe": timeframe,
            "up_price": up,
            "down_price": down,
            "volume": market.volume,
            "liquidity": market.liquidity,
        }
        
        current_prices = {"up": up, "down": down}
        
        try:
            # Get AI signal
            signal = client.ai.generate_trading_signal(market_data, current_prices)
            
            print(f"\n🤖 AI Decision:")
            print(f"  Action: {signal.action}")
            print(f"  Confidence: {signal.confidence:.1%}")
            print(f"  Reasoning: {signal.reasoning[:100]}...")
            
            # Execute trade if confident enough
            if signal.action == "BUY" and signal.confidence > 0.6 and signal.side and signal.amount:
                trade_count += 1
                print(f"\n✅ Executing Trade #{trade_count}:")
                print(f"  Side: {signal.side}")
                print(f"  Amount: ${signal.amount:.2f}")
                
                order = client.paper.buy(
                    market,
                    side=signal.side,
                    amount=signal.amount
                )
                print(f"  Order ID: {order.id}")
                print(f"  Filled at: {order.price:.4f}")
                print(f"  Shares: {order.shares:.2f}")
                
                return order
            
            print(f"  ⏸️  No trade (confidence too low or action is HOLD)")
            return None
            
        except Exception as e:
            print(f"\n❌ AI Error: {e}")
            return None
    
    # Set up price stream
    stream = client.stream(market)
    
    @stream.on("price")
    def on_price(up: float, down: float):
        print(f"\n💰 Price Update: UP={up:.4f} DOWN={down:.4f}")
        on_ai_decision(up, down)
    
    @stream.on("close")
    def on_close():
        print("\n" + "="*60)
        print("MARKET CLOSED - FINAL SUMMARY")
        print("="*60)
        client.paper.summary()
    
    print("\n🚀 Starting auto-trading stream...")
    print("Press Ctrl+C to stop early\n")
    
    try:
        stream.start()
    except KeyboardInterrupt:
        print("\n\n⏸️  Stopped by user")
        stream.stop()
    
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    client.paper.summary()
    print(f"\n💰 Total AI Cost: ${client.ai.total_cost:.4f}")
    print(f"📊 Total AI Tokens: {client.ai.total_tokens}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="AI-Powered Trading Example")
    parser.add_argument("--api-key", help="OpenRouter API key (or set OPENROUTER_API_KEY env var)")
    parser.add_argument("--mode", choices=["chat", "analysis", "signal", "auto-trade"], 
                       default="analysis", help="Example mode to run")
    parser.add_argument("--asset", default="BTC", help="Asset to trade (BTC, ETH, SOL, etc.)")
    parser.add_argument("--timeframe", default="5m", help="Timeframe (5m, 15m, 1h, 4h, 24h)")
    parser.add_argument("--max-trades", type=int, default=5, 
                       help="Maximum trades for auto-trade mode")
    parser.add_argument("--balance", type=float, default=100.0, 
                       help="Starting paper trading balance")
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or get_api_key()
    
    # Initialize client
    print("="*60)
    print("POLYALPHA AI TRADING EXAMPLE")
    print("="*60)
    print(f"Asset: {args.asset}")
    print(f"Timeframe: {args.timeframe}")
    print(f"Mode: {args.mode}")
    print(f"Balance: ${args.balance:.2f}")
    
    client = polyalpha.Client(
        openrouter_api_key=api_key,
        balance=args.balance,
        log_level="INFO"
    )
    
    try:
        # Run selected mode
        if args.mode == "chat":
            basic_chat_example(client)
        elif args.mode == "analysis":
            market_analysis_example(client, args.asset, args.timeframe)
        elif args.mode == "signal":
            trading_signal_example(client, args.asset, args.timeframe)
        elif args.mode == "auto-trade":
            auto_trade_example(client, args.asset, args.timeframe, args.max_trades)
        
    except polyalpha.AIAuthenticationError:
        print("\n❌ Error: Invalid OpenRouter API key")
        print("Please check your API key at: https://openrouter.ai/keys")
    except polyalpha.MarketNotFound:
        print(f"\n❌ Error: No active market found for {args.asset} {args.timeframe}")
        print("Try a different asset or timeframe")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    main()
