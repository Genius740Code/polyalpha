"""bot_hub.history — Chainlink history helper.

Resolves the ``chainlink_history`` kwarg accepted by ``BotHub`` and
``Bot`` into a normalized ``(recorder, owned)`` tuple.
"""

from __future__ import annotations


def _resolve_chainlink_history(value, asset: str):
    if value is None or value is False:
        return None, False
    try:
        from ..history import ChainlinkHistoryConfig, ChainlinkRecorder
    except ImportError:
        return None, False
    if isinstance(value, ChainlinkRecorder):
        return value, False
    # Import here to avoid circular
    from ..history import ChainlinkHistoryConfig as CHC, ChainlinkRecorder as CR  # type: ignore

    if isinstance(value, CHC):
        rec = CR(config=value)
        return rec, True
    if isinstance(value, dict):
        cfg = CHC(warmup=dict(value))
        rec = CR(config=cfg)
        return rec, True
    if value is True:
        cfg = CHC(warmup={"1m": 20})
        rec = CR(config=cfg)
        return rec, True
    if isinstance(value, str):
        cfg = CHC(warmup={"1m": 20}, db_path=value)
        rec = CR(config=cfg)
        return rec, True
    return None, False
