# 30 Strategies — Polyalpha Code Review & Feasibility

## Critical Context

Polyalpha is a **Polymarket prediction markets SDK** — it trades UP/DOWN binary options, not BTC spot/futures. The `DataFeed` pulls OHLCV from Binance for *analysis only*. All strategies below are evaluated for this reality.

## Strategy-by-Strategy Review

### 1. EMA Crossover — ✅ DOABLE IMPLEMENTED

```
ctx.indicators.ema(9) and ctx.indicators.ema(21) exist.
```

**Code:**
```python
@bot.on_tick
def strat(ctx):
    ema9 = ctx.indicators.ema(9)
    ema21 = ctx.indicators.ema(21)
    sma200 = ctx.indicators.sma(200)
    if ema9 is None or ema21 is None or sma200 is None:
        return
    if ema9[-1] > ema21[-1] and ema9[-2] <= ema21[-2] and sma200[-1] > sma200[-2]:
        ctx.buy("UP", 20)
    elif ema9[-1] < ema21[-1] and ema9[-2] >= ema21[-2] and sma200[-1] < sma200[-2]:
        ctx.buy("DOWN", 20)
```

**Issues:**
- No way to know SMA slope from conditions DSL — must use imperative.
- Indicators return full series but `Bot` only shows latest tick context. BotHub's `IndicatorAccessor` returns DataFrames internally but strategy context (`TickContext`) has no `ctx.indicators` — that's only on `BotHub`'s `StrategyContext`. **Bot class users get zero indicator access.** This is a major gap.
- Workaround: use `BotHub` or manually compute via `DataFeed`.

---

### 2. Supertrend Momentum — ❌ IMPOSSIBLE (indicator missing) Implemented

```
Supertrend does NOT exist in polyalpha.
```

**Code:**
```python
# Cannot write. No supertrend() indicator.
# Would need 40+ lines of custom numpy logic inside strategy.
```

**Issues:**
- Missing from both `indicators.py` and `_native_ta.py`.
- Would need to be implemented as a custom indicator in `conditions.when()` or a separate module.
- The trailing-stop behavior *is* supported natively via `trail_sl` param on orders. The signal generation is the problem.

---

### 3. Ichimoku Breakout — ❌ IMPOSSIBLE (indicator missing) Implemented

```
Ichimoku Cloud does NOT exist in polyalpha.
```

**Code:**
```python
# Entirely missing. Needs Tenkan-sen, Kijun-sen, Senkou A/B, Chikou span.
# Would be ~80 lines of custom code minimum.
```

**Issues:**
- Complex multi-line indicator. Not worth implementing from scratch in a strategy file.
- Belongs in `_native_ta.py` as a first-class indicator.

---

### 4. Parabolic SAR Ride — ❌ IMPOSSIBLE (indicator missing) Implemented

```
Parabolic SAR does NOT exist in polyalpha.
```

**Code:**
```python
# Does not exist. Would need custom implementation ~30 lines.
```

**Issues:**
- Classic indicator. Missing from an "analysis" module that claims to have 20+ indicators.
- The trailing stop behavior (SAR flip → exit) is possible via `ctx.close_position()` after manual calc.

---

### 5. Donchian Channel Breakout — ❌ IMPOSSIBLE (indicator missing)

```
Donchian Channels do NOT exist in polyalpha.
```

**Code:**
```python
# Missing. Would need to track rolling 20-period high/low manually.
```

**Issues:**
- Simple rolling max/min — trivial to add to `_native_ta.py`.
- Workaround: store rolling high/low in strategy state dict.

---

### 6. Bollinger Squeeze — ⚠️ PARTIAL

```
BB(20,2) exists. BB width as % of 50-period average does not.
```

**Code:**
```python
@bot.on_tick
def strat(ctx):
    bb = ctx.indicators.bollinger_bands(20, 2)
    if bb is None:
        return
    width = bb["upper"] - bb["lower"]
    # PROBLEM: can't compute % of 50-period avg width without manual rolling calc
    # PROBLEM: ctx.price.up/down != BB band values - need to compare manually
```

**Issues:**
- `bollinger_bands()` returns DataFrame with `upper/middle/lower` columns. No helper to compute BB width as % of historical mean.
- No built-in squeeze detection.
- The R:moment `target = middle band` is impossible with binary options (no partial fills, all-or-nothing expiration).
- **Binary options fundamentally break mean-reversion** — you can't "target middle band" because payout is binary.

---

### 7. RSI 2-Period — ⚠️ PARTIAL

```
RSI exists, including custom periods via rsi(2).
```

**Code:**
```python
@bot.on_tick
def strat(ctx):
    r = ctx.indicators.rsi(2)
    # PROBLEM: r returns DataFrame. Need r.iloc[-1] to get current value.
    # ctx.buy("UP"/"DOWN") - but "target = RSI crosses 50" is impossible
    # because binary options have fixed expiry, not price targets.
```

**Issues:**
- Binary options have a fixed time horizon (5m). "Target = RSI crosses 50" means "I need a take-profit signal", which doesn't exist as a trigger — you'd have to poll on every tick.
- No take-profit *signal*, only take-profit *price* targets. RSI is a computed value, can't be used as a TP trigger.
- Workaround: `ctx.buy_once_per_candle()` + manual exit check on each tick, but `close_position` closes at current market price — not at RSI target.

---

### 8. Stochastic Overshoot — ⚠️ PARTIAL

```
Stochastic exists. Divergence detection does not.
```

**Code:**
```python
@bot.on_tick
def strat(ctx):
    stoch = ctx.indicators.stochastic(14, 3, 3)
    k = stoch["STOCHk"].iloc[-1]
    d = stoch["STOCHd"].iloc[-1]
    # "bullish divergence" needs comparison of price lows vs stoch lows over N bars
    # No built-in divergence detection
    # No bar low access in TickContext
```

**Issues:**
- **No divergence detection** anywhere in the codebase. This affects #2 (RSI Divergence) and #19 too.
- No access to candle low/high in `TickContext` or `StrategyContext` — only `ctx.price.up/down` (current mid price).
- `DataFeed` gives OHLCV but not integrated into strategy context.

---

### 9. Mean Reversion to VWAP — ⚠️ PARTIAL

```
VWAP exists. "2 sigma above VWAP" needs standard deviation of price vs VWAP.
```

**Code:**
```python
@bot.on_tick
def strat(ctx):
    v = ctx.indicators.vwap()
    # PROBLEM: vwap() returns single VWAP value, not standard deviation bands
    # "2σ above VWAP" requires rolling std of (price - VWAP) - not built
```

**Issues:**
- VWAP returns a single value, not bands.
- Would need manual rolling std calculation.
- Binary payout fundamentally undermines the thesis — price returning to VWAP doesn't guarantee a 5m UP outcome.

---

### 10. Keltner Channel Fade — ✅ DOABLE (indicator exists)

```
Keltner Channels exist.
```

**Code:**
```python
@bot.on_tick
def strat(ctx):
    kc = ctx.indicators.keltner_channels(20, 14, 2)
    price = ctx.price.up
    if price >= kc["upper"].iloc[-1]:
        ctx.buy("DOWN", 20)  # fade the touch
    elif price <= kc["lower"].iloc[-1]:
        ctx.buy("UP", 20)
```

**Issues:**
- Same "binary vs reversion" problem. A touch of the upper Keltner band doesn't mean the 5m binary will expire DOWN.
- No middle-line return mechanism. You bet DOWN and hope it expires out of the money on UP.

---

### 11. ATR Breakout — ⚠️ PARTIAL

```
ATR exists. "First 5m candle range * 2" needs candle open/high/low access.
```

**Code:**
```python
atr = ctx.indicators.atr(20)
# PROBLEM: No first-candle-of-timeframe tracking.
# ctx.candle_id and ctx.seconds_in exist but don't give open/high/low.
# ctx.price.up is current mid price, not candle OHLC.
```

**Issues:**
- **No OHLC candle access** in strategy context. You get a running mid price, not candle open/high/low/close.
- Cannot detect "first 5m candle" because you don't have bar open/close.
- `DataFeed` provides OHLCV but in a separate pipeline — not real-time.
- `ctx.seconds_in` can approximate "early in candle" but can't detect range.

---

### 12. VIX-equivalent Spike (RVOL Fade) — ❌ IMPOSSIBLE

```
No RVOL (relative volume) indicator. No volume data in tick context.
```

**Code:**
```python
# ctx does not expose volume on tick.
# ctx.indicators has no volume accessor.
# BotHub StrategyContext has no volume attribute.
```

**Issues:**
- TickContext has: `price.up/down`, `balance`, `positions`, `pnl`, `tick_count`, `trade_count`, `candle_id`, `seconds_in`. **No volume.**
- RVOL = current volume / avg volume. Neither is available.
- DataFeed can fetch volume, but not live per-tick.

---

### 13. Opening Range Break — ❌ IMPOSSIBLE

```
No candle open/high/low in context. No range tracking.
```

**Code:**
```python
# Need first-15m high/low. No bar data available.
```

**Issues:**
- Polymarket doesn't have a traditional "open" — it's continuous trading with a mid price.
- The concept of "opening range" doesn't apply to prediction markets.
- A Polymarket market begins at creation, not at a session open.

---

### 14. Implied-to-Realized Vol Arb — ❌ NOT APPLICABLE

```
No implied volatility surface. Binary options don't have IV/RV in standard form.
```

**Code:**
```python
# Makes no sense for binary prediction markets.
# HV(20) / HV(5) can be computed from DataFeed data,
# but "iron condor short wings" is options lingo that doesn't exist here.
```

**Issues:**
- Polymarket has no options (no calls, puts, strikes).
- No vol surface, no IV, no Greeks.
- The thesis is fundamentally about options vol arbitrage. Inapplicable.

---

### 15. Gap Fill — ❌ IMPOSSIBLE

```
No session concept. No prior close tracking.
```

**Code:**
```python
# Polymarket trades 24/7. No "prior session close."
# No data feed compares against previous session.
```

**Issues:**
- Polymarket runs 24/7/365. No market open/close bell.
- No gap concept.
- Workaround: track daily price at UTC midnight manually. Clunky.

---

### 16. MACD Histogram Momentum — ✅ DOABLE

```
MACD exists, returns histogram.
```

**Code:**
```python
@bot.on_tick
def strat(ctx):
    m = ctx.indicators.macd(12, 26, 9)
    hist = m["histogram"]
    if len(hist) >= 2:
        if hist.iloc[-1] > hist.iloc[-2] > 0:
            ctx.buy("UP", 20)
        elif hist.iloc[-1] < hist.iloc[-2] < 0:
            ctx.buy("DOWN", 20)
```

**Issues:**
- No condition DSL equivalent — must use imperative strategy.
- "Increasing for 2 bars" needs series access, which DSL conditions don't provide.
- Indicator values drift as more bars arrive — no persistent state for `hist.iloc[-2]`.
- Works but fragile.

---

### 17. OBV Divergence — ⚠️ PARTIAL

```
OBV exists. Divergence detection does not.
```

**Code:**
```python
obv = ctx.indicators.obv()
# PROBLEM: No helper to detect price making lower low while OBV makes higher low.
# Need manual comparison of recent minima - ~20 lines of state tracking.
```

**Issues:**
- No divergence detection (same as #8).
- No swing low/high detection.
- Would need manual state stored across ticks.

---

### 18. Volume Weighted Momentum — ❌ NOT APPLICABLE

```
No volume in tick context. No comparison against average volume.
```

**Code:**
```python
# ctx has no volume. Can't implement.
```

**Issues:**
- Tick context has zero volume data.
- "Volume > 1.5× avg" is impossible to evaluate.
- The entire volume-based category is non-functional.

---

### 19. RSI Divergence — ❌ IMPOSSIBLE

```
No divergence detection. No bar low/high in context.
```

**Code:**
```python
# Hidden divergence = price higher low + RSI higher low
# Needs: (1) swing low detection, (2) RSI at those swings, (3) comparison
# None of these primitives exist.
```

**Issues:**
- Missing: swing point detection, divergence comparison, bar OHLC.
- Would be ~60 lines of custom state logic.
- This is strategy logic that belongs in a reusable signal.

---

### 20. Chandelier Exit — ⚠️ PARTIAL

```
ATR exists. Trail exists. "Re-enter on flip" needs position re-entry logic.
```

**Code:**
```python
# ctx.indicators.atr(22) exists.
# ctx.position management exists.
# But "price < 22-day high - 3×ATR" needs rolling 22-day high - not in context.
# "Re-enter on flip" means exiting and re-entering - bot supports multiple entries.
```

**Issues:**
- Rolling period high/low is not accessible from strategy context.
- Would need manual `max()` tracking over last N ticks.

---

### 21. Z-Score Mean Reversion — ⚠️ PARTIAL

```
Rolling mean + std can be computed. No built-in z-score.
```

**Code:**
```python
prices = []  # manual tracking

@bot.on_tick
def strat(ctx):
    prices.append(ctx.price.up)
    if len(prices) >= 50:
        mean = sum(prices[-50:]) / 50
        std = (sum((x - mean)**2 for x in prices[-50:]) / 50) ** 0.5
        z = (ctx.price.up - mean) / std
        if z > 2:
            ctx.buy("DOWN", 20)
        elif z < -2:
            ctx.buy("UP", 20)
```

**Issues:**
- Manual rolling window is ugly but works.
- No existing z-score function in analysis module.
- Strategy state (`prices` list) is not persisted across bot restarts.
- Binary options: "exit at z=0" is not a thing (can only hold to expiry or close at market mid price).

---

### 22. Correlation Pairs — ❌ IMPOSSIBLE (no multi-asset in context)

```
Bot/BotHub is single-asset. No multi-asset correlation access.
```

**Code:**
```python
# Bot is tied to single asset ("BTC"). Cannot access SPX data.
# DataFeed can fetch SPX, but not integrated into strategy context.
```

**Issues:**
- Architecture is 1 bot = 1 asset. No multi-asset support.
- Can't access prices of other assets in strategy context.
- Workaround: run separate DataFeed outside strategy, push to shared state. Not clean.
- Polymarket SPX markets are different contracts from BTC markets — different order books, different liquidity.

---

### 23. Markov Regime Switch — ❌ ARCHITECTURAL LIMIT

```
No HMM. No persistent model state across ticks. No model serialization.
```

**Code:**
```python
# Needs: (1) hmmlearn dependency, (2) rolling window of returns, (3) state persistence
# None of this exists. Would need to train HMM outside bot, save, load in strategy.
```

**Issues:**
- `hmmlearn` is not a dependency.
- Models cannot be persisted in strategy context.
- "Stand aside" means bot goes idle — no built-in pause mechanism per regime.
- Architectural: strategy is stateless tick handler. No clean way to maintain HMM state.

---

### 24. Order Flow Imbalance — ⚠️ PARTIAL

```
Order book exists. CVD/delta does not.
```

**Code:**
```python
# ctx.orderbook.up.bids/asks exist but only on BotHub.
# imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol) can be computed.
# "10-tick scalp" needs tick-level trade data.
```

**Issues:**
- Order book access is **only on BotHub**, not Bot. Huge gap.
- Top-of-book vs depth-weighted imbalance — no built-in.
- "10-tick scalp" is not meaningful for binary options (expiry at fixed time).
- Polymarket order book is thin compared to Binance.

---

### 25. Entropy Collapse — ❌ NOT FEASIBLE

```
No permutation entropy. No numpy in bot context.
```

**Code:**
```python
# Permutation entropy needs: (1) scipy or custom implementation,
# (2) rolling window, (3) percentile ranking.
# None of these exist in strategy context.
```

**Issues:**
- `scipy` not guaranteed (optional dep).
- "Trade both sides" needs simultaneous long + short — impossible with binary options (single direction per order).
- Exotic statistical indicator with zero library support.

---

### 26. Funding Rate Fade — ❌ NOT APPLICABLE

```
No funding rate data. Polymarket is not a perpetual futures exchange.
```

**Code:**
```python
# Polymarket has NO funding rates.
# Markets price as binary options (0-100 cents on the dollar).
# "Overnight hold" is always possible (24/7 market) but no funding cost.
```

**Issues:**
- Entire thesis is based on perpetual futures funding arbitrage. Inapplicable.
- Polymarket pricing is based on outcome probability, not funding.

---

### 27. Open Interest Delta — ❌ NOT APPLICABLE

```
No open interest data. Polymarket does not have futures OI.
```

**Code:**
```python
# OI doesn't exist for binary outcome markets.
# Total liquidity yes, open interest no.
```

**Issues:**
- Prediction markets have outstanding positions but no standardized OI concept like futures.
- Gamma API may return `volume` for each market but not comparable to futures OI.

---

### 28. CVD Divergence — ❌ IMPOSSIBLE

```
Cumulative Volume Delta does not exist.
```

**Code:**
```python
# CVD needs tick-level trade data with buy/sell classification.
# Polymarket order book stream provides trades but no aggregated CVD indicator.
# No built-in CVD.
```

**Issues:**
- Missing from entire analysis pipeline.
- Would need to build from raw trade stream — no existing aggregation.
- Same divergence problem as #8, #17, #19.

---

### 29. Whale Cluster Detection — ❌ IMPOSSIBLE

```
No trade clustering. No level-based aggregation.
```

**Code:**
```python
# Needs: (1) order book snapshot history, (2) trade aggregation by price level,
# (3) cluster detection (N trades at same level in M minutes).
# None of this exists.
```

**Issues:**
- Order book snapshots aren't persisted for analysis.
- Trade stream is not aggregated by price bucket.
- 10 BTC limit orders: Polymarket uses USDC — are we talking $10,000 orders? The SDK doesn't flag whale activity.
- No on-chain whale wallet tracking integration.

---

### 30. Exchange Flow Velocity — ❌ NOT APPLICABLE

```
No exchange flow data. Polymarket is a single exchange/protocol.
```

**Code:**
```python
# "Net BTC flow to exchanges" requires on-chain wallet labels + multi-exchange tracking.
# Polyalpha only interfaces with Polymarket.
```

**Issues:**
- Thesis assumes multi-exchange Bitcoin flow tracking.
- Polymarket doesn't custody BTC.
- Would require external API (CryptoQuant, Glassnode) — zero integration.
- Even if implemented, BTC flowing to Coinbase says nothing about Polymarket binary option price.

---

## Summary of Findings

### Strategies by Feasibility

| Status | Count | Strategies |
|--------|-------|------------|
| **✅ Doable** | 3 | #1 EMA, #10 Keltner Fade, #16 MACD Hist |
| **⚠️ Partial** | 8 | #6 BB Squeeze, #7 RSI 2, #8 Stoch, #9 VWAP, #11 ATR, #17 OBV, #20 Chandelier, #21 Z-Score, #24 Order Flow |
| **❌ Impossible (missing indicator)** | 4 | #2 Supertrend, #3 Ichimoku, #4 ParSAR, #5 Donchian |
| **❌ Impossible (missing volume/OHLC data)** | 3 | #12 RVOL, #13 Opening Range, #18 Volume Mom |
| **❌ Not applicable (Polymarket architecture)** | 7 | #14 IV/RV, #15 Gap, #22 Pairs, #23 HMM, #26 Funding, #27 OI, #30 Exchange Flow |
| **❌ Impossible (missing advanced calc)** | 5 | #19 RSI Div, #24 Order Flow, #25 Entropy, #28 CVD, #29 Whale |

### Critical Feature Gaps in Polyalpha

| Gap | Severity | Affected Strategies |
|-----|----------|-------------------|
| **No Supertrend, Ichimoku, ParSAR, Donchian** | HIGH | #2, #3, #4, #5 |
| **No OHLC candle access in strategy context** | HIGH | #11, #13, #19, all divergence |
| **No volume in tick context** | HIGH | #12, #18 |
| **No divergence detection** | HIGH | #8, #17, #19, #28 |
| **No indicators on `Bot` — only `BotHub`** | HIGH | All strategies on `Bot` class |
| **No multi-asset price access** | MEDIUM | #22 |
| **No funding rate / OI data** | MEDIUM | #26, #27 |
| **Binary options incompatible with targets** | MEDIUM | #6, #7, #9, #10 |
| **No persistent strategy state** | MEDIUM | #20, #21, #23, #24 |
| **No JSON/YAML config — Python only** | LOW | All (ergonomic preference) |
| **No OHLCV backtesting** | MEDIUM | All (validation impossible) |

### What I Like

- **Clean Bot/BotHub abstraction** — strategy entry point is simple and focused.
- **Composable conditions DSL** — `and_(rsi_above(50), price_above("up", 0.9))` is elegant for simple strategies.
- **Order management is excellent** — trailing stops, OCO, bracket, TWAP, iceberg. Production-grade.
- **Risk management** — Kelly, percentage, hybrid position sizing, circuit breakers. Rare in a Python SDK.
- **Paper trading** — configurable fees, slippage, fill probability. Good simulation fidelity.
- **Report engine** — 30 metrics, 12 charts. Better than most trading SDKs.

### Structural Criticism

1. **The Bot/BotHub indicator gap is the single worst UX problem.** `Bot` is the advertised entry point in README examples, but it has zero indicator access. `BotHub` has indicators but is documented as "advanced." New users hit this immediately.

2. **No real-time OHLC integration.** The strategy context gives you a mid price, not candle data. For 5m strategies, you need to know where price is relative to the candle open, high, low. This forces everyone to use `DataFeed` separately or hack rolling state.

3. **Indicators return raw DataFrames, not scalar values.** Every strategy needs `.iloc[-1]` calls. This is fragile and ugly for strategy code. A `.value()` or `.current()` accessor on each indicator method would be cleaner.

4. **Conditions DSL is too limited.** It works for simple threshold checks but breaks for anything involving crossover, divergence, multi-bar patterns, or slope. These are *exactly the strategies 5m traders use.* The DSL needs `crossed_above(indicator, threshold)` and `slope(indicator, period)` primitives.

5. **No backtesting for indicator-based strategies.** The `BacktestEngine` only supports order-book strategies. You can't backtest any of these 30 strategies without writing a custom backtester. This is a dealbreaker for anyone serious about strategy development.

6. **Single-asset architecture limits strategy surface.** No multi-asset correlation, no pairs trading, no macro overlay. For a "trading bot SDK," the inability to access other markets is a hard ceiling.

7. **Strategy state is not managed.** Every strategy that needs rolling windows (half of the 30) must hack state via closures or globals. No clean `@bot.state` or persistent variable pattern.

8. **No take-profit signals — only price targets.** Many mean-reversion strategies want to exit based on an indicator crossing a threshold, not a specific price. The order system forces price-based exit.

9. **Order flow / market microstructure is underdeveloped.** Order book access is `BotHub`-only. CVD doesn't exist. No trade imbalance. For 5m strategies, microstructure is often *more* useful than TA.

10. **The README sells it as a "trading bot" but it's really a Polymarket SDK.** Strategies that assume spot/futures semantics (funding rates, OI, gaps, vol arb) are misleading. The documentation should be clearer about the binary options constraint.
