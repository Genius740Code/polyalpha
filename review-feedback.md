# polyalpha review feedback

## what works (don't change)

- `Bot` + `@on_tick` — ~5 lines for a working strategy. Keep this as the flagship API.
- `conditions` module with `and_`, `or_`, `not_` + `&` `|` `~` operator overloads. Clean declarative DSL.
- `Client` as single entry point that wires everything together. Good DX.
- `client.markets.latest("BTC", "5m")` — simple, predictable market discovery.
- Paper trading with realistic configs (slippage, delay, fees, fill probability, presets).
- Rich feature surface: order book, AI, reporting, database, wallet, auto-redeem.

## what to fix

### 1. ~~split `PaperEngine` (3021 lines) and `RealTradingEngine` (5247 lines)~~ ✅ Done

PaperEngine split into focused modules:

```
trading/
├── paper_config.py       # PaperConfig dataclass + presets
├── paper_types.py        # PaperOrder, PaperPosition dataclasses + helpers
├── paper_risk.py         # RiskManager — risk checks, limits, stop-loss/tp/trailing
├── paper_fees.py         # PaperFeeManager — fee calculation, rebates, slippage, delay
├── paper_reporting.py    # display/summary functions
├── paper_engine.py       # PaperEngine — order placement, matching, lifecycle (composes above)
├── paper.py              # backward-compat shim re-exporting all public names
```

`paper.py` kept as a re-export shim so all existing imports continue to work. 698 tests passing.

TODO: Same split for `RealTradingEngine` (5247 lines).

### 2. fix `TickContext` lazy imports

Every property access does `import pandas` + relative import of `_native_ta`:

```python
@property
def rsi(self) -> Optional[float]:
    import pandas as _pd           # ← runs every tick
    from ..analysis._native_ta import rsi as _rsi  # ← runs every tick
```

Move to `__init__` or cache at module level. A bot running 5m timeframes gets 288 ticks/day — this is 288 redundant imports for every indicator.

### 3. ~~make conditions stateless~~ ✅ Done

`CrossedAbove` and `CrossedBelow` were mutating `self._prev` on every call. Now state is stored in `TickContext._cross_state[id(self)]` so a shared condition works independently across bots:

### 4. ~~add `sell` / `close_position` to TickContext~~ ✅ Done

Added `ctx.close_position(side, amount=None)` — delegates to `PaperEngine.sell_position`. Amount is optional (defaults to full position).

### 5. publish a "15-line sniper" example

The TA sniper example is 215 lines. It shows everything but contradicts the "very little code" promise. Add a `examples/sniper_minimal.py`:

```python
bot = polyalpha.Sniper("BTC", "5m", side="UP", entry=0.92, exit=0.88, amount=20)
bot.run()
```

### 6. async support

`Stream` and `Bot` are synchronous/blocking. Running 3 bots side by side means 3 threads. An async API would let users run multiple strategies in one event loop:

```python
async def main():
    await asyncio.gather(
        bot1.run_async(),
        bot2.run_async(),
        bot3.run_async(),
    )
```

### 7. minor things

| issue | where | fix |
|---|---|---|
| version mismatch | `__init__.py:195` says `0.2.0`, `pyproject.toml:7` says `0.2.01` | pick one |
| `_setup_logging()` called twice | `__init__.py:126` and `__init__.py:129` | remove one |
| every example does `sys.path.insert(0, ...)` | all 29 examples | add a `python -m polyalpha.examples.bot_simple` entry point or document `pip install -e .` |
| redundant `bot.stop()` in examples | `bot_simple.py:21` inside strategy then `bot_simple.py:26` in except | only need one |
| `RSIAbove` silently returns False on missing data | `conditions.py:122-124` | log a warning or raise, don't fail silently |

## summary

| priority | what | effort |
|---|---|---|
| P0 | split `PaperEngine` / `RealTradingEngine` | high |
| P0 | fix `TickContext` lazy imports | low |
| P1 | make conditions stateless | low |
| P1 | add `close_position` to TickContext | low |
| P2 | publish a 15-line sniper example | low |
| P2 | async support | high |
| P3 | version, double call, sys.path, redundant stop | trivial |
