"""
Retry decorator tests — run with: pytest tests/unit/trading/test_retry.py
"""

import time
import pytest

from polyalpha.trading.retry import retry_on_error, retry_with_jitter
from polyalpha.core import TransientError, NetworkError


@pytest.mark.unit
class TestRetryOnError:
    """Test retry_on_error decorator."""

    def test_retry_on_success_first_attempt(self):
        """Test function succeeds on first attempt."""
        @retry_on_error(max_attempts=3, delay=0.01)
        def succeed_func():
            return "success"
        
        result = succeed_func()
        assert result == "success"

    def test_retry_on_success_after_retry(self):
        """Test function succeeds after retry."""
        attempts = [0]
        
        @retry_on_error(max_attempts=3, delay=0.01)
        def fail_then_succeed():
            attempts[0] += 1
            if attempts[0] < 2:
                raise TransientError("Temporary failure")
            return "success"
        
        result = fail_then_succeed()
        assert result == "success"
        assert attempts[0] == 2

    def test_retry_on_max_attempts_exceeded(self):
        """Test function fails after max attempts."""
        @retry_on_error(max_attempts=3, delay=0.01)
        def always_fail():
            raise TransientError("Always fails")
        
        with pytest.raises(TransientError, match="Always fails"):
            always_fail()

    def test_retry_on_specific_exception(self):
        """Test retry only on specified exception types."""
        @retry_on_error(max_attempts=3, delay=0.01, retry_on=(ValueError,))
        def raise_value_error():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            raise_value_error()

    def test_retry_on_unexpected_exception_no_retry(self):
        """Test unexpected exceptions are not retried."""
        attempts = [0]
        
        @retry_on_error(max_attempts=3, delay=0.01)
        def raise_unexpected():
            attempts[0] += 1
            raise RuntimeError("Unexpected error")
        
        with pytest.raises(RuntimeError):
            raise_unexpected()
        
        # Should only attempt once
        assert attempts[0] == 1

    def test_retry_on_ignore_exception(self):
        """Test ignored exceptions are not retried."""
        attempts = [0]
        
        @retry_on_error(
            max_attempts=3,
            delay=0.01,
            retry_on=(TransientError,),
            ignore_on=(ValueError,)
        )
        def raise_ignored():
            attempts[0] += 1
            raise ValueError("Ignored error")
        
        with pytest.raises(ValueError):
            raise_ignored()
        
        # Should only attempt once
        assert attempts[0] == 1

    def test_retry_on_network_error(self):
        """Test retry on NetworkError."""
        attempts = [0]
        
        @retry_on_error(max_attempts=3, delay=0.01)
        def raise_network_error():
            attempts[0] += 1
            if attempts[0] < 2:
                raise NetworkError("Network issue")
            return "success"
        
        result = raise_network_error()
        assert result == "success"
        assert attempts[0] == 2

    def test_retry_on_timeout_error(self):
        """Test retry on TimeoutError."""
        attempts = [0]
        
        @retry_on_error(max_attempts=3, delay=0.01)
        def raise_timeout():
            attempts[0] += 1
            if attempts[0] < 2:
                raise TimeoutError("Timeout")
            return "success"
        
        result = raise_timeout()
        assert result == "success"
        assert attempts[0] == 2

    def test_retry_exponential_backoff(self):
        """Test exponential backoff delay calculation."""
        delays = []
        
        @retry_on_error(max_attempts=4, delay=0.1, backoff_factor=2.0)
        def fail_with_delay_tracking():
            raise TransientError("Fail")
        
        # Mock time.sleep to capture delays
        original_sleep = time.sleep
        def mock_sleep(delay):
            delays.append(delay)
        
        time.sleep = mock_sleep
        try:
            with pytest.raises(TransientError):
                fail_with_delay_tracking()
        finally:
            time.sleep = original_sleep
        
        # Expected delays: 0.1, 0.2, 0.4 (exponential backoff)
        assert len(delays) == 3
        assert delays[0] == pytest.approx(0.1)
        assert delays[1] == pytest.approx(0.2)
        assert delays[2] == pytest.approx(0.4)

    def test_retry_custom_delay(self):
        """Test custom initial delay."""
        delays = []
        
        @retry_on_error(max_attempts=3, delay=0.5)
        def fail_func():
            raise TransientError("Fail")
        
        original_sleep = time.sleep
        def mock_sleep(delay):
            delays.append(delay)
        
        time.sleep = mock_sleep
        try:
            with pytest.raises(TransientError):
                fail_func()
        finally:
            time.sleep = original_sleep
        
        assert delays[0] == pytest.approx(0.5)

    def test_retry_preserves_function_metadata(self):
        """Test that decorator preserves function metadata."""
        @retry_on_error(max_attempts=3)
        def example_func(x, y):
            """Example function docstring."""
            return x + y
        
        assert example_func.__name__ == "example_func"
        assert example_func.__doc__ == "Example function docstring."

    def test_retry_with_function_args(self):
        """Test retry with function arguments."""
        @retry_on_error(max_attempts=3, delay=0.01)
        def add_with_retry(x, y):
            if x + y == 0:
                raise TransientError("Zero sum")
            return x + y
        
        result = add_with_retry(5, 3)
        assert result == 8

    def test_retry_with_function_kwargs(self):
        """Test retry with function keyword arguments."""
        @retry_on_error(max_attempts=3, delay=0.01)
        def multiply_with_retry(x, y=1):
            if x * y == 0:
                raise TransientError("Zero product")
            return x * y
        
        result = multiply_with_retry(5, y=3)
        assert result == 15

    def test_retry_zero_attempts(self):
        """Test with max_attempts=1 (no retries)."""
        @retry_on_error(max_attempts=1, delay=0.01)
        def fail_immediately():
            raise TransientError("Fail")
        
        with pytest.raises(TransientError):
            fail_immediately()

    def test_retry_default_parameters(self):
        """Test default parameters work correctly."""
        @retry_on_error()
        def succeed():
            return "success"
        
        result = succeed()
        assert result == "success"


@pytest.mark.unit
class TestRetryWithJitter:
    """Test retry_with_jitter decorator."""

    def test_jitter_on_success_first_attempt(self):
        """Test function succeeds on first attempt with jitter."""
        @retry_with_jitter(max_attempts=3, delay=0.01, jitter=0.1)
        def succeed_func():
            return "success"
        
        result = succeed_func()
        assert result == "success"

    def test_jitter_on_success_after_retry(self):
        """Test function succeeds after retry with jitter."""
        attempts = [0]
        
        @retry_with_jitter(max_attempts=3, delay=0.01, jitter=0.1)
        def fail_then_succeed():
            attempts[0] += 1
            if attempts[0] < 2:
                raise TransientError("Temporary failure")
            return "success"
        
        result = fail_then_succeed()
        assert result == "success"
        assert attempts[0] == 2

    def test_jitter_max_attempts_exceeded(self):
        """Test function fails after max attempts with jitter."""
        @retry_with_jitter(max_attempts=3, delay=0.01, jitter=0.1)
        def always_fail():
            raise TransientError("Always fails")
        
        with pytest.raises(TransientError, match="Always fails"):
            always_fail()

    def test_jitter_adds_randomness(self):
        """Test that jitter adds randomness to delays."""
        delays = []
        
        @retry_with_jitter(max_attempts=4, delay=0.1, backoff_factor=2.0, jitter=0.2)
        def fail_func():
            raise TransientError("Fail")
        
        original_sleep = time.sleep
        def mock_sleep(delay):
            delays.append(delay)
        
        time.sleep = mock_sleep
        try:
            with pytest.raises(TransientError):
                fail_func()
        finally:
            time.sleep = original_sleep
        
        # Delays should vary due to jitter
        assert len(delays) == 3
        # Base delays: 0.1, 0.2, 0.4
        # With 20% jitter, actual delays should be within ±20%
        assert 0.08 <= delays[0] <= 0.12
        assert 0.16 <= delays[1] <= 0.24
        assert 0.32 <= delays[2] <= 0.48

    def test_jitter_zero(self):
        """Test with zero jitter (no randomness)."""
        delays = []
        
        @retry_with_jitter(max_attempts=3, delay=0.1, jitter=0.0)
        def fail_func():
            raise TransientError("Fail")
        
        original_sleep = time.sleep
        def mock_sleep(delay):
            delays.append(delay)
        
        time.sleep = mock_sleep
        try:
            with pytest.raises(TransientError):
                fail_func()
        finally:
            time.sleep = original_sleep
        
        # Delays should be exact without jitter
        assert delays[0] == pytest.approx(0.1)
        assert delays[1] == pytest.approx(0.2)

    def test_jitter_negative_delay_prevented(self):
        """Test that jitter cannot make delay negative."""
        delays = []
        
        @retry_with_jitter(max_attempts=3, delay=0.01, jitter=10.0)
        def fail_func():
            raise TransientError("Fail")
        
        original_sleep = time.sleep
        def mock_sleep(delay):
            delays.append(delay)
        
        time.sleep = mock_sleep
        try:
            with pytest.raises(TransientError):
                fail_func()
        finally:
            time.sleep = original_sleep
        
        # All delays should be non-negative
        for delay in delays:
            assert delay >= 0

    def test_jitter_preserves_function_metadata(self):
        """Test that jitter decorator preserves function metadata."""
        @retry_with_jitter(max_attempts=3, jitter=0.1)
        def example_func(x):
            """Example function docstring."""
            return x * 2
        
        assert example_func.__name__ == "example_func"
        assert example_func.__doc__ == "Example function docstring."

    def test_jitter_custom_retry_on(self):
        """Test custom retry_on exception types with jitter."""
        @retry_with_jitter(
            max_attempts=3,
            delay=0.01,
            jitter=0.1,
            retry_on=(ValueError,)
        )
        def raise_value_error():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            raise_value_error()

    def test_jitter_unexpected_exception_no_retry(self):
        """Test unexpected exceptions are not retried with jitter."""
        attempts = [0]
        
        @retry_with_jitter(max_attempts=3, delay=0.01, jitter=0.1)
        def raise_unexpected():
            attempts[0] += 1
            raise RuntimeError("Unexpected error")
        
        with pytest.raises(RuntimeError):
            raise_unexpected()
        
        assert attempts[0] == 1


@pytest.mark.unit
class TestRetryEdgeCases:
    """Test edge cases for retry decorators."""

    def test_retry_with_no_exception_types(self):
        """Test retry with empty retry_on tuple."""
        @retry_on_error(max_attempts=3, delay=0.01, retry_on=())
        def raise_error():
            raise TransientError("Fail")
        
        # Should not retry since no exception types specified
        with pytest.raises(TransientError):
            raise_error()

    def test_retry_function_returns_none(self):
        """Test retry when function returns None."""
        @retry_on_error(max_attempts=3, delay=0.01)
        def return_none():
            return None
        
        result = return_none()
        assert result is None

    def test_retry_with_class_method(self):
        """Test retry decorator on class method."""
        class TestClass:
            @retry_on_error(max_attempts=3, delay=0.01)
            def method_with_retry(self, x):
                if x < 0:
                    raise TransientError("Negative value")
                return x * 2
        
        obj = TestClass()
        result = obj.method_with_retry(5)
        assert result == 10

    def test_retry_with_static_method(self):
        """Test retry decorator on static method."""
        class TestClass:
            @staticmethod
            @retry_on_error(max_attempts=3, delay=0.01)
            def static_method(x):
                if x < 0:
                    raise TransientError("Negative value")
                return x * 2
        
        result = TestClass.static_method(5)
        assert result == 10

    def test_retry_nested_decorators(self):
        """Test retry with other decorators."""
        def uppercase_decorator(func):
            def wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                return result.upper()
            return wrapper
        
        @uppercase_decorator
        @retry_on_error(max_attempts=3, delay=0.01)
        def get_string():
            return "success"
        
        result = get_string()
        assert result == "SUCCESS"
