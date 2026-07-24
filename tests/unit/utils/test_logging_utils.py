"""
Logging utility tests — run with: pytest tests/unit/utils/test_logging_utils.py
"""

import logging
import pytest

from polyalpha.utils.logging_utils import log_call, get_logger


@pytest.mark.unit
class TestGetLogger:
    """Test get_logger convenience function."""

    def test_get_logger_auto_name(self):
        """get_logger() auto-detects the caller module name."""
        logger = get_logger()
        assert "test_logging_utils" in logger.name

    def test_get_logger_explicit_name(self):
        """get_logger('foo') returns logger named 'foo'."""
        logger = get_logger("polyalpha.Bot")
        assert logger.name == "polyalpha.Bot"

    def test_get_logger_returns_logger_instance(self):
        """get_logger always returns a logging.Logger."""
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)


@pytest.mark.unit
class TestLogCallDefaults:
    """Test @log_call with default parameters."""

    def test_no_parens_logs_entry(self, caplog):
        """@log_call without parens logs function entry at DEBUG."""
        caplog.set_level(logging.DEBUG)

        @log_call
        def greet(name: str):
            return f"Hello {name}"

        result = greet("World")
        assert result == "Hello World"

        assert any(
            "->" in rec.message and "name='World'" in rec.message
            for rec in caplog.records
        )

    def test_no_parens_no_result_logged(self, caplog):
        """@log_call without log_result does not log return value."""
        caplog.set_level(logging.DEBUG)

        @log_call
        def add(a: int, b: int):
            return a + b

        add(2, 3)
        exit_msgs = [r.message for r in caplog.records if "<-" in r.message]
        assert len(exit_msgs) == 0

    def test_skips_self_in_method(self, caplog):
        """@log_call skips 'self' from arg logging."""
        caplog.set_level(logging.DEBUG)

        class MyClass:
            @log_call
            def method(self, x: int):
                return x * 2

        MyClass().method(5)
        assert any("x=5" in r.message for r in caplog.records)
        assert not any("self=" in r.message for r in caplog.records)

    def test_preserves_function_metadata(self):
        """@log_call preserves __name__ and __doc__."""
        @log_call
        def my_func(x):
            """My docstring."""
            return x

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."

    def test_function_returns_normally(self):
        """Decorated function still returns correct value."""
        @log_call
        def add(a, b):
            return a + b

        assert add(1, 2) == 3


@pytest.mark.unit
class TestLogCallWithParens:
    """Test @log_call(...) with explicit parameters."""

    def test_info_level(self, caplog):
        """@log_call(level=logging.INFO) uses INFO level."""
        caplog.set_level(logging.DEBUG)

        @log_call(level=logging.INFO)
        def do_thing():
            return 42

        do_thing()
        assert any(
            rec.levelno == logging.INFO and "->" in rec.message
            for rec in caplog.records
        )

    def test_log_result_true(self, caplog):
        """@log_call(log_result=True) logs return value."""
        caplog.set_level(logging.DEBUG)

        @log_call(log_result=True)
        def add(a, b):
            return a + b

        add(2, 3)
        assert any("<-" in r.message and "5" in r.message for r in caplog.records)

    def test_log_result_false_default(self, caplog):
        """@log_call(log_result=False) does not log return value."""
        caplog.set_level(logging.DEBUG)

        @log_call(log_result=False)
        def add(a, b):
            return a + b

        add(2, 3)
        exit_msgs = [r.message for r in caplog.records if "<-" in r.message]
        assert len(exit_msgs) == 0

    def test_custom_skip_args(self, caplog):
        """@log_call(skip_args=('secret',)) hides that arg."""
        caplog.set_level(logging.DEBUG)

        @log_call(skip_args=("secret",))
        def process(secret: str, value: int):
            return value

        process("s3kr3t", 42)
        assert not any("secret=" in r.message for r in caplog.records)
        assert any("value=42" in r.message for r in caplog.records)

    def test_skip_market_by_default(self, caplog):
        """'market' arg is skipped by default."""
        caplog.set_level(logging.DEBUG)

        class FakeMarket:
            slug = "btc-updown-5m-123"

        @log_call
        def buy(market, side: str, amount: float):
            return "ok"

        buy(FakeMarket(), "UP", 42.0)
        assert not any("market=" in r.message for r in caplog.records)
        assert any("side='UP'" in r.message for r in caplog.records)
        assert any("amount=42.0" in r.message for r in caplog.records)


@pytest.mark.unit
class TestLogCallErrors:
    """Test @log_call error logging."""

    def test_logs_exception_at_error_level(self, caplog):
        """Exception is logged at ERROR level."""
        caplog.set_level(logging.DEBUG)

        @log_call(level=logging.INFO)
        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            fail()

        assert any(
            rec.levelno == logging.ERROR
            and "ValueError" in rec.message
            and "boom" in rec.message
            for rec in caplog.records
        )

    def test_re_raises_exception(self):
        """Exception is re-raised, not swallowed."""
        @log_call
        def fail():
            raise RuntimeError("should propagate")

        with pytest.raises(RuntimeError, match="should propagate"):
            fail()

    def test_log_error_false_silences_exception_logging(self, caplog):
        """@log_call(log_error=False) does not log exceptions."""
        caplog.set_level(logging.DEBUG)

        @log_call(log_error=False)
        def fail():
            raise ValueError("silent")

        with pytest.raises(ValueError):
            fail()

        error_msgs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_msgs) == 0


@pytest.mark.unit
class TestLogCallTruncation:
    """Test arg/result truncation for readability."""

    def test_truncates_long_string(self, caplog):
        """Long strings are truncated."""
        caplog.set_level(logging.DEBUG)

        @log_call
        def log_long(s: str):
            return "ok"

        long_str = "a" * 200
        log_long(long_str)
        assert any("..." in r.message for r in caplog.records)

    def test_truncates_long_list(self, caplog):
        """Long lists are truncated to max_items."""
        caplog.set_level(logging.DEBUG)

        @log_call
        def log_list(items: list):
            return len(items)

        log_list(list(range(100)))
        assert any("..." in r.message for r in caplog.records)

    def test_short_args_not_truncated(self, caplog):
        """Short strings show in full."""
        caplog.set_level(logging.DEBUG)

        @log_call
        def greet(name: str):
            return f"Hi {name}"

        greet("Alice")
        assert any("name='Alice'" in r.message for r in caplog.records)


@pytest.mark.unit
class TestLogCallImportFromPolyalpha:
    """Test that log_call is exported from the polyalpha package."""

    def test_import_from_polyalpha(self):
        """log_call can be imported directly from polyalpha."""
        from polyalpha import log_call as lc
        assert lc is log_call

    def test_import_from_init(self):
        """log_call exported in polyalpha.__init__."""
        import polyalpha
        assert hasattr(polyalpha, "log_call")
