"""Signal metrics (Vrms, etc.)."""
from typing import Dict, List
import numpy as np


def compute_vrms(
    data: np.ndarray,
    channel_indices: List[int],
) -> Dict[int, float]:
    """
    Compute Vrms for each channel.

    Args:
        data: Shape (n_channels, n_samples) or (n_samples,)
        channel_indices: Original channel indices (used as dict keys).

    Returns:
        Dict mapping channel index -> Vrms value.
    """
    if data.ndim == 1:
        data = data.reshape(1, -1)

    result = {}
    for i, ch_idx in enumerate(channel_indices):
        if i < data.shape[0]:
            result[ch_idx] = float(np.sqrt(np.mean(data[i] ** 2)))
    return result


def apply_vrms_threshold(
    data: np.ndarray,
    vrms_values: Dict[int, float],
    channel_indices: List[int],
    multiplier: float,
) -> np.ndarray:
    """
    Zero out samples whose absolute value < multiplier * Vrms.

    Args:
        data: Shape (n_channels, n_samples) or (n_samples,)
        vrms_values: Pre-computed Vrms per channel (from before this filter).
        channel_indices: Original channel indices matching rows of data.
        multiplier: Threshold = multiplier * Vrms.

    Returns:
        Thresholded data (copy).
    """
    result = data.copy()
    was_1d = result.ndim == 1
    if was_1d:
        result = result.reshape(1, -1)

    for i, ch_idx in enumerate(channel_indices):
        if i < result.shape[0] and ch_idx in vrms_values:
            threshold = multiplier * vrms_values[ch_idx]
            mask = np.abs(result[i]) < threshold
            result[i, mask] = 0.0

    if was_1d:
        return result[0]
    return result
