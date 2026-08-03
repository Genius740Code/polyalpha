# Plan: Port Polymarket signal-bot streaming features into polyalpha

> This file is the canonical reference. The source `polymarket_signal_bot_v3.py`
> has been deleted — all endpoint URLs, subscribe payloads, event shapes,
> thresholds, and algorithms from it are reproduced below so no reverse
> engineering is needed.

Priority: HIGH

Status:
- [x] 1. CLOB book stream (done in `src/polyalpha/orderbook/tracker.py`)
- [x] 2. favourite() + spread metrics (done in `src/polyalpha/orderbook/tracker.py`)
- [x] 3. sweep() trade-burst detection (done in `src/polyalpha/orderbook/tracker.py`)
- [ ] 4. CVDTracker in `src/polyalpha/analysis/delta.py`
- [x] 5. Shared Globals / one-connection-many-strategies refactor
- [ ] 6. LiquidationTracker

---

## 1. CLOB book stream — DONE

Implemented at `src/polyalpha/orderbook/tracker.py` (`TokenPairTracker`,
`TokenPairTrackerConfig`), exported from `src/polyalpha/orderbook/__init__.py`.
Constants in `src/polyalpha/core/constants.py`: `CLOB_API`,
`CLOB_WS`, `CLOB_MAX_AGE_S = 20`.

Spec (keep faithful to this when extending):

- Endpoint: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Subscribe on connect:
  `{"assets_ids": [up_id, down_id], "type": "market", "custom_feature_enabled": True}`
- Seed on connect (before subscribing): per token, REST
  `GET https://clob.polymarket.com/book?token_id=<tid>`.
- Sort-order (verified against live API 2026-07-31): Polymarket CLOB sorts
  `bids` **ascending** (best/highest bid = `bids[-1]`) and `asks` **descending**
  (best/lowest ask = `asks[-1]`). Always use `[-1]`, never `[0]`.
- Event handling (raw frames are JSON; a frame may be a single object or a list):
  - `book` → `{"event_type":"book","asset_id":tid,"bids":[{"price","size"},...],"asks":[...]}`
    → best_bid[tid] = `bids[-1]["price"]`, best_ask[tid] = `asks[-1]["price"]`.
  - `price_change` → `{"event_type":"price_change","price_changes":[
    {"asset_id":tid,"best_bid":"0.58","best_ask":"0.61"},...]}`
    → per entry update `best_bid`/`best_ask` (each may be absent; preserve the
    other side).
  - Ignore `PONG` (server's reply to our keepalive).
- Keepalive: send text `"PING"` every 10s on a background task; connect with
  `ping_interval=None` so the websocket lib adds no competing ping.
- Staleness: `fresh()` is False once no best-bid/ask update has arrived within
  `CLOB_MAX_AGE_S` (20s). `mid(tid)`/`up_mid`/`down_mid` return `None` when
  stale or a side is missing.
- Reconnect: on any WS drop, log a warning and sleep 3s, then reseed + resubscribe.

## 2. favourite() + spread metrics

Add to `TokenPairTracker` (or a thin wrapper): a per-token `spread_history`
(deque maxlen=120).

- `_record_spread(tid)`: on every book/price_change where both best_bid and
  best_ask are present, append `{"ts": time.time(), "spread": ask-bid,
  "bid": b, "ask": a}`.
- `favourite()`: `u, d = up_mid, down_mid`; if either is `None` → `(None, None)`;
  `u > d` → `("UP", u)`; `d > u` → `("DOWN", d)`; exact tie → `(None, None)`
  (never bias toward either side).
- `spread_stats(tid)`: needs `>= 10` samples else `None`; returns
  `(mean, std)` of the `spread` field.
- `spread_expansion(tid, z=2.0, lookback_samples=6)`:
  - needs `>= 10` samples and valid stats; if `std <= 0` or
    `cur["spread"] <= mean + z*std` → `None`.
  - `baseline = hist[-lookback_samples]` (or `hist[0]` when shorter).
  - `ask_move = cur["ask"] - baseline["ask"]`; `bid_move = baseline["bid"] - cur["bid"]`.
  - `side_pulled = "ask" if ask_move > bid_move else "bid"`.
  - return `{"spread","mean","std","side_pulled"}`.
- Interpretation: ask pulling back (rising) → bullish pressure; bid pulling
  back (falling) → bearish pressure.

## 3. sweep() trade-burst detection

Extend `TokenPairTracker`: per-token `trade_tape` (deque maxlen=200) fed by the
`last_trade_price` event.

- Event shape:
  `{"event_type":"last_trade_price","asset_id":tid,"price":...,"size":...,
  "side":"BUY"|"SELL","timestamp":...}`
- Append `{"ts": time.time(), "price": float(ev["price"]), "size":
  float(ev["size"]), "side": ev["side"]}`; swallow `TypeError`/`ValueError`.
- **NOTE**: verify `side` is the taker/aggressor side against the live stream.
  If it is actually the maker side, the direction interpretation below is
  inverted.
- `sweep(tid, window_s=15, min_count=4, min_notional=0.0)`:
  - `recent = [t for t in tape if now - t["ts"] <= window_s]`; `< min_count` → None.
  - `buys`/`sells` split by side; `dom_side` = the side with count >= the other
    (tie → BUY); if `len(dom) < min_count` → None.
  - `notional = sum(t["price"] * t["size"] for t in dom)`; `< min_notional` → None.
  - return `{"side": dom_side, "count": len(dom), "notional": notional}`.
- Direction interpretation (from bot strat16):
  - BUY sweep on UP token → `"UP"` (bullish); SELL sweep on UP token → `"DOWN"`.
  - BUY sweep on DOWN token → `"DOWN"`; SELL sweep on DOWN token → `"UP"`.
  - If both tokens sweep, pick the larger-notional candidate; require that
    direction's token mid to be present before emitting a signal.

## 4. CVDTracker — target `src/polyalpha/analysis/delta.py`

`delta.py` today is pandas-style indicator calcs with no streaming. Add a
Binance aggTrade feed.

- Endpoint: `wss://stream.binance.com:9443/ws/btcusdt@aggTrade`
  (connect with `ping_interval=20`).
- Message: `{"m": true|false, "q": "qty", "p": "px", ...}` — `m=true` →
  aggressive **sell** → signed `-qty`; `m=false` → aggressive **buy** → `+qty`.
- `samples`: deque of `(ts, signed)`; prune older than 180s.
- Every 10s, snapshot `{"ts": now, "cvd30": cvd(30), "cvd60": cvd(60)}` into
  `history` (deque maxlen=200).
- API:
  - `cvd(window_s)`: sum of signed qty with `ts >= now - window_s`.
  - `z(window_s=60)`: key = `"cvd60"` if `window_s >= 60` else `"cvd30"`; needs
    `>= 5` history points; `(cvd(window_s) - mean) / std`; `None` if `std == 0`.
  - `decelerating()`: needs `>= 2` snapshots; last and prev `cvd30` share a sign
    AND `abs(last) < abs(prev)`.
  - `velocity(key="cvd60")`: `hist[-1][key] - hist[-2][key]`.
  - `acceleration(key="cvd60")`: needs `>= 3` snapshots;
    `(hist[-1]-hist[-2]) - (hist[-2]-hist[-3])`.
- Reconnect: on drop, log warning + sleep 3s, loop forever.

## 5. Shared Globals / one-connection-many-strategies — DONE

Implemented in `src/polyalpha/globals.py` (exported from the package root):

- `Globals` dataclass mirroring the bot's field set: `price_feed`,
  `klines`, `cvd`, `obi_cache`, `futures`, `liq`, `db` + optional
  `eth_feed`, `klines_15m`, `klines_1h`. Out-of-scope feeds (Binance
  klines/OBI/futures, trade DB) stay `None` and are skipped by lifecycle.
  `Globals.defaults(asset, *, price_feed=True, cvd=True, liq=False)` builds
  the in-scope feeds; `start()` (idempotent, price_feed via
  `background=True`) / `stop()` (reverse order) manage them all.
- `MarketCtx` per-market scope wrapping a `TokenPairTracker`:
  holds `globals`, `tracker`, `open_price`, `end_time`; exposes
  `remaining`, `price()`, `favourite()`, `spread(side)`, `trade_sweep(side)`.
- `watch_market(globals, market, tick, interval=2.0)`: creates + starts the
  per-market `TokenPairTracker`, ticks `tick(ctx)` every 2s until
  `remaining <= 0`, `tracker.stop()` in `finally`.
- Wired into `strategy/suite.py` / `bot_hub.py` / `StrategyContext`: an
  optional `globals=` is shared by every strategy (`ctx.globals.cvd`, ...);
  `BotHub` reuses `globals.price_feed` instead of opening a second Chainlink
  connection. Caller owns the `Globals` lifecycle per the main/finally
  pattern above.

Audit results:
- `src/polyalpha/analysis/signals/` — computes from a caller-supplied
  `IndicatorCalculator` DataFrame; the per-call duplication lives in
  `DataFeed.fetch()` (Binance REST), which is the "klines" feed — tracked
  separately under TOD, not this plan.
- `src/polyalpha/bot.py` — single-strategy runner, already one shared
  connection; unchanged.

## 6. LiquidationTracker — target `src/polyalpha/analysis/`

- Endpoint: `wss://fstream.binance.com/ws/btcusdt@forceOrder`
  (connect with `ping_interval=20`).
- Message: `{"o": {"S": "SELL"|"BUY", "q": qty, "p": price}}` →
  append `(time.time(), side, notional=qty*price)` to `events` (deque maxlen=500).
- `cluster(window_s=20, min_count=3, notional_mult=2.0)`:
  - `recent` = events within `window_s`; `< min_count` → None.
  - `side` = the LAST event's side; `same` = events with that side;
    `len(same) < min_count` → None.
  - `notional = sum(same)`; hourly avg = mean notional over events within 3600s;
    if hourly avg exists and `notional < avg * notional_mult` → None.
  - return `{"direction": "DOWN" if side == "SELL" else "UP",
    "notional": notional, "count": len(same)}`.
- Semantics: a SELL liquidation closes a long (bearish pressure); a BUY
  liquidation closes a short (bullish pressure).
- Reconnect: on drop, log warning + sleep 3s, loop forever.

---

## Deliberately NOT stealing

- **Bot BTC price feed** (polled Binance REST spot every 2s): polyalpha's
  `ChainlinkStreamer` (`src/polyalpha/analysis/streaming.py`, class at :90)
  uses Polymarket's own Chainlink oracle WS (`crypto_prices_chainlink`) — the
  exact feed that decides up/down resolution. Keep polyalpha's; do not port the
  Binance poller.
- **Keepalive/PING handling**: polyalpha already handles text PING/PONG
  (`analysis/streaming.py` :332-336) and has a `_ping_loop` (:367). Reuse that
  pattern; do not duplicate.
- **KlineCache / OBICache / FuturesCache** (Binance klines REST poll, depth
  poll, funding + OI): these are Binance-side BTC data outside this plan's CLOB
  scope. Tracked separately under TOD ("binance data such as volume etc").

## Implementation order

1. ~~CLOB book stream~~ (done)
2. ~~favourite + spread_expansion~~ (done)
3. ~~sweep()~~ (done)
4. CVD in delta.py
5. Shared Globals refactor
6. LiquidationTracker
