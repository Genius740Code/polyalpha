# ── Endpoints ──────────────────────────────────────────────────────────────────

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_WS   = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# ── Timeframes ─────────────────────────────────────────────────────────────────

TIMEFRAME_SECONDS: dict[str, int] = {
    "5m":  300,
    "15m": 900,
    "1h":  3600,
    "4h":  14400,
    "24h": 86400,
}

# ── Assets ─────────────────────────────────────────────────────────────────────

ASSETS: list[str] = ["BTC", "ETH", "SOL", "XRP", "DOGE"]

# ── Fees ───────────────────────────────────────────────────────────────────────

TAKER_FEE_RATE = 0.02   # 2% simulated taker fee on paper fills

# ── Streaming ──────────────────────────────────────────────────────────────────

WS_PING_INTERVAL  = 10    # seconds — must text-PING before server drops us
WS_PING_TIMEOUT   = 5     # seconds to wait for PONG before marking stale
WS_RETRY_DELAY    = 3.0   # base back-off in seconds (multiplied by attempt #)
WS_MAX_RETRIES    = 10    # attempts before giving up entirely

# ── Data Feed ───────────────────────────────────────────────────────────────────

DEFAULT_CACHE_MAX_TICKS = 1000    # Maximum ticks to keep in WebSocket cache
API_REQUEST_TIMEOUT = 10          # Default timeout for API requests (seconds)
CACHE_EXPIRY_SECONDS = 3600        # Cache expiry time (1 hour)

# ── Sniper Bot ──────────────────────────────────────────────────────────────────

DEFAULT_WINDOW_SECONDS = 35       # Default trading window size
DEFAULT_MAX_CONSECUTIVE_LOSSES = 3
DEFAULT_PRE_WINDOW_BUFFER = 5     # Seconds before window to start monitoring
DEFAULT_POST_WINDOW_TIMEOUT = 10  # Seconds after window to wait for fills
DEFAULT_TA_LOOKBACK_PERIODS = 200 # Default lookback for technical analysis
MARKET_DISCOVERY_BACKOFF = 5      # Seconds to wait after failed market discovery
POSITION_LIMIT_CHECK_DELAY = 10   # Seconds to wait when position limit reached
ROLLOVER_PAUSE = 1                # Seconds to pause between market cycles
STREAM_SETUP_DELAY = 1            # Seconds to wait for stream connection
PRICE_CHECK_INTERVAL = 0.1         # Seconds between price checks
RESOLUTION_TIMEOUT = 120          # Max seconds to wait for market resolution
RESOLUTION_CHECK_INTERVAL = 0.5  # Seconds between resolution checks

# ── Slug helpers ───────────────────────────────────────────────────────────────

def build_slug(asset: str, timeframe: str, window_end_ts: int) -> str:
    """Return the deterministic Gamma event slug for an asset/timeframe window."""
    return f"{asset.lower()}-updown-{timeframe}-{window_end_ts}"
