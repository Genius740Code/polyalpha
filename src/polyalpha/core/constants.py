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

# ── Slug helpers ───────────────────────────────────────────────────────────────

def build_slug(asset: str, timeframe: str, window_end_ts: int) -> str:
    """Return the deterministic Gamma event slug for an asset/timeframe window."""
    return f"{asset.lower()}-updown-{timeframe}-{window_end_ts}"
