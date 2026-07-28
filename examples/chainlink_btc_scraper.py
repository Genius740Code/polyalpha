"""
Simple BTC Price Scraper via Polymarket WebSocket
Scrapes BTC/USD price from Polymarket's Chainlink WebSocket and prints every second.
"""
import time
from datetime import datetime
from polyalpha.analysis import DataFeed, DataFeedConfig

# Configure data feed to use Polymarket WebSocket scraping (Chainlink data)
config = DataFeedConfig(
    source="scraping",
    timeframe="1m",
    lookback_periods=2,
    use_cache=False,
    scraping_timeout=5,  # Short timeout for quick price fetches
)

feed = DataFeed(config)

def main():
    """Main loop to fetch and print BTC price every second."""
    print("Starting Polymarket BTC Price Scraper (Chainlink data via WebSocket)...")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            try:
                # Fetch latest BTC data from Polymarket WebSocket (Chainlink)
                data = feed.fetch("BTC")
                
                if data is not None and len(data) > 0:
                    # Get the latest close price
                    latest_price = data['close'].iloc[-1]
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{timestamp}] BTC Price: ${latest_price:,.2f}")
                else:
                    print("Failed to fetch price")
                    
            except Exception as e:
                print(f"Error: {e}")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\nStopping scraper...")

if __name__ == "__main__":
    main()
