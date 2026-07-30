"""
Unit tests for volume calculations.
"""

import pytest
from polyalpha.calculations.volume_calculations import VolumeCalculations, VolumeTrend


class TestVolumeCalculations:
    """Test suite for VolumeCalculations class."""
    
    def test_vol_ratio_basic(self):
        """Test basic volume ratio calculation."""
        data = [100.0, 120.0, 110.0, 130.0]
        result = VolumeCalculations.vol_ratio(data, period=3)
        assert result is not None
        # Current 130 / avg of [100, 120, 110] = 130 / 110 ≈ 1.18
        assert abs(result - 1.18) < 0.01
    
    def test_vol_ratio_higher_period(self):
        """Test volume ratio with higher period."""
        data = [100.0, 120.0, 110.0, 130.0, 140.0, 150.0]
        result = VolumeCalculations.vol_ratio(data, period=5)
        assert result is not None
        # Current 150 / avg of [100, 120, 110, 130, 140] = 150 / 120 = 1.25
        assert abs(result - 1.25) < 0.01
    
    def test_vol_ratio_insufficient_data(self):
        """Test volume ratio with insufficient data."""
        data = [100.0]
        result = VolumeCalculations.vol_ratio(data, period=3)
        assert result is None
    
    def test_vol_ratio_zero_average(self):
        """Test volume ratio with zero average volume."""
        data = [0.0, 0.0, 0.0, 130.0]
        result = VolumeCalculations.vol_ratio(data, period=3)
        assert result is None
    
    def test_volume_trend_increasing(self):
        """Test volume trend detection for increasing volume."""
        data = [100.0, 120.0, 110.0, 130.0]
        result = VolumeCalculations.volume_trend(data, period=3, threshold=0.1)
        assert result == VolumeTrend.INCREASING
    
    def test_volume_trend_decreasing(self):
        """Test volume trend detection for decreasing volume."""
        data = [100.0, 90.0, 95.0, 80.0]
        result = VolumeCalculations.volume_trend(data, period=3, threshold=0.1)
        assert result == VolumeTrend.DECREASING
    
    def test_volume_trend_stable(self):
        """Test volume trend detection for stable volume."""
        data = [100.0, 101.0, 99.0, 100.0]
        result = VolumeCalculations.volume_trend(data, period=3, threshold=0.1)
        assert result == VolumeTrend.STABLE
    
    def test_volume_trend_insufficient_data(self):
        """Test volume trend with insufficient data."""
        data = [100.0]
        result = VolumeCalculations.volume_trend(data, period=3)
        assert result == VolumeTrend.STABLE
    
    def test_volume_surge_detected(self):
        """Test volume surge detection."""
        data = [100.0, 110.0, 105.0, 120.0, 250.0]
        result = VolumeCalculations.volume_surge(data, multiplier=2.0, period=4)
        assert result is True
    
    def test_volume_surge_not_detected(self):
        """Test volume surge not detected."""
        data = [100.0, 110.0, 105.0, 120.0, 130.0]
        result = VolumeCalculations.volume_surge(data, multiplier=2.0, period=4)
        assert result is False
    
    def test_volume_surge_insufficient_data(self):
        """Test volume surge with insufficient data."""
        data = [100.0]
        result = VolumeCalculations.volume_surge(data, multiplier=2.0, period=4)
        assert result is None
    
    def test_volume_surge_high_multiplier(self):
        """Test volume surge with high multiplier."""
        data = [100.0, 110.0, 105.0, 120.0, 250.0]
        result = VolumeCalculations.volume_surge(data, multiplier=3.0, period=4)
        assert result is False  # 250/108.75 ≈ 2.3 < 3.0
    
    def test_avg_volume_basic(self):
        """Test average volume calculation."""
        data = [100.0, 120.0, 110.0, 130.0]
        result = VolumeCalculations.avg_volume(data, period=3)
        assert result is not None
        assert abs(result - 120.0) < 0.01  # (100 + 120 + 110 + 130) / 4 = 115
    
    def test_avg_volume_partial_window(self):
        """Test average volume with partial window."""
        data = [100.0, 120.0, 110.0]
        result = VolumeCalculations.avg_volume(data, period=10)
        assert result is not None
        assert abs(result - 110.0) < 0.01  # (100 + 120 + 110) / 3
    
    def test_avg_volume_no_data(self):
        """Test average volume with no data."""
        data = []
        result = VolumeCalculations.avg_volume(data, period=5)
        assert result is None
    
    def test_volume_momentum_positive(self):
        """Test volume momentum with positive change."""
        data = [100.0, 120.0, 110.0, 130.0]
        result = VolumeCalculations.volume_momentum(data, period=3)
        assert result is not None
        assert result > 0  # Positive momentum
    
    def test_volume_momentum_negative(self):
        """Test volume momentum with negative change."""
        data = [100.0, 90.0, 95.0, 80.0]
        result = VolumeCalculations.volume_momentum(data, period=3)
        assert result is not None
        assert result < 0  # Negative momentum
    
    def test_volume_momentum_insufficient_data(self):
        """Test volume momentum with insufficient data."""
        data = [100.0]
        result = VolumeCalculations.volume_momentum(data, period=3)
        assert result is None
    
    def test_relative_volume_above_percentile(self):
        """Test relative volume above percentile."""
        data = [100.0, 110.0, 105.0, 120.0, 130.0]
        result = VolumeCalculations.relative_volume(data, percentile=0.75, period=4)
        assert result is True  # 130 is above 75th percentile of [100, 110, 105, 120]
    
    def test_relative_volume_below_percentile(self):
        """Test relative volume below percentile."""
        data = [100.0, 110.0, 105.0, 120.0, 103.0]
        result = VolumeCalculations.relative_volume(data, percentile=0.75, period=4)
        assert result is False  # 103 is below 75th percentile
    
    def test_relative_volume_insufficient_data(self):
        """Test relative volume with insufficient data."""
        data = [100.0]
        result = VolumeCalculations.relative_volume(data, percentile=0.75)
        assert result is None
    
    def test_relative_volume_high_percentile(self):
        """Test relative volume with high percentile."""
        data = [100.0, 110.0, 105.0, 120.0, 130.0]
        result = VolumeCalculations.relative_volume(data, percentile=0.95, period=4)
        # With 4 data points [100, 110, 105, 120], 95th percentile would be close to max
        # 130 is the current value and it's higher than all previous values
        # So it should be above the 95th percentile
        assert result is True  # 130 is above 95th percentile of [100, 110, 105, 120]
    
    def test_edge_case_constant_volume(self):
        """Test calculations with constant volume."""
        data = [100.0, 100.0, 100.0, 100.0]
        
        assert VolumeCalculations.vol_ratio(data, period=3) == 1.0
        assert VolumeCalculations.volume_trend(data, period=2) == VolumeTrend.STABLE
        assert VolumeCalculations.volume_surge(data, multiplier=2.0) is False
        assert VolumeCalculations.avg_volume(data, period=4) == 100.0
    
    def test_edge_case_zero_volume(self):
        """Test calculations with zero volume."""
        data = [0.0, 0.0, 0.0, 0.0]
        
        # vol_ratio should return None due to division by zero
        assert VolumeCalculations.vol_ratio(data, period=3) is None
        assert VolumeCalculations.avg_volume(data, period=4) == 0.0
    
    def test_edge_case_single_data_point(self):
        """Test calculations with single data point."""
        data = [100.0]
        
        assert VolumeCalculations.vol_ratio(data, period=3) is None
        assert VolumeCalculations.volume_trend(data, period=3) == VolumeTrend.STABLE
        assert VolumeCalculations.volume_surge(data, period=3) is None
        assert VolumeCalculations.avg_volume(data, period=3) == 100.0
        assert VolumeCalculations.volume_momentum(data, period=3) is None
        assert VolumeCalculations.relative_volume(data, period=3) is None
    
    def test_edge_case_spike_detection(self):
        """Test spike detection with various multipliers."""
        base_data = [100.0, 105.0, 98.0, 102.0, 106.0]
        spike_data = base_data + [300.0]  # Large spike
        
        # Detect spike with lower multiplier
        assert VolumeCalculations.volume_surge(spike_data, multiplier=2.0, period=5) is True
        
        # Don't detect spike with very high multiplier
        assert VolumeCalculations.volume_surge(spike_data, multiplier=5.0, period=5) is False
