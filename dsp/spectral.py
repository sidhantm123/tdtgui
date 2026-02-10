"""Spectral analysis: FFT and PSD computation."""
from typing import Tuple, Optional
import numpy as np
from scipy import signal


def compute_fft(
    data: np.ndarray,
    fs: float,
    window: str = "hann",
    normalize: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute FFT magnitude spectrum.

    Args:
        data: Input data (1D for single channel or 2D with channels as rows)
        fs: Sampling frequency in Hz
        window: Window function name (scipy.signal.get_window compatible)
        normalize: If True, normalize by number of samples

    Returns:
        Tuple of (frequencies, magnitudes) where:
            frequencies: Positive frequency values in Hz
            magnitudes: FFT magnitude (absolute value), shape (n_channels, n_freqs) or (n_freqs,)
    """
    if data.ndim == 1:
        data = data.reshape(1, -1)
        was_1d = True
    else:
        was_1d = False

    n_channels, n_samples = data.shape

    # Apply window
    try:
        win = signal.get_window(window, n_samples)
    except ValueError:
        win = np.ones(n_samples)

    # Compute FFT
    windowed_data = data * win

    fft_result = np.fft.rfft(windowed_data, axis=1)

    # Get frequencies (positive only)
    freqs = np.fft.rfftfreq(n_samples, d=1.0 / fs)

    # Compute magnitude
    magnitudes = np.abs(fft_result)

    if normalize:
        magnitudes = magnitudes / n_samples
        # Double the magnitude for non-DC and non-Nyquist components
        # to account for the negative frequencies
        magnitudes[:, 1:-1] *= 2

    if was_1d:
        return freqs, magnitudes[0]
    return freqs, magnitudes


def compute_psd(
    data: np.ndarray,
    fs: float,
    nperseg: int = 1024,
    overlap: float = 0.5,
    window: str = "hann",
    scaling: str = "density",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute Power Spectral Density using Welch's method.

    Args:
        data: Input data (1D for single channel or 2D with channels as rows)
        fs: Sampling frequency in Hz
        nperseg: Length of each segment
        overlap: Overlap fraction (0 to 1)
        window: Window function name
        scaling: 'density' for power/Hz, 'spectrum' for power

    Returns:
        Tuple of (frequencies, psd) where:
            frequencies: Frequency values in Hz
            psd: Power spectral density, shape (n_channels, n_freqs) or (n_freqs,)
    """
    if data.ndim == 1:
        data = data.reshape(1, -1)
        was_1d = True
    else:
        was_1d = False

    n_channels, n_samples = data.shape

    # Adjust nperseg if data is shorter
    nperseg = min(nperseg, n_samples)
    noverlap = int(nperseg * overlap)

    # Compute PSD for each channel
    psd_list = []
    freqs = None

    for i in range(n_channels):
        f, pxx = signal.welch(
            data[i],
            fs=fs,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            scaling=scaling,
        )
        psd_list.append(pxx)
        if freqs is None:
            freqs = f

    psd = np.array(psd_list)

    if was_1d:
        return freqs, psd[0]
    return freqs, psd


def compute_spectrogram(
    data: np.ndarray,
    fs: float,
    nperseg: int = 256,
    overlap: float = 0.75,
    window: str = "hann",
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute spectrogram.

    Args:
        data: Input data (1D)
        fs: Sampling frequency in Hz
        nperseg: Length of each segment
        overlap: Overlap fraction
        window: Window function name

    Returns:
        Tuple of (frequencies, times, spectrogram) where:
            frequencies: Frequency values in Hz
            times: Time values in seconds
            spectrogram: 2D array of power values
    """
    if data.ndim > 1:
        data = data[0]  # Use first channel only

    nperseg = min(nperseg, len(data))
    noverlap = int(nperseg * overlap)

    f, t, Sxx = signal.spectrogram(
        data,
        fs=fs,
        window=window,
        nperseg=nperseg,
        noverlap=noverlap,
    )

    return f, t, Sxx


def find_peak_frequency(
    freqs: np.ndarray,
    magnitude: np.ndarray,
    freq_range: Optional[Tuple[float, float]] = None,
) -> Tuple[float, float]:
    """
    Find the peak frequency in a spectrum.

    Args:
        freqs: Frequency array
        magnitude: Magnitude array
        freq_range: Optional (min_freq, max_freq) to search within

    Returns:
        Tuple of (peak_frequency, peak_magnitude)
    """
    if freq_range is not None:
        mask = (freqs >= freq_range[0]) & (freqs <= freq_range[1])
        freqs_search = freqs[mask]
        mag_search = magnitude[mask]
    else:
        freqs_search = freqs
        mag_search = magnitude

    if len(mag_search) == 0:
        return 0.0, 0.0

    peak_idx = np.argmax(mag_search)
    return float(freqs_search[peak_idx]), float(mag_search[peak_idx])
