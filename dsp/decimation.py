"""Decimation utilities for efficient plotting."""
from typing import Tuple
import numpy as np
from scipy import signal


def decimate_for_display(
    data: np.ndarray,
    time_axis: np.ndarray,
    target_points: int = 4000,
    method: str = "minmax",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Decimate data for display while preserving visual features.

    For time series visualization, we want to preserve peaks and troughs
    so the visual appearance matches the full-resolution data.

    Args:
        data: Input data, shape (n_channels, n_samples) or (n_samples,)
        time_axis: Time values for each sample
        target_points: Target number of points for display
        method: 'minmax' preserves peaks (recommended), 'decimate' uses scipy

    Returns:
        Tuple of (decimated_data, decimated_time)
    """
    if data.ndim == 1:
        data = data.reshape(1, -1)
        was_1d = True
    else:
        was_1d = False

    n_channels, n_samples = data.shape

    if n_samples <= target_points:
        # No decimation needed
        if was_1d:
            return data[0], time_axis
        return data, time_axis

    if method == "minmax":
        # MinMax decimation: preserve peaks and troughs
        # Each output point represents a bin of input points
        # We output both min and max per bin to preserve visual shape

        # Calculate points per bin (we'll output 2 points per bin)
        points_per_bin = n_samples / (target_points // 2)
        n_bins = int(n_samples / points_per_bin)

        if n_bins < 2:
            n_bins = 2

        # Create output arrays (2 points per bin: min and max)
        out_samples = n_bins * 2
        out_data = np.zeros((n_channels, out_samples), dtype=data.dtype)
        out_time = np.zeros(out_samples, dtype=time_axis.dtype)

        for i in range(n_bins):
            start_idx = int(i * points_per_bin)
            end_idx = int((i + 1) * points_per_bin)
            end_idx = min(end_idx, n_samples)

            if start_idx >= end_idx:
                continue

            bin_data = data[:, start_idx:end_idx]
            bin_time = time_axis[start_idx:end_idx]

            # Find min and max indices for each channel
            min_vals = np.min(bin_data, axis=1)
            max_vals = np.max(bin_data, axis=1)

            # Store min first, then max (maintains visual order)
            out_data[:, 2 * i] = min_vals
            out_data[:, 2 * i + 1] = max_vals

            # Time points at bin boundaries
            out_time[2 * i] = bin_time[0]
            out_time[2 * i + 1] = bin_time[-1] if len(bin_time) > 1 else bin_time[0]

        if was_1d:
            return out_data[0], out_time
        return out_data, out_time

    elif method == "decimate":
        # Standard scipy decimation with anti-aliasing
        factor = max(1, n_samples // target_points)

        if factor == 1:
            if was_1d:
                return data[0], time_axis
            return data, time_axis

        out_data = np.zeros(
            (n_channels, n_samples // factor), dtype=np.float64
        )

        for i in range(n_channels):
            # Use FIR filter for stability
            out_data[i] = signal.decimate(
                data[i].astype(np.float64), factor, ftype="fir", zero_phase=True
            )

        out_time = time_axis[::factor][: out_data.shape[1]]

        if was_1d:
            return out_data[0], out_time
        return out_data, out_time

    else:
        # Simple subsampling (not recommended but fast)
        factor = max(1, n_samples // target_points)
        out_data = data[:, ::factor]
        out_time = time_axis[::factor]

        if was_1d:
            return out_data[0], out_time
        return out_data, out_time


def calculate_decimation_factor(
    n_samples: int, display_width_pixels: int = 2000
) -> int:
    """
    Calculate appropriate decimation factor based on display constraints.

    Args:
        n_samples: Number of samples in the data
        display_width_pixels: Approximate width of display area in pixels

    Returns:
        Decimation factor (1 = no decimation needed)
    """
    # We want roughly 2-4 samples per pixel for good visual quality
    target_samples = display_width_pixels * 4
    factor = max(1, n_samples // target_samples)
    return factor
