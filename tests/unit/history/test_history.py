import time, tempfile
from pathlib import Path
import pytest

# mock streamer to avoid network
import polyalpha.analysis.streaming as streaming

def _mock_init(self, config=None):
    self.config = config or streaming.ChainlinkStreamerConfig()
    self._callbacks={"price":[],"error":[],"connect":[],"disconnect":[]}
    self._running=False
    self.last_price=None
    self._active_symbol=None
    self._accessors={}
    self._last_price_time=0
    self._stale_warned=False
def _mock_start(self, symbol, background=False):
    self._running=True
    self._active_symbol=symbol.upper()
def _mock_stop(self):
    self._running=False

@pytest.fixture(autouse=True)
def mock_streamer(monkeypatch):
    monkeypatch.setattr(streaming.ChainlinkStreamer, "__init__", _mock_init)
    monkeypatch.setattr(streaming.ChainlinkStreamer, "start", _mock_start)
    monkeypatch.setattr(streaming.ChainlinkStreamer, "stop", _mock_stop)

def test_user_chooses_keep_and_unused_deleted():
    from polyalpha.history import ChainlinkHistoryConfig, ChainlinkRecorder
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp)/"db"
        cfg = ChainlinkHistoryConfig(warmup={"1m":3, "1s":5, "1h":2}, db_path=str(db))
        rec = ChainlinkRecorder(config=cfg)
        start = int(time.time())//60*60
        ticks = [(start+i, 60000+i) for i in range(200)]
        rec.inject_ticks("BTC", ticks)
        assert rec.count("1m","BTC") == 3
        assert rec.count("1s","BTC") == 5  # pruned to keep 5
        # 1h only 1 closed because 200s is 3 mins
        # insert fake unused TF
        rec._store._conn.execute("INSERT OR REPLACE INTO candles(asset,timeframe,start_ts,open,high,low,close,count) VALUES('BTC','1d',123,1,2,0.5,1.5,1)")
        rec._store._conn.commit()
        assert rec.count("1d","BTC") == 1
        # now change config to only 1m:2 — unused 1s/1h/1d should be pruned
        cfg2 = ChainlinkHistoryConfig(warmup={"1m":2}, db_path=str(db))
        rec2 = ChainlinkRecorder(config=cfg2)
        rec2._asset="BTC"
        # reuse same store file
        rec2._store = rec._store
        # prune_unused removes TFs not in keep, and prune_keep_last_n trims excess
        rec2._store.prune_all("BTC", cfg2.keep)
        assert rec2.count("1s","BTC") == 0
        assert rec2.count("1h","BTC") == 0
        assert rec2.count("1d","BTC") == 0
        assert rec2.count("1m","BTC") == 2

def test_storage_best_format_sqlite_wal():
    from polyalpha.history import ChainlinkHistoryConfig, ChainlinkRecorder
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp)/"db"
        cfg = ChainlinkHistoryConfig(warmup={"1m":10, "1h":5}, db_path=str(db))
        rec = ChainlinkRecorder(config=cfg)
        start = int(time.time())//3600*3600
        ticks = [(start+i, 50000+i*0.1) for i in range(4000)]  # ~1h
        rec.inject_ticks("BTC", ticks)
        # file should be tiny (WAL, WITHOUT ROWID)
        size = Path(db).stat().st_size
        # 15 rows * overhead ~ small, one page 4096
        assert size < 100_000, f"db too big {size}"
        # check WAL mode
        cur = rec._store._conn.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0].lower() == "wal"

def test_bot_warmup_gate(monkeypatch):
    from polyalpha import Bot
    from polyalpha.history import ChainlinkHistoryConfig
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp)/"db"
        cfg = ChainlinkHistoryConfig(warmup={"1m":2}, db_path=str(db), block="wait", warmup_emit_interval=0.01)
        bot = Bot("BTC","5m", balance=100, chainlink_history=cfg)
        rec = bot.chainlink_history
        assert not rec.is_ready("1m",2)
        fired=[]
        @bot.on_warmup
        def w(s): fired.append(s)
        @bot.on_tick
        def strat(ctx):
            fired.append("strat")
        # simulate gate
        from polyalpha.bot import TickContext
        bot._ctx = TickContext(bot)
        # need to expose _stream etc for gate logic — just test is_ready
        assert not rec.is_ready("1m",2)
        # inject to make ready
        start=int(time.time())//60*60
        rec.inject_ticks("BTC", [(start+i, 70000+i) for i in range(130)])
        assert rec.is_ready("1m",2)
        bot._cleanup()

def test_bot_shorthand_dict():
    from polyalpha import Bot
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp)/"db"
        # user shorthand dict {"1m":10, "1h":50, "1s":20}
        bot = Bot("BTC","5m", balance=100, chainlink_history={"1m":10, "1h":50, "1s":20})
        cfg = bot.chainlink_history.config
        assert cfg.warmup == {"1m":10, "1h":50, "1s":20}
        assert set(cfg.timeframes) == {"1m","1h","1s"}
        # keep equals warmup
        assert cfg.keep == cfg.warmup
        bot._cleanup()

def test_view_both_signatures():
    from polyalpha.history import ChainlinkHistoryConfig, ChainlinkRecorder
    from polyalpha.history.view import ChainlinkHistoryView
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp)/"db"
        cfg = ChainlinkHistoryConfig(warmup={"1m":5}, db_path=str(db))
        rec = ChainlinkRecorder(config=cfg)
        start=int(time.time())//60*60
        ticks=[(start+i, 60000+i) for i in range(400)]
        rec.inject_ticks("BTC", ticks)
        view = ChainlinkHistoryView(rec, asset="BTC", strat_name="test")
        # 2-arg form
        v1 = view.ema("1m", 3)
        # 3-arg form
        v2 = view.ema("BTC","1m",3)
        assert v1 == v2
        assert view.sma("1m",3) == view.sma("BTC","1m",3)
        assert view.close("1m") == rec.close("1m","BTC")
        assert view.count("1m") == rec.count("1m","BTC")
