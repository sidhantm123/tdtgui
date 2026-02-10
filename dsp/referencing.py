"""Common reference subtraction (CAR/CMR) for multi-channel data."""
from typing import List, Tuple
import numpy as np


def apply_car(
    data: np.ndarray,
    channel_groups: List[List[int]],
) -> Tuple[np.ndarray, List[str]]:
    """
    Apply Common Average Reference.

    For each group, subtracts the mean across group channels at each time point
    from every channel in that group.

    Args:
        data: Shape (n_channels, n_samples). All channels must be present.
        channel_groups: List of groups, each a list of 0-indexed channel indices.
                        Channels not in any group are left unchanged.

    Returns:
        (re-referenced data copy, warnings)
    """
    warnings = []
    result = data.copy()
    n_channels = data.shape[0]

    for group_idx, group in enumerate(channel_groups):
        valid = [ch for ch in group if 0 <= ch < n_channels]
        if len(valid) < 2:
            warnings.append(
                f"CAR group {group_idx + 1}: need >= 2 valid channels, got {len(valid)}"
            )
            continue
        group_mean = np.mean(result[valid, :], axis=0)
        result[valid, :] -= group_mean

    return result, warnings


def apply_cmr(
    data: np.ndarray,
    channel_groups: List[List[int]],
) -> Tuple[np.ndarray, List[str]]:
    """
    Apply Common Median Reference.

    Same as CAR but uses median instead of mean.

    Args:
        data: Shape (n_channels, n_samples). All channels must be present.
        channel_groups: List of groups, each a list of 0-indexed channel indices.

    Returns:
        (re-referenced data copy, warnings)
    """
    warnings = []
    result = data.copy()
    n_channels = data.shape[0]

    for group_idx, group in enumerate(channel_groups):
        valid = [ch for ch in group if 0 <= ch < n_channels]
        if len(valid) < 2:
            warnings.append(
                f"CMR group {group_idx + 1}: need >= 2 valid channels, got {len(valid)}"
            )
            continue
        group_median = np.median(result[valid, :], axis=0)
        result[valid, :] -= group_median

    return result, warnings
