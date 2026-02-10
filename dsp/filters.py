"""Filter design and application using SOS format."""
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy import signal

from models.filter_config import FilterConfig, FilterType
from .referencing import apply_car, apply_cmr
from .metrics import compute_vrms, apply_vrms_threshold


def design_filter(config: FilterConfig, fs: float) -> Optional[np.ndarray]:
    """
    Design a filter and return SOS coefficients.

    Args:
        config: Filter configuration
        fs: Sampling frequency in Hz

    Returns:
        SOS coefficients array, or None if design fails
    """
    nyq = fs / 2.0

    try:
        if config.filter_type == FilterType.LOWPASS:
            if config.cutoff_high >= nyq:
                return None  # Invalid cutoff
            sos = signal.butter(
                config.order,
                config.cutoff_high / nyq,
                btype="low",
                output="sos",
            )

        elif config.filter_type == FilterType.HIGHPASS:
            if config.cutoff_low >= nyq or config.cutoff_low <= 0:
                return None
            sos = signal.butter(
                config.order,
                config.cutoff_low / nyq,
                btype="high",
                output="sos",
            )

        elif config.filter_type == FilterType.BANDPASS:
            if config.cutoff_low >= nyq or config.cutoff_high >= nyq:
                return None
            if config.cutoff_low >= config.cutoff_high:
                return None
            sos = signal.butter(
                config.order,
                [config.cutoff_low / nyq, config.cutoff_high / nyq],
                btype="band",
                output="sos",
            )

        elif config.filter_type == FilterType.NOTCH:
            if config.notch_freq >= nyq or config.notch_freq <= 0:
                return None
            # Design notch filter using iirnotch, then convert to SOS
            b, a = signal.iirnotch(config.notch_freq, config.notch_q, fs)
            # Convert to SOS for numerical stability
            sos = signal.tf2sos(b, a)

        else:
            return None

        return sos

    except Exception:
        return None


def apply_filter(data: np.ndarray, sos: np.ndarray) -> np.ndarray:
    """
    Apply SOS filter using zero-phase filtering.

    Args:
        data: Input data (1D or 2D with channels as rows)
        sos: SOS coefficients

    Returns:
        Filtered data with same shape as input
    """
    if data.ndim == 1:
        return signal.sosfiltfilt(sos, data)
    else:
        # Apply to each channel
        result = np.zeros_like(data)
        for i in range(data.shape[0]):
            result[i] = signal.sosfiltfilt(sos, data[i])
        return result


def apply_filter_chain(
    data: np.ndarray,
    filters: List[FilterConfig],
    fs: float,
    global_bypass: bool = False,
    all_channel_data: Optional[np.ndarray] = None,
    channel_indices: Optional[List[int]] = None,
) -> Tuple[np.ndarray, List[str], Dict[int, float]]:
    """
    Apply ordered filter chain to data.

    Args:
        data: Input data (1D or 2D with channels as rows) — displayed channels.
        filters: List of filter configurations in order.
        fs: Sampling frequency.
        global_bypass: If True, skip all filtering.
        all_channel_data: Full array with ALL channels loaded (required for CAR/CMR).
                          Shape (total_n_channels, n_samples).
        channel_indices: 0-indexed channel indices corresponding to rows of ``data``.
                         Required for CAR/CMR to map back after re-referencing.

    Returns:
        Tuple of (filtered_data, warnings, vrms_dict).
        vrms_dict is computed after all filters except VRMS_THRESHOLD.
    """
    warnings: List[str] = []

    if data.ndim == 1:
        data = data.reshape(1, -1)
        was_1d = True
    else:
        was_1d = False

    if channel_indices is None:
        channel_indices = list(range(data.shape[0]))

    if global_bypass or not filters:
        vrms = compute_vrms(data, channel_indices)
        out = data.copy()
        return (out[0] if was_1d else out), warnings, vrms

    result = data.copy()

    # Keep a mutable copy of all-channel data for CAR/CMR updates
    all_data = all_channel_data.copy() if all_channel_data is not None else None

    vrms_dict: Optional[Dict[int, float]] = None

    for filt in filters:
        if filt.bypassed:
            continue

        if filt.filter_type in (FilterType.CAR, FilterType.CMR):
            if all_data is None:
                warnings.append(
                    f"{filt.get_display_name()}: requires all channels loaded"
                )
                continue

            if filt.filter_type == FilterType.CAR:
                all_data, w = apply_car(all_data, filt.channel_groups)
            else:
                all_data, w = apply_cmr(all_data, filt.channel_groups)
            warnings.extend(w)

            # Extract displayed channels from updated all-channel array
            for i, ch_idx in enumerate(channel_indices):
                if ch_idx < all_data.shape[0]:
                    result[i] = all_data[ch_idx]

        elif filt.filter_type == FilterType.VRMS_THRESHOLD:
            # Compute Vrms BEFORE thresholding
            vrms_dict = compute_vrms(result, channel_indices)
            try:
                result = apply_vrms_threshold(
                    result, vrms_dict, channel_indices, filt.vrms_multiplier
                )
            except Exception as e:
                warnings.append(f"{filt.get_display_name()} failed: {e}")

        else:
            # Standard SOS filter
            sos = design_filter(filt, fs)
            if sos is None:
                warnings.append(
                    f"Filter '{filt.get_display_name()}' could not be designed "
                    f"(invalid parameters for fs={fs:.0f} Hz)"
                )
                continue

            try:
                result = apply_filter(result, sos)
            except Exception as e:
                warnings.append(f"Filter '{filt.get_display_name()}' failed: {e}")

    # If no threshold filter was encountered, compute Vrms on final result
    if vrms_dict is None:
        vrms_dict = compute_vrms(result, channel_indices)

    out = result[0] if was_1d else result
    return out, warnings, vrms_dict


def get_filter_response(
    config: FilterConfig, fs: float, n_points: int = 512
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Get frequency response of a filter.

    Args:
        config: Filter configuration
        fs: Sampling frequency
        n_points: Number of frequency points

    Returns:
        Tuple of (frequencies, magnitude in dB), or (None, None) if design fails
    """
    sos = design_filter(config, fs)
    if sos is None:
        return None, None

    try:
        w, h = signal.sosfreqz(sos, worN=n_points, fs=fs)
        magnitude_db = 20 * np.log10(np.maximum(np.abs(h), 1e-10))
        return w, magnitude_db
    except Exception:
        return None, None
