# Sniper parity issues — sniper_poly vs sniper_plain

Fix parity bugs so `sniper_poly` produces the same trade data as `sniper_plain`.

Two comparison bots are meant to be equivalent but diverge:

- `sniper_plain.py` — consumes the shared Clob feed (`HubClient → /home/fese/polyhub/hub.py`).
- `sniper_poly.py` — uses the polyalpha `Sniper` bot, which opens **its own** direct Polymarket Clob websocket.

**Root cause (verified):** `sniper_poly` trades on a stale price. polyalpha's own websocket drops/reconnects frequently and there is **no staleness check before entry**. On market `btc-updown-5m-1785955200` at 18:44:30, plain correctly saw `up=0.895`, but poly entered UP @ `0.6550` (~90s old).

Secondary divergences: best vs worst book level; different market discovery; missing resolution persistence (`outcome=NULL`).

- **Priority:** 🔴 P0 (loses money / wrong fill) · 🟠 P1 (data divergence) · 🟡 P2 (correctness) 
- Not fixing: trading gates (`EN=0.60`, `EN_MAX=0.98`, `WIN=30`, `RSI_thread=50`, `AMT=20`) and all strategy parameters — leave unchanged.

---

## #1 — Staleness guard before entry  🔴 P0 (highest priority)

**Where** `polyalpha/src/polyalpha/**`

- `stream.py:190` — `self._last_price_time` field already exists. Surface it (report last-update age, e.g. `age_seconds = time.time() - self._last_price_time`) and make `last_price_time` publicly reachable via a Stream method.
- `bots/sniper.py` `_place_order()` **and** the entry trigger `_on_price_update`: before placing an order, **skip** the trade when the stream's last price update is older than a threshold.
  - Default `5.0s`; configurable via `SniperConfig.stale_data_max_age`.
  - Log `"entry skipped: stale price (age=%.1fs) ul=%.4f"` with old and reject.
  - Do **not** read `self._stream.up` blindly.
- **Test:** prices frozen past the threshold → no order placed; nothing freezes the thread.

## #2 — Route polyalpha off its own websocket onto the hub feed  🟠 P1

- `sniper_poly.py` currently uses `client.stream(market)`.
- **Preferred:** replace it with the hub-driven price source; `sniper_plain.py:Clob` already parses the identical feed (`book`, `price_change`, `best_bid_ask`). Reuse the same `Clob`/`HubClient` across both bots and drive the Sniper's `price` events from it (preserving UP/DOWN orientation).
- **Acceptable fallback** (if the wiring is too invasive): make poly's Stream reconnect faster — lower `STALE_DATA_SECONDS` to `10`, force-reconnect at `2x` — **and** still add fix #1. Document the tradeoff.

## #3 — Use the same book level in both bots  🟡 P2

- `sniper_plain.py:53-54` reads the **worst** level — `bids[-1], asks[-1]`.
- polyalpha reads **best** level — `stream.py:740: bids[0], asks[0]`.
- **Align both to the best bid/ask level:** change `sniper_plain.py` to `bids[0]/asks[0]` (`price_change`/`best_bid_ask` already use best). Verify the shared slots match.

## #4 — Fix resolution persistence (`outcome=NULL`)  🔴 P0

When the WS drops before a clean `market_resolved` (logs show `Resolution timeout, forcing manual resolve` then `No resolved position found`), the outcome must not be silently dropped.

- On timeout/disconnect, **fall back to resolving via Gamma** — `gamma_resolve(slug)` in `/home/fese/sniper_cmp/payoff.py` — and write it via `mark_outcome`.
- Confirm **no `outcome IS NULL` rows remain** for markets that actually resolved.

## #5 — Align market discovery  🟠 P1

- `sniper_poly` discovers its own market via `client.markets.latest()`, while `plain` follows the hub's current market — each fires different 5-min cycles.
- Make the poly path use the **same hub market event (`on_market → slug`) as plain** so both evaluate the same slug each 5-min cycle.

---

## Validation to run

Run both bots + `python compare.py` in `/home/fese/sniper_cmp`. Report:

- shared slots; only-poly / only-plain counts
- median `|up_mid diff|` (aim: near-zero on the shared set)
- outcome agreement and filled-set match between bots
- ensure `compare.py`'s `backfill_outcomes()` still works
- keep the 5 gates (`EN=0.60`, `EN_MAX=0.98`, `WIN=30`, `RSI_thread=50`, `AMT=20`) and all strategy parameters unchanged

**Tests (new)** — a pytest unit test under the tests dir for:

- the staleness guard: price frozen past the threshold → no order is placed
- book-level parity: best vs worst level alignment

## Report

What you changed, the before/after comparison numbers, and any residual diffs left and why.

---

## Do-not-touch

- Trading gates: `EN=0.60`, `EN_MAX=0.98`, `WIN=30`, `RSI_thread=50`, `AMT=20`
- Any strategy parameters

---

## Code style

- No new comments unless needed; match surrounding logging.