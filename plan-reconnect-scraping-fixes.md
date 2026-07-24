# Reconnection & Scraping Reliability Plan

## Phase 1: `ChainlinkStreamer` (`src/polyalpha/analysis/streaming.py`)

| # | Issue | Fix |
|---|-------|-----|
| 1.1 | Timeout `break` exits cleanly → no reconnect delay | `raise` instead of `break` so outer `except` fires |
| 1.2 | Fixed 5s reconnect, no backoff/jitter | Add exponential backoff + jitter, track `consecutive_failures` |
| 1.3 | No max retries, infinite loop关系 | Add `max_retries` (default 10), emit error + stop when exceeded |
| 1.4 | No PING/PONG keepalive | Spawn concurrent ping task, handle server PING → PONG |
| 1.5 | No stale data detection | Track `_last_price_time`, warn if >30s since last update |
| 1.6 | Per-recv timeout too tied to overall timeout | Separate recv timeout from overall session timeout |

## Phase 2: `DataFeed` scraping (`src/polyalpha/analysis/data_feed.py`)

| # | Issue | Fix |
|---|-------|------|
| 2.1 | No retry before Binance fallback | Retry WS 2-3x with 1s backoff before falling back |
| 2.2 | Per-message timeout = 90s | Split into `recv_timeout` (10s) + `session_duration` (90s) |
| 2.3 | 2s sleep per tick → ~45 ticks only | Make delay adaptive per timeframe (0.2s-0.5s), remove per-tick sleep |
| 2.4 | No reconnection within scrape session | Wrap WS in inner retry loop; don't give up on single disconnect |

## Phase 3: Main `Stream` (`src/polyalpha/stream.py`)

| # | Issue | Fix |
|---|-------|------|
| 3.1 | `consecutive_failures` never resets | Reset to 0 after successful `_connect()` returns |
| 3.2 | No missing-pong detection | Track `_last_pong_time`, warn on missed pongs |
| 3.3 | Circuit breaker sleep(5) hardcoded | Use `recovery_timeout` from breaker config instead |

## Phase 4: Constants (`src/polyalpha/core/constants.py`)

| # | Change |
|---|--------|
| 4.1 | Add `CL_WS_RECV_TIMEOUT = 10` for ChainlinkStreamer per-message timeout |
| 4.2 | Add `CL_WS_MAX_RETRIES = 10` |
| 4.3 | Add `CL_WS_BASE_DELAY = 3.0` |
| 4.4 | Add `CL_WS_BACKOFF_FACTOR = 2.0` |
| 4.5 | Add `CL_WS_JITTER = 0.2` |
| 4.6 | Add `SCRAPE_RECV_TIMEOUT = 10` for data_feed per-message timeout |
| 4.7 | Add `SCRAPE_RETRY_ATTEMPTS = 3` |