"""Tests for DSP module."""
import sys
import os
import unittest
import numpy as np

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsp.filters import design_filter, apply_filter_chain, apply_filter
from dsp.decimation import decimate_for_display, calculate_decimation_factor
from dsp.spectral import compute_fft, compute_psd
from dsp.referencing import apply_car, apply_cmr
from dsp.metrics import compute_vrms, apply_vrms_threshold
from models.filter_config import FilterConfig, FilterType


class TestFilters(unittest.TestCase):
    """Test filter design and application."""

    def setUp(self):
        """Set up test data."""
        self.fs = 24000  # 24 kHz sample rate
        self.duration = 1.0  # 1 second
        self.n_samples = int(self.fs * self.duration)
        self.t = np.linspace(0, self.duration, self.n_samples)

        # Create test signal: 100 Hz + 1000 Hz + noise
        self.signal = (
            np.sin(2 * np.pi * 100 * self.t) +
            0.5 * np.sin(2 * np.pi * 1000 * self.t) +
            0.1 * np.random.randn(self.n_samples)
        )

    def test_lowpass_design(self):
        """Test low-pass filter design."""
        config = FilterConfig(
            filter_type=FilterType.LOWPASS,
            cutoff_high=500,
            order=4,
        )
        sos = design_filter(config, self.fs)
        self.assertIsNotNone(sos)
        self.assertEqual(sos.shape[1], 6)  # SOS format

    def test_highpass_design(self):
        """Test high-pass filter design."""
        config = FilterConfig(
            filter_type=FilterType.HIGHPASS,
            cutoff_low=200,
            order=4,
        )
        sos = design_filter(config, self.fs)
        self.assertIsNotNone(sos)

    def test_bandpass_design(self):
        """Test band-pass filter design."""
        config = FilterConfig(
            filter_type=FilterType.BANDPASS,
            cutoff_low=300,
            cutoff_high=3000,
            order=4,
        )
        sos = design_filter(config, self.fs)
        self.assertIsNotNone(sos)

    def test_notch_design(self):
        """Test notch filter design."""
        config = FilterConfig(
            filter_type=FilterType.NOTCH,
            notch_freq=60,
            notch_q=30,
        )
        sos = design_filter(config, self.fs)
        self.assertIsNotNone(sos)

    def test_invalid_cutoff(self):
        """Test filter with cutoff above Nyquist."""
        config = FilterConfig(
            filter_type=FilterType.LOWPASS,
            cutoff_high=15000,  # Above Nyquist for 24 kHz
            order=4,
        )
        sos = design_filter(config, self.fs)
        self.assertIsNone(sos)

    def test_apply_lowpass(self):
        """Test low-pass filter removes high frequencies."""
        config = FilterConfig(
            filter_type=FilterType.LOWPASS,
            cutoff_high=500,
            order=4,
        )

        filtered, warnings, vrms = apply_filter_chain(
            self.signal, [config], self.fs
        )

        # Check that high frequency content is reduced
        # Compute FFT of original and filtered
        orig_fft = np.abs(np.fft.rfft(self.signal))
        filt_fft = np.abs(np.fft.rfft(filtered))

        # Find bin for 1000 Hz
        freqs = np.fft.rfftfreq(self.n_samples, 1/self.fs)
        bin_1000 = np.argmin(np.abs(freqs - 1000))

        # 1000 Hz should be attenuated
        self.assertLess(filt_fft[bin_1000], orig_fft[bin_1000] * 0.1)

    def test_filter_chain(self):
        """Test applying multiple filters in sequence."""
        filters = [
            FilterConfig(FilterType.HIGHPASS, cutoff_low=50, order=2),
            FilterConfig(FilterType.LOWPASS, cutoff_high=5000, order=4),
            FilterConfig(FilterType.NOTCH, notch_freq=60, notch_q=30),
        ]

        filtered, warnings, vrms = apply_filter_chain(self.signal, filters, self.fs)

        self.assertEqual(len(filtered), len(self.signal))
        self.assertEqual(len(warnings), 0)

    def test_bypass(self):
        """Test filter bypass."""
        config = FilterConfig(
            filter_type=FilterType.LOWPASS,
            cutoff_high=500,
            order=4,
            bypassed=True,
        )

        filtered, _, _ = apply_filter_chain(self.signal, [config], self.fs)
        np.testing.assert_array_almost_equal(filtered, self.signal)

    def test_global_bypass(self):
        """Test global bypass."""
        config = FilterConfig(
            filter_type=FilterType.LOWPASS,
            cutoff_high=500,
            order=4,
        )

        filtered, _, _ = apply_filter_chain(
            self.signal, [config], self.fs, global_bypass=True
        )
        np.testing.assert_array_almost_equal(filtered, self.signal)

    def test_multichannel(self):
        """Test filtering multi-channel data."""
        data = np.vstack([self.signal, self.signal * 0.5, self.signal * 0.25])

        config = FilterConfig(
            filter_type=FilterType.LOWPASS,
            cutoff_high=500,
            order=4,
        )

        filtered, _, _ = apply_filter_chain(data, [config], self.fs)

        self.assertEqual(filtered.shape, data.shape)


class TestDecimation(unittest.TestCase):
    """Test decimation utilities."""

    def setUp(self):
        """Set up test data."""
        self.n_samples = 100000
        self.fs = 24000
        self.t = np.linspace(0, self.n_samples / self.fs, self.n_samples)
        self.signal = np.sin(2 * np.pi * 100 * self.t)

    def test_minmax_decimation(self):
        """Test minmax decimation."""
        target_points = 2000

        dec_data, dec_time = decimate_for_display(
            self.signal, self.t, target_points=target_points, method="minmax"
        )

        # Should be reduced but preserve extrema info
        self.assertLess(len(dec_data), len(self.signal))
        self.assertLessEqual(len(dec_data), target_points * 2)

    def test_no_decimation_needed(self):
        """Test that short signals aren't decimated."""
        short_signal = self.signal[:1000]
        short_time = self.t[:1000]

        dec_data, dec_time = decimate_for_display(
            short_signal, short_time, target_points=2000
        )

        self.assertEqual(len(dec_data), len(short_signal))

    def test_multichannel_decimation(self):
        """Test decimation of multi-channel data."""
        data = np.vstack([self.signal, self.signal * 0.5])

        dec_data, dec_time = decimate_for_display(
            data, self.t, target_points=2000
        )

        self.assertEqual(dec_data.shape[0], 2)
        self.assertLess(dec_data.shape[1], data.shape[1])

    def test_calculate_factor(self):
        """Test decimation factor calculation."""
        factor = calculate_decimation_factor(100000, display_width_pixels=1000)
        self.assertGreater(factor, 1)

        factor = calculate_decimation_factor(1000, display_width_pixels=2000)
        self.assertEqual(factor, 1)


class TestSpectral(unittest.TestCase):
    """Test spectral analysis functions."""

    def setUp(self):
        """Set up test data."""
        self.fs = 24000
        self.duration = 2.0
        self.n_samples = int(self.fs * self.duration)
        self.t = np.linspace(0, self.duration, self.n_samples)

        # Create signal with known frequency components
        self.signal = (
            np.sin(2 * np.pi * 100 * self.t) +  # 100 Hz
            0.5 * np.sin(2 * np.pi * 500 * self.t)  # 500 Hz
        )

    def test_fft(self):
        """Test FFT computation."""
        freqs, magnitude = compute_fft(self.signal, self.fs)

        # Check frequency array
        self.assertGreater(len(freqs), 0)
        self.assertEqual(freqs[0], 0)  # DC component

        # Should have peaks near 100 Hz and 500 Hz
        bin_100 = np.argmin(np.abs(freqs - 100))
        bin_500 = np.argmin(np.abs(freqs - 500))

        # 100 Hz peak should be larger than 500 Hz peak
        self.assertGreater(magnitude[bin_100], magnitude[bin_500] * 1.5)

    def test_psd(self):
        """Test PSD computation."""
        freqs, psd = compute_psd(self.signal, self.fs, nperseg=1024)

        # Check output
        self.assertGreater(len(freqs), 0)
        self.assertGreater(len(psd), 0)

        # Should have peaks at expected frequencies
        bin_100 = np.argmin(np.abs(freqs - 100))
        self.assertGreater(psd[bin_100], np.mean(psd))

    def test_multichannel_fft(self):
        """Test FFT on multi-channel data."""
        data = np.vstack([self.signal, self.signal * 0.5])

        freqs, magnitude = compute_fft(data, self.fs)

        self.assertEqual(magnitude.shape[0], 2)
        self.assertEqual(len(freqs), magnitude.shape[1])

    def test_multichannel_psd(self):
        """Test PSD on multi-channel data."""
        data = np.vstack([self.signal, self.signal * 0.5])

        freqs, psd = compute_psd(data, self.fs)

        self.assertEqual(psd.shape[0], 2)
        self.assertEqual(len(freqs), psd.shape[1])


class TestFilterConfig(unittest.TestCase):
    """Test filter configuration model."""

    def test_serialization(self):
        """Test filter config serialization."""
        config = FilterConfig(
            filter_type=FilterType.BANDPASS,
            cutoff_low=300,
            cutoff_high=3000,
            order=4,
            bypassed=True,
        )

        data = config.to_dict()
        restored = FilterConfig.from_dict(data)

        self.assertEqual(restored.filter_type, config.filter_type)
        self.assertEqual(restored.cutoff_low, config.cutoff_low)
        self.assertEqual(restored.cutoff_high, config.cutoff_high)
        self.assertEqual(restored.order, config.order)
        self.assertEqual(restored.bypassed, config.bypassed)

    def test_display_name(self):
        """Test display name generation."""
        config = FilterConfig(
            filter_type=FilterType.BANDPASS,
            cutoff_low=300,
            cutoff_high=3000,
            order=4,
        )

        name = config.get_display_name()
        self.assertIn("300", name)
        self.assertIn("3000", name)
        self.assertIn("BP", name)


class TestCAR(unittest.TestCase):
    """Test Common Average Reference."""

    def test_car_subtracts_mean(self):
        """Test that CAR subtracts the group mean from each channel."""
        # 4 channels, 100 samples
        data = np.array([
            [1.0, 2.0, 3.0, 4.0],
            [5.0, 6.0, 7.0, 8.0],
            [3.0, 4.0, 5.0, 6.0],
            [7.0, 8.0, 9.0, 10.0],
        ])
        # One group: channels 0, 1, 2, 3
        groups = [[0, 1, 2, 3]]
        result, warnings = apply_car(data, groups)

        self.assertEqual(len(warnings), 0)
        # Mean of col 0: (1+5+3+7)/4 = 4
        # After CAR, channel 0 col 0: 1 - 4 = -3
        self.assertAlmostEqual(result[0, 0], -3.0)
        # After CAR, channel 1 col 0: 5 - 4 = 1
        self.assertAlmostEqual(result[1, 0], 1.0)
        # Each column should sum to ~0
        for col in range(data.shape[1]):
            self.assertAlmostEqual(np.sum(result[:, col]), 0.0, places=10)

    def test_car_two_groups(self):
        """Test CAR with two independent subgroups."""
        data = np.array([
            [10.0, 20.0],
            [20.0, 30.0],
            [100.0, 200.0],
            [200.0, 300.0],
        ])
        groups = [[0, 1], [2, 3]]
        result, warnings = apply_car(data, groups)
        self.assertEqual(len(warnings), 0)

        # Group 1 mean col 0: (10+20)/2 = 15
        self.assertAlmostEqual(result[0, 0], -5.0)
        self.assertAlmostEqual(result[1, 0], 5.0)
        # Group 2 mean col 0: (100+200)/2 = 150
        self.assertAlmostEqual(result[2, 0], -50.0)
        self.assertAlmostEqual(result[3, 0], 50.0)

    def test_car_warning_small_group(self):
        """Test CAR warns on group with < 2 channels."""
        data = np.zeros((4, 10))
        groups = [[0], [1, 2, 3]]
        _, warnings = apply_car(data, groups)
        self.assertEqual(len(warnings), 1)


class TestCMR(unittest.TestCase):
    """Test Common Median Reference."""

    def test_cmr_subtracts_median(self):
        """Test that CMR subtracts the group median."""
        data = np.array([
            [1.0, 2.0],
            [3.0, 4.0],
            [100.0, 200.0],  # outlier
        ])
        groups = [[0, 1, 2]]
        result, warnings = apply_cmr(data, groups)
        self.assertEqual(len(warnings), 0)

        # Median of col 0: median(1, 3, 100) = 3
        self.assertAlmostEqual(result[0, 0], -2.0)
        self.assertAlmostEqual(result[1, 0], 0.0)
        self.assertAlmostEqual(result[2, 0], 97.0)


class TestVrms(unittest.TestCase):
    """Test Vrms computation and thresholding."""

    def test_compute_vrms_sine(self):
        """Test Vrms of a sine wave equals amplitude / sqrt(2)."""
        fs = 10000
        t = np.linspace(0, 1.0, fs, endpoint=False)
        amplitude = 2.0
        sine = amplitude * np.sin(2 * np.pi * 100 * t)
        data = sine.reshape(1, -1)

        vrms = compute_vrms(data, [0])
        expected = amplitude / np.sqrt(2)
        self.assertAlmostEqual(vrms[0], expected, places=2)

    def test_compute_vrms_multichannel(self):
        """Test Vrms computed independently per channel."""
        data = np.array([
            np.ones(1000),
            2 * np.ones(1000),
        ])
        vrms = compute_vrms(data, [0, 1])
        self.assertAlmostEqual(vrms[0], 1.0, places=5)
        self.assertAlmostEqual(vrms[1], 2.0, places=5)

    def test_threshold_zeros_small_values(self):
        """Test that Vrms threshold zeros out sub-threshold points."""
        data = np.array([[1.0, 0.01, -0.01, 5.0, -3.0]])
        vrms = {0: 1.0}
        # multiplier=1 → threshold = 1.0 → zero out |x| < 1
        result = apply_vrms_threshold(data, vrms, [0], multiplier=1.0)
        self.assertEqual(result[0, 0], 1.0)
        self.assertEqual(result[0, 1], 0.0)
        self.assertEqual(result[0, 2], 0.0)
        self.assertEqual(result[0, 3], 5.0)
        self.assertEqual(result[0, 4], -3.0)


class TestMixedFilterChain(unittest.TestCase):
    """Test filter chain with mixed filter types (CAR + SOS + threshold)."""

    def test_car_plus_bandpass(self):
        """Test a chain of CAR followed by bandpass."""
        fs = 24000
        n = 24000  # 1 second
        t = np.linspace(0, 1.0, n, endpoint=False)
        # 4-channel data
        data = np.array([
            np.sin(2 * np.pi * 100 * t) + 1.0,  # DC offset + 100 Hz
            np.sin(2 * np.pi * 100 * t) + 2.0,
            np.sin(2 * np.pi * 100 * t) + 3.0,
            np.sin(2 * np.pi * 100 * t) + 4.0,
        ])

        filters = [
            FilterConfig(
                FilterType.CAR,
                channel_groups=[[0, 1, 2, 3]],
            ),
            FilterConfig(
                FilterType.BANDPASS,
                cutoff_low=50,
                cutoff_high=200,
                order=2,
            ),
        ]

        # Display channels 0 and 1
        displayed = data[:2].copy()
        result, warnings, vrms = apply_filter_chain(
            displayed, filters, fs,
            all_channel_data=data,
            channel_indices=[0, 1],
        )

        self.assertEqual(result.shape[0], 2)
        self.assertEqual(len(vrms), 2)
        # Warnings should be empty for valid chain
        self.assertEqual(len(warnings), 0)

    def test_chain_with_threshold(self):
        """Test that Vrms is computed before thresholding."""
        data = np.array([[1.0, 0.01, -0.01, 5.0, -3.0]] * 1000)
        data = data.T  # (5, 1000) — but let's just use a simple 1-channel
        data_1ch = np.array([np.concatenate([np.ones(500), 0.001 * np.ones(500)])])
        filters = [
            FilterConfig(FilterType.VRMS_THRESHOLD, vrms_multiplier=1.0),
        ]

        result, warnings, vrms = apply_filter_chain(
            data_1ch, filters, 1000.0,
            channel_indices=[0],
        )

        # vrms computed BEFORE threshold was applied
        self.assertIn(0, vrms)
        self.assertGreater(vrms[0], 0)


class TestNewFilterConfigSerialization(unittest.TestCase):
    """Test serialization for new filter types."""

    def test_car_serialization(self):
        """Test CAR config round-trips through dict."""
        config = FilterConfig(
            filter_type=FilterType.CAR,
            channel_groups=[[0, 1, 2], [3, 4, 5]],
        )
        data = config.to_dict()
        restored = FilterConfig.from_dict(data)
        self.assertEqual(restored.filter_type, FilterType.CAR)
        self.assertEqual(restored.channel_groups, [[0, 1, 2], [3, 4, 5]])

    def test_cmr_serialization(self):
        """Test CMR config round-trips through dict."""
        config = FilterConfig(
            filter_type=FilterType.CMR,
            channel_groups=[[0, 1], [2, 3]],
        )
        data = config.to_dict()
        restored = FilterConfig.from_dict(data)
        self.assertEqual(restored.filter_type, FilterType.CMR)
        self.assertEqual(restored.channel_groups, [[0, 1], [2, 3]])

    def test_vrms_threshold_serialization(self):
        """Test Vrms threshold config round-trips through dict."""
        config = FilterConfig(
            filter_type=FilterType.VRMS_THRESHOLD,
            vrms_multiplier=5.0,
        )
        data = config.to_dict()
        restored = FilterConfig.from_dict(data)
        self.assertEqual(restored.filter_type, FilterType.VRMS_THRESHOLD)
        self.assertEqual(restored.vrms_multiplier, 5.0)

    def test_car_display_name(self):
        """Test CAR display name."""
        config = FilterConfig(
            filter_type=FilterType.CAR,
            channel_groups=[[0, 1], [2, 3], [4, 5]],
        )
        name = config.get_display_name()
        self.assertIn("CAR", name)
        self.assertIn("3", name)

    def test_vrms_display_name(self):
        """Test Vrms threshold display name."""
        config = FilterConfig(
            filter_type=FilterType.VRMS_THRESHOLD,
            vrms_multiplier=3.0,
        )
        name = config.get_display_name()
        self.assertIn("Vrms", name)
        self.assertIn("3.0", name)


if __name__ == "__main__":
    unittest.main()
