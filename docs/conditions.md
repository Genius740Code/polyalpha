# Trading Conditions

Composable trading conditions for `Bot` strategies. Each condition is a callable that receives a `TickContext` and returns `bool`.

```python
from polyalpha.conditions import rsi_above, price_above, and_

bot = polyalpha.Bot("BTC", "5m", balance=500)
bot.when(
    and_(rsi_above(50), price_above("up", 0.9))
).buy("UP", 20)
bot.run()
```

---

## Condition Protocol

```python
class Condition:
    """Base class for trading conditions."""
    def __call__(self, ctx: TickContext) -> bool:
        raise NotImplementedError

    def __and__(self, other) -> Condition  # &
    def __or__(self, other) -> Condition   # |
    def __invert__(self) -> Condition      # ~
```

All conditions support operator overloading:

```python
condition = (rsi_above(50) & price_above("up", 0.9)) | ~crossed_below("down", 0.3)
```

---

## Combinators

### `and_(*conditions)`

True when ALL sub-conditions are true (short-circuits).

```python
from polyalpha.conditions import and_

condition = and_(rsi_above(50), price_above("up", 0.9))
# or: condition = rsi_above(50) & price_above("up", 0.9)
```

### `or_(*conditions)`

True when ANY sub-condition is true (short-circuits).

```python
from polyalpha.conditions import or_

condition = or_(rsi_above(70), price_above("up", 0.95))
# or: condition = rsi_above(70) | price_above("up", 0.95)
```

### `not_(condition)`

Inverts a sub-condition.

```python
from polyalpha.conditions import not_

condition = not_(rsi_above(50))
# or: condition = ~rsi_above(50)
```

---

## Pre-built Conditions

### `rsi_above(threshold)`

True when RSI(14) is above the threshold.

```python
from polyalpha.conditions import rsi_above

condition = rsi_above(70)  # overbought
```

Returns `False` if RSI data is unavailable.

### `rsi_below(threshold)`

True when RSI(14) is below the threshold.

```python
from polyalpha.conditions import rsi_below

condition = rsi_below(30)  # oversold
```

Returns `False` if RSI data is unavailable.

### `price_above(side, threshold)`

True when the side's current price is above a threshold.

| Param | Type | Description |
|-------|------|-------------|
| `side` | `str` | `"UP"` or `"DOWN"` |
| `threshold` | `float` | Price threshold (0–1) |

```python
from polyalpha.conditions import price_above

condition = price_above("up", 0.9)
```

### `price_below(side, threshold)`

True when the side's current price is below a threshold.

```python
from polyalpha.conditions import price_below

condition = price_below("down", 0.2)
```

### `crossed_above(side, threshold)`

True when the side's price crossed **above** the threshold since the last tick. Returns `False` on the first tick (no history to compare).

```python
from polyalpha.conditions import crossed_above

condition = crossed_above("up", 0.9)
```

### `crossed_below(side, threshold)`

True when the side's price crossed **below** the threshold since the last tick. Returns `False` on the first tick.

```python
from polyalpha.conditions import crossed_below

condition = crossed_below("down", 0.3)
```

### `always()`

Always true — useful as a default or fallthrough.

```python
from polyalpha.conditions import always

condition = always()  # always triggers
```

### `never()`

Always false.

```python
from polyalpha.conditions import never

condition = never()  # never triggers
```

### `when(fn)`

Wrap an arbitrary function as a `Condition`.

| Param | Type | Description |
|-------|------|-------------|
| `fn` | `Callable[[TickContext], bool]` | Any function that takes a `TickContext` and returns bool |

```python
from polyalpha.conditions import when

condition = when(lambda ctx: ctx.tick_count > 100 and ctx.balance > 200)
```

---

## Custom Conditions

Subclass `Condition` and implement `__call__`:

```python
from polyalpha.conditions import Condition

class VolumeSpike(Condition):
    def __init__(self, min_volume: float):
        self._min_volume = min_volume

    def __call__(self, ctx) -> bool:
        return ctx.trade_count > 0 and ctx.balance < self._min_volume
```

Or use the `when()` factory with a lambda:

```python
condition = when(lambda ctx: ctx.pnl > 50)
```

---

## Full Example

```python
import polyalpha
from polyalpha.conditions import (
    and_, or_, not_,
    rsi_above, rsi_below,
    price_above, price_below,
    crossed_above,
)

bot = polyalpha.Bot("BTC", "5m", balance=500)

# Complex strategy: enter when RSI crosses above 30 AND price is above 0.85
# OR when price drops below 0.1 (oversold bounce play)
bot.when(
    or_(
        and_(crossed_above("up", 0.85), rsi_above(30)),
        price_below("down", 0.1),
    )
).buy("UP", 20)

bot.run()
```

---

## Factory Function Reference

| Function | Returns | Description |
|----------|---------|-------------|
| `rsi_above(t)` | `RSIAbove` | RSI(14) > threshold |
| `rsi_below(t)` | `RSIBelow` | RSI(14) < threshold |
| `price_above(side, t)` | `PriceAbove` | Side price > threshold |
| `price_below(side, t)` | `PriceBelow` | Side price < threshold |
| `crossed_above(side, t)` | `CrossedAbove` | Price crossed above since last tick |
| `crossed_below(side, t)` | `CrossedBelow` | Price crossed below since last tick |
| `always()` | `Always` | Always true |
| `never()` | `Never` | Always false |
| `when(fn)` | `LambdaCondition` | Custom function as condition |
| `and_(*c)` | `AndCondition` | All conditions true |
| `or_(*c)` | `OrCondition` | Any condition true |
| `not_(c)` | `NotCondition` | Invert condition |

Available via `polyalpha.conditions`:
```python
import polyalpha
polyalpha.conditions.rsi_above(50)
```
