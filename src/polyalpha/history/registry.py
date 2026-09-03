"""
Registry — in-process singleton for ChainlinkRecorder per (db_path, asset).

Ensures one WS + one SQLite handle per (db_path, asset) inside a process,
so BotHub + Client can share without duplicating connections.
Thread-safe.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from .config import ChainlinkHistoryConfig
from .recorder import ChainlinkRecorder

_REGISTRY: dict[tuple[str, str], ChainlinkRecorder] = {}
_LOCK = threading.RLock()
_REFCOUNT: dict[tuple[str, str], int] = {}


def _key(db_path: str | Path, asset: str) -> tuple[str, str]:
    p = str(Path(str(db_path)).expanduser().resolve()) if str(db_path).strip() else ":memory:"
    return (p, asset.upper())


def get_or_create(
    db_path: str | Path,
    asset: str,
    config: ChainlinkHistoryConfig | None = None,
    read_only: bool = False,
) -> ChainlinkRecorder:
    """
    Return singleton Recorder for (db_path, asset). Create if missing.
    Increments refcount.
    """
    k = _key(db_path, asset)
    with _LOCK:
        if k in _REGISTRY:
            _REFCOUNT[k] = _REFCOUNT.get(k, 1) + 1
            return _REGISTRY[k]
        # create new
        rec = ChainlinkRecorder(config=config) if config is not None else ChainlinkRecorder(db_path=db_path, read_only=read_only)
        # ensure config db_path aligns
        _REGISTRY[k] = rec
        _REFCOUNT[k] = 1
        return rec


def get(db_path: str | Path, asset: str) -> Optional[ChainlinkRecorder]:
    k = _key(db_path, asset)
    with _LOCK:
        return _REGISTRY.get(k)


def release(db_path: str | Path, asset: str) -> None:
    """
    Decrement refcount; when 0, stop recorder and remove from registry.
    """
    k = _key(db_path, asset)
    with _LOCK:
        if k not in _REGISTRY:
            return
        cnt = _REFCOUNT.get(k, 1) - 1
        if cnt <= 0:
            rec = _REGISTRY.pop(k)
            _REFCOUNT.pop(k, None)
            try:
                rec.stop()
            except Exception:
                pass
        else:
            _REFCOUNT[k] = cnt


def clear() -> None:
    """Stop all and clear registry (for tests)."""
    with _LOCK:
        for rec in list(_REGISTRY.values()):
            try:
                rec.stop()
            except Exception:
                pass
        _REGISTRY.clear()
        _REFCOUNT.clear()
