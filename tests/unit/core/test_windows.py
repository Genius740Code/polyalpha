"""
Unit tests for TimeWindow class.
"""

import time
import unittest
from polyalpha.windows import TimeWindow


class TestTimeWindow(unittest.TestCase):
    """Test TimeWindow functionality."""

    def setUp(self):
        """Set up a fresh TimeWindow for each test."""
        self.window = TimeWindow(max_age=120)

    def test_initial_state(self):
        """Test initial state of TimeWindow."""
        self.assertIsNone(self.window.value)
        self.assertEqual(len(self.window), 0)
        self.assertEqual(self.window.age_s, float('inf'))

    def test_update_single_value(self):
        """Test updating with a single value."""
        self.window.update(100.0)
        self.assertEqual(self.window.value, 100.0)
        self.assertEqual(len(self.window), 1)
        self.assertLess(self.window.age_s, 1.0)

    def test_update_multiple_values(self):
        """Test updating with multiple values."""
        values = [100.0, 105.0, 110.0, 115.0]
        for v in values:
            self.window.update(v)
            time.sleep(0.01)  # Small delay to ensure different timestamps
        
        self.assertEqual(self.window.value, 115.0)
        self.assertEqual(len(self.window), 4)

    def test_change_pct_basic(self):
        """Test basic percentage change calculation."""
        self.window.update(100.0)
        time.sleep(0.05)
        self.window.update(110.0)
        
        # 10% increase should give approximately 0.10
        change = self.window.change_pct(0.1)  # 0.1 seconds window
        self.assertIsNotNone(change)
        self.assertAlmostEqual(change, 0.10, places=1)

    def test_change_pct_decrease(self):
        """Test percentage change for decreasing values."""
        self.window.update(100.0)
        time.sleep(0.05)
        self.window.update(90.0)
        
        # 10% decrease should give approximately -0.10
        change = self.window.change_pct(0.1)
        self.assertIsNotNone(change)
        self.assertAlmostEqual(change, -0.10, places=1)

    def test_change_pct_insufficient_data(self):
        """Test change_pct with insufficient data."""
        self.window.update(100.0)
        
        # Request change over 30 seconds with only 1 data point
        # Should return None since we need at least 2 points for valid change calculation
        change = self.window.change_pct(30)
        self.assertIsNone(change, "Should return None with only 1 data point")

    def test_change_pct_no_data(self):
        """Test change_pct with no data."""
        change = self.window.change_pct(30)
        self.assertIsNone(change)

    def test_change_pct_different_periods(self):
        """Test change_pct over different time periods."""
        # Add data points over time
        for i in range(5):
            self.window.update(100.0 + i * 10)
            time.sleep(0.1)
        
        # Test different time windows
        change_1s = self.window.change_pct(1.0)
        change_2s = self.window.change_pct(2.0)
        
        self.assertIsNotNone(change_1s)
        self.assertIsNotNone(change_2s)
        # Longer window should generally show more change or equal
        self.assertGreaterEqual(abs(change_2s), abs(change_1s))

    def test_pruning_old_data(self):
        """Test that old data is pruned based on max_age."""
        window = TimeWindow(max_age=0.5)  # 0.5 second max age
        
        window.update(100.0)
        time.sleep(0.6)
        window.update(200.0)
        
        # Old data should be pruned
        self.assertEqual(len(window), 1)
        self.assertEqual(window.value, 200.0)

    def test_age_s_calculation(self):
        """Test age_s calculation."""
        self.window.update(100.0)
        time.sleep(0.1)
        
        age = self.window.age_s
        self.assertGreater(age, 0.09)
        self.assertLess(age, 0.2)

    def test_age_s_no_data(self):
        """Test age_s with no data."""
        age = self.window.age_s
        self.assertEqual(age, float('inf'))

    def test_get_value_at(self):
        """Test getting value at specific time in past."""
        self.window.update(100.0)
        time.sleep(0.1)
        self.window.update(110.0)
        time.sleep(0.1)
        self.window.update(120.0)
        
        # Get value 0.15 seconds ago (should be around 110.0)
        value = self.window.get_value_at(0.15)
        self.assertIsNotNone(value)
        self.assertAlmostEqual(value, 110.0, places=0)

    def test_get_value_at_no_data(self):
        """Test get_value_at with no data."""
        value = self.window.get_value_at(1.0)
        self.assertIsNone(value)

    def test_clear(self):
        """Test clearing the window."""
        self.window.update(100.0)
        self.window.update(110.0)
        
        self.assertEqual(len(self.window), 2)
        
        self.window.clear()
        
        self.assertEqual(len(self.window), 0)
        self.assertIsNone(self.window.value)
        self.assertEqual(self.window.age_s, float('inf'))

    def test_thread_safety(self):
        """Test basic thread safety with concurrent updates."""
        import threading
        
        def update_window(value):
            for i in range(100):
                self.window.update(value + i)
                time.sleep(0.001)
        
        thread1 = threading.Thread(target=update_window, args=(100,))
        thread2 = threading.Thread(target=update_window, args=(200,))
        
        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()
        
        # Should have some data without errors
        self.assertGreater(len(self.window), 0)
        self.assertIsNotNone(self.window.value)

    def test_zero_division_protection(self):
        """Test that zero values don't cause division errors."""
        self.window.update(0.0)
        time.sleep(0.05)
        self.window.update(100.0)
        
        # Should handle zero gracefully
        change = self.window.change_pct(0.1)
        # Either None or some reasonable value (not crash)
        self.assertTrue(change is None or isinstance(change, (int, float)))

    def test_negative_values(self):
        """Test handling of negative values."""
        self.window.update(-100.0)
        time.sleep(0.05)
        self.window.update(-90.0)
        
        change = self.window.change_pct(0.1)
        self.assertIsNotNone(change)
        # -90 to -100 is a decrease, so change should be negative
        self.assertLess(change, 0)


if __name__ == "__main__":
    unittest.main()
