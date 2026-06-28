# Endpoints
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_WS   = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# Timeframe seconds (used for slug timestamp floor)
TIMEFRAME_SECONDS = {
    "5m":  300,
    "15m": 900,
    "1h":  3600,
    "4h":  14400,
    "24h": 86400,
}

# Supported assets
ASSETS = ["BTC", "ETH", "SOL", "XRP", "DOGE"]

# Slug prefix pattern: {asset}-updown-{timeframe}-{unix_ts}
# The unix_ts is the END time of the window (= window_start + interval)
def slug_prefix(asset: str, timeframe: str) -> str:
    return f"{asset.lower()}-updown-{timeframe}-"

def build_slug(asset: str, timeframe: str, window_end_ts: int) -> str:
    return f"{asset.lower()}-updown-{timeframe}-{window_end_ts}"