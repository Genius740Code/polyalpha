"""
NTP-based clock sync for deterministic Polymarket slug generation.

Usage
-----
    from polyalpha.core.time_sync import TimeSync

    ts = TimeSync()
    report = ts.sync()
    print(f"Offset: {report.offset_ms:.1f}ms")

    # Get corrected Unix timestamp (system time + offset)
    now = ts.now()

Slug generation uses ``int(time.time())`` — if the local clock is off by
even a few seconds, the window-finding math in ``markets.py`` will probe
wrong slugs and raise ``MarketNotFound``.
"""

from __future__ import annotations

import logging
import random
import socket
import struct
import time

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

NTP_PORT = 123
NTP_VERSION = 4  # NTP v4
NTP_TIMEOUT = 5.0
NTP_RETRIES = 2

# NTP ↔ Unix epoch offset (seconds between 1900-01-01 and 1970-01-01)
NTP_EPOCH_OFFSET = 2_208_988_800

DEFAULT_SERVERS: list[str] = [
    "pool.ntp.org",
    "time.google.com",
    "time.cloudflare.com",
    "time.windows.com",
]

# ── NTP packet helpers ────────────────────────────────────────────────────────

_NTP_PACKET = b"\x1b" + 47 * b"\0"  # NTP v4 client-mode request (48 bytes)


def _query_server(host: str, port: int = NTP_PORT, timeout: float = NTP_TIMEOUT) -> dict:
    """Send one NTP request to *host*, return timing data.

    Returns
    -------
    dict with keys: offset (s), delay (s), t1–t4 (client/server timestamps).
    Raises socket / timeout errors on failure.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        t1 = time.time()
        sock.sendto(_NTP_PACKET, (host, port))

        response, _ = sock.recvfrom(1024)
        t4 = time.time()
    finally:
        sock.close()

    # NTP responses are exactly 48 bytes, but some servers pad them
    # (extension fields / auth). Reject undersized packets and unpack only
    # the first 48 bytes so oversized ones don't crash the whole failover.
    if len(response) < 48:
        raise ValueError(f"Short NTP response from {host} ({len(response)} bytes)")
    unpacked = struct.unpack("!12I", response[:48])

    # Receive Timestamp (srv rx) = bytes 32-39 → unpacked[6], unpacked[7]
    # Transmit Timestamp (srv tx) = bytes 40-47 → unpacked[10], unpacked[11]
    #   (RFC 5905 section 7.3 — we only need Transmit Timestamp for offset calc)

    t3_int = unpacked[10]
    t3_frac = unpacked[11]

    # NTP timestamp = seconds since 1900 + fractional part / 2^32
    t3 = (t3_int - NTP_EPOCH_OFFSET) + t3_frac / 2**32

    # Symmetric peer model approximation (RFC 5905 appendix A.5.1.2):
    #   offset = ((t2 - t1) + (t3 - t4)) / 2
    # We don't parse t2 from the response for simplicity.
    # Instead use the client-observed timestamps with t2 ≈ t3 (server processing ≈ 0):
    #   offset = t3 - ((t1 + t4) / 2)
    # This is a common approximation used in SNTP (RFC 5905 section 14).
    midpoint = (t1 + t4) / 2.0
    offset = t3 - midpoint
    delay = t4 - t1

    return {
        "server": host,
        "offset": offset,
        "offset_ms": offset * 1000.0,
        "delay": delay,
        "delay_ms": delay * 1000.0,
        "t1": t1,
        "t3": t3,
        "t4": t4,
    }


# ── TimeSync ──────────────────────────────────────────────────────────────────


class TimeSync:
    """Query NTP servers to determine local clock drift.

    Caches the last sync result so repeated calls are cheap.

    Parameters
    ----------
    servers      : List of NTP server hostnames to try (in random order).
    cache_ttl    : Seconds before a cached result is considered stale.
    warn_drift_ms: Log a warning when |offset| exceeds this.
    fail_drift_ms: Return ``can_proceed=False`` when |offset| exceeds this.
    retries      : Attempts per server before falling through.
    timeout      : Socket timeout per NTP request.
    """

    def __init__(
        self,
        servers: list[str] | None = None,
        cache_ttl: float = 300.0,
        warn_drift_ms: float = 2_000.0,
        fail_drift_ms: float = 10_000.0,
        retries: int = 2,
        timeout: float = 5.0,
    ):
        self._servers = list(servers or DEFAULT_SERVERS)
        self._cache_ttl = cache_ttl
        self._warn_drift_ms = warn_drift_ms
        self._fail_drift_ms = fail_drift_ms
        self._retries = retries
        self._timeout = timeout

        # Last sync state
        self._offset = 0.0  # seconds (system time + offset = true time)
        self._last_sync = 0.0
        self._last_server: str | None = None
        self._last_delay_ms: float = 0.0

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def offset(self) -> float:
        """Current NTP-derived clock offset in seconds (cached)."""
        return self._offset

    @property
    def offset_ms(self) -> float:
        """Current NTP-derived clock offset in milliseconds."""
        return self._offset * 1000.0

    @property
    def is_stale(self) -> bool:
        """Whether cached sync data is older than *cache_ttl*."""
        return (time.time() - self._last_sync) > self._cache_ttl

    @property
    def last_sync_ago(self) -> float:
        """Seconds since last successful NTP sync."""
        return time.time() - self._last_sync if self._last_sync else float("inf")

    # ── Core API ───────────────────────────────────────────────────────────

    def now(self) -> float:
        """Return the NTP-corrected Unix timestamp.

        Uses cached offset — call ``.sync()`` first or let it auto-sync.
        """
        return time.time() + self._offset

    def now_int(self) -> int:
        """Return the NTP-corrected Unix timestamp as an integer.

        Convenience for slug generation (``int(time.time())`` equivalent).
        """
        return int(self.now())

    def sync(self, force: bool = False) -> dict:
        """Query NTP servers and return a sync report.

        Parameters
        ----------
        force : Bypass the cache and force a fresh network query.

        Returns
        -------
        dict with keys:
            server       : Hostname that responded.
            offset_ms    : Clock offset in ms (positive = system is behind).
            delay_ms     : Round-trip delay in ms.
            can_proceed  : True if |offset| < *fail_drift_ms*.
            warnings     : List of human-readable warning strings.
            corrected_ts : NTP-corrected Unix timestamp.
        """
        if not force and not self.is_stale:
            return self._report()

        servers = list(self._servers)
        random.shuffle(servers)

        last_error: str | None = None

        for host in servers:
            for attempt in range(1, self._retries + 1):
                try:
                    result = _query_server(host, timeout=self._timeout)
                except (socket.timeout, OSError, struct.error, ValueError) as exc:
                    last_error = f"{host}: {exc}"
                    log.debug("NTP sync failed (%s, attempt %d/%d)", host, attempt, self._retries)
                    continue

                self._offset = result["offset"]
                self._last_sync = time.time()
                self._last_server = host
                self._last_delay_ms = result["delay_ms"]

                log.info(
                    "NTP synced via %s | offset=%.1fms delay=%.1fms",
                    host, result["offset_ms"], result["delay_ms"],
                )
                return self._report()

        # All servers / attempts exhausted
        log.warning("NTP sync failed — all servers unreachable (%s)", last_error)
        return self._report(error=f"All NTP servers unreachable. Last: {last_error}")

    def report(self) -> dict:
        """Return the current sync report without querying."""
        return self._report()

    # ── Internal ───────────────────────────────────────────────────────────

    def _report(self, error: str | None = None) -> dict:
        """Build the sync report dict from current state."""
        abs_offset_ms = abs(self.offset_ms)
        warnings: list[str] = []

        if abs_offset_ms > self._fail_drift_ms:
            warnings.append(
                f"Clock drift {self.offset_ms:.0f}ms exceeds fail threshold "
                f"({self._fail_drift_ms:.0f}ms) — slug generation may be unreliable"
            )
        elif abs_offset_ms > self._warn_drift_ms:
            warnings.append(
                f"Clock drift {self.offset_ms:.0f}ms exceeds warning threshold "
                f"({self._warn_drift_ms:.0f}ms)"
            )

        can_proceed = abs_offset_ms < self._fail_drift_ms

        return {
            "server": self._last_server or "none",
            "offset_ms": round(self.offset_ms, 1),
            "delay_ms": round(self._last_delay_ms, 1),
            "can_proceed": can_proceed,
            "synced": self._last_sync > 0,
            "stale": self.is_stale,
            "last_sync_ago": round(self.last_sync_ago, 1),
            "warnings": warnings,
            "corrected_ts": int(time.time() + self._offset),
            "error": error,
        }

    def __repr__(self) -> str:
        return (
            f"TimeSync(offset={self.offset_ms:.1f}ms, "
            f"server={self._last_server}, "
            f"synced={self._last_sync > 0})"
        )
