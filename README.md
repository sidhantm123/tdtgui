# TDT Multi-Channel Viewer

A cross-platform desktop application for viewing and analyzing Tucker-Davis Technologies (TDT) neural recording data.

## Features

- **Multi-channel visualization**: View single channels or overlay up to 8 channels simultaneously
- **High-performance plotting**: Automatic decimation for smooth interaction with long recordings (up to 120+ minutes)
- **Configurable filter chains**: Apply multiple filters (low-pass, high-pass, band-pass, notch, CAR, CMR, Vrms threshold) in any order
- **Common Average / Median Reference**: Interactive channel subgroup assignment with color-coded UI
- **Vrms display**: Per-channel RMS voltage shown in real time, with SI-prefix formatting
- **Vrms threshold filter**: Zero out sub-threshold data points based on a configurable Vrms multiplier
- **Scatter / dot mode**: Toggle between line and scatter rendering for the time series plot
- **Per-stream filter persistence**: Each stream maintains its own filter configuration
- **Spectral analysis**: FFT magnitude and Welch PSD with interval selection
- **Session save/load**: Save filter configurations, view settings, and display mode as JSON
- **Drag-and-drop**: Simply drag a TDT block folder onto the window

## Requirements

- Python 3.9 or later
- Windows 10/11 or macOS 12+

## Installation

### From Source

1. Clone or download this repository

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

### Development Mode

```bash
cd tdt_viewer_app
python main.py
```

Or with a TDT block folder:
```bash
python main.py /path/to/tdt/block/folder
```

### Running Tests

```bash
cd tdt_viewer_app
python -m pytest tests/ -v
```

Or without pytest:
```bash
python -m unittest discover tests/
```

## Building Standalone Executables

### Prerequisites

Install PyInstaller:
```bash
pip install pyinstaller
```

### Windows Build

```bash
cd tdt_viewer_app
pyinstaller tdt_viewer.spec
```

The executable will be created at:
- `dist/TDT_Viewer/TDT_Viewer.exe`

To create a single-file executable (larger, slower startup):
```bash
pyinstaller --onefile --windowed --name TDT_Viewer main.py
```

### macOS Build

```bash
cd tdt_viewer_app
pyinstaller tdt_viewer.spec
```

The application bundle will be created at:
- `dist/TDT_Viewer.app`

To run the app:
```bash
open dist/TDT_Viewer.app
```

Or from terminal:
```bash
./dist/TDT_Viewer.app/Contents/MacOS/TDT_Viewer
```

### Build Notes

- The first build may take several minutes as PyInstaller analyzes dependencies
- Build output is in the `dist/` directory
- Intermediate files are in the `build/` directory (can be deleted)
- Add `--clean` flag to force a fresh build: `pyinstaller --clean tdt_viewer.spec`

---

## Usage Guide

### 1. Opening TDT Data

There are three ways to load a TDT recording block:

1. **File menu**: File > Open TDT Block... and select the block folder
2. **Drag and drop**: Drag a TDT block folder onto the application window
3. **Command line**: `python main.py /path/to/block`

The application expects a folder containing TDT recording files (`.tdx`, `.tev`, `.tsq`, `.tnt`, `.tbk`, `.tin`, etc.).

Once loaded, the left panel shows block info (name, duration, stream count) and a list of available streams.

**ADD SCREENSHOT OF the main window after loading a TDT block, showing the stream list on the left, the time series plot in the center, and the control panel on the right**

### 2. Stream and Channel Selection

**Selecting a stream:**
Click any stream in the left panel. The stream's metadata (channel count, sample rate) and data will load automatically.

**Channel modes** (Channels tab, right panel):

- **Single Channel**: Use the spinner to pick one channel to display.
- **Overlay Channels**: Add up to 8 channels to display simultaneously with distinct colors. Use the "Add" combo + "+" button to add channels, and "Remove Selected" to remove them.

**ADD SCREENSHOT OF the Channels tab showing overlay mode with multiple channels selected and the multi-channel time series plot**

### 3. Navigation

- **Mouse wheel**: Zoom in/out on the time axis
- **Click and drag**: Pan the view
- **Double-click**: Reset to full view
- **View Range controls**: Enter exact start/end times in the Channels tab and click "Apply View", or click "Reset" to return to the default window

**ADD SCREENSHOT OF a zoomed-in time series view showing the View Range controls with start and end time spinners**

### 4. Filter Chain

Go to the **Filters** tab in the right panel.

**Adding a filter:**

1. Click **Add** to open the filter dialog
2. Select the filter type from the dropdown
3. Configure the parameters (details below per type)
4. Click **OK** to add the filter to the chain

**Available filter types:**

| Type | Parameters | Description |
|------|-----------|-------------|
| Low-pass | Cutoff frequency, order | Removes frequencies above the cutoff |
| High-pass | Cutoff frequency, order | Removes frequencies below the cutoff |
| Band-pass | Low/high cutoff, order | Keeps frequencies within a range |
| Notch | Center frequency, Q factor | Removes a specific frequency (e.g., 60 Hz line noise) |
| Common Avg Ref (CAR) | Channel subgroups | Subtracts the per-group mean across channels |
| Common Median Ref (CMR) | Channel subgroups | Subtracts the per-group median across channels |
| Vrms Threshold | Multiplier (x Vrms) | Zeros out data points with amplitude below the threshold |

**ADD SCREENSHOT OF the Filters tab showing a filter chain with multiple filters listed (e.g., a highpass, a CAR, and a notch filter)**

**Managing filters:**

- **Edit**: Double-click a filter in the list, or select it and click **Edit**
- **Reorder**: Select a filter and use **Up** / **Down** to change its position in the chain
- **Toggle Bypass**: Select a filter and click **Toggle Bypass** to temporarily disable it (shown as `[BYPASS]` in the list)
- **Bypass All**: Check the "Bypass All" checkbox at the top to disable the entire chain
- **Remove**: Select a filter and click **Remove**

Filters are applied in the order shown, top to bottom. Reordering matters -- for example, applying a highpass before CAR gives different results than the reverse.

**ADD SCREENSHOT OF the Add Filter dialog showing the filter type dropdown with all seven options visible**

### 5. Common Average / Median Reference (CAR/CMR)

When you select CAR or CMR as the filter type, an interactive channel grouping panel appears.

**How to assign channels to subgroups:**

1. Click **"+ Add Subgroup"** in the top bar to create a new subgroup (SG 1, SG 2, etc.). Each subgroup gets a distinct color.
2. Click a **subgroup button** in the top bar to select it as the active "brush".
3. Click **channel buttons** in the grid below to assign them to the active subgroup. Assigned channels take on the subgroup's color.
4. To **reassign** a channel, select a different subgroup and click the channel.
5. To **unassign** a channel, click it while the same subgroup is already active.
6. The status bar shows how many channels are assigned (e.g., "24 / 32 channels assigned").
7. The **OK** button is disabled until every channel is assigned to exactly one subgroup.

**ADD SCREENSHOT OF the Add Filter dialog with CAR selected, showing the channel grouping widget with two subgroups (different colors) and channels partially assigned**

**ADD SCREENSHOT OF the channel grouping widget with all channels assigned to subgroups (status shows N/N assigned, OK button enabled)**

### 6. Vrms Display

The **Vrms** box in the Channels tab shows the RMS voltage for each displayed channel. Values are formatted with SI prefixes (nV, uV, mV, V) for readability.

- Vrms updates automatically whenever filters change or new data is loaded.
- When a **Vrms Threshold** filter is in the chain, the displayed Vrms reflects the signal *before* thresholding, so the threshold doesn't feed back into its own reference value.

**ADD SCREENSHOT OF the Channels tab showing the Vrms display box with per-channel RMS values in microvolt or millivolt units**

### 7. Vrms Threshold Filter

This filter zeros out data points where `|amplitude| < multiplier * Vrms`. It is useful for removing background noise while preserving spikes and other large-amplitude events.

1. Add a new filter and select **Vrms Threshold**
2. Set the **Threshold multiplier** (default: 3.0x Vrms)
3. Click **OK**

**ADD SCREENSHOT OF the time series plot showing data before and after a Vrms threshold filter is applied (sub-threshold points zeroed out, spikes preserved)**

### 8. Scatter / Dot Mode

Check the **"Scatter / Dot Mode"** checkbox in the Display section of the Channels tab to render data as dots instead of connected lines. This can be useful for visualizing spike sorting results or sparse data.

The scatter mode setting is saved per-stream and persists across sessions.

**ADD SCREENSHOT OF the time series plot in scatter/dot mode showing data rendered as colored dots instead of lines**

### 9. Spectral Analysis

1. Go to the **Analysis** tab in the right panel
2. Select method: **FFT Magnitude** or **PSD (Welch)**
3. Set the time interval:
   - Enter start/end times manually, or
   - Check "Select on plot" and drag the selection region on the time series
4. Choose which channels to analyze
5. For PSD, configure segment length and overlap
6. Click **Analyze**
7. Results appear in the **Spectrum** tab

**ADD SCREENSHOT OF the Spectrum tab showing a PSD plot with peaks at identifiable frequencies and the Analysis controls visible on the right**

### 10. Saving and Loading Sessions

Save your entire workspace (filter chains, view ranges, channel selections, scatter mode) for later:

- **File > Save Session...**: Saves as a `.json` file
- **File > Load Session...**: Restores all settings. The original TDT block folder must still be accessible at the saved path.

---

## Project Structure

```
tdt_viewer_app/
├── main.py              # Application entry point
├── requirements.txt     # Python dependencies
├── tdt_viewer.spec      # PyInstaller build configuration
├── README.md            # This file
├── assets/              # Application icons
├── core/                # Application state and workers
│   ├── app_state.py     # Global state management
│   └── workers.py       # Background processing threads
├── dsp/                 # Digital signal processing
│   ├── filters.py       # Filter design and chain application
│   ├── decimation.py    # Data decimation for display
│   ├── spectral.py      # FFT and PSD computation
│   ├── referencing.py   # CAR and CMR re-referencing
│   └── metrics.py       # Vrms computation and thresholding
├── tdt_io/              # Data input/output
│   └── tdt_reader.py    # TDT file reading
├── models/              # Data models
│   ├── filter_config.py # Filter configuration (7 types)
│   └── stream_state.py  # Per-stream state
├── ui/                  # User interface
│   ├── main_window.py   # Main application window
│   ├── stream_panel.py  # Stream list widget
│   ├── control_panel.py # Channel selection, Vrms display, scatter toggle
│   ├── filter_panel.py  # Filter chain editor + channel group widget
│   ├── spectrum_panel.py# Spectral analysis controls
│   └── plot_widget.py   # Time series and spectrum plots
└── tests/               # Unit tests
    └── test_dsp.py      # DSP module tests
```

## Codebase Architecture

### Overview

The application follows a layered architecture with clear separation between data models, signal processing, application state, and UI. Communication between UI components uses Qt's signal/slot mechanism.

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py (entry point)                    │
│                              │                                  │
│                        MainWindow (ui/)                         │
│             ┌────────────────┼────────────────┐                 │
│        StreamPanel     ControlPanel     FilterPanel             │
│             │          SpectrumPanel    PlotWidgets              │
│             │                │                │                  │
│             └────────────────┼────────────────┘                 │
│                              │                                  │
│                        AppState (core/)                         │
│                        WorkerManager                            │
│                              │                                  │
│                 ┌────────────┼────────────┐                     │
│            TDTReader    StreamState    FilterConfig              │
│            (tdt_io/)    (models/)      (models/)                │
│                              │                                  │
│                         DSP (dsp/)                              │
│              filters / referencing / metrics / spectral          │
└─────────────────────────────────────────────────────────────────┘
```

### Layer-by-layer

**`models/`** — Pure data classes with no UI or I/O dependencies.

- `FilterConfig`: Dataclass representing one filter in the chain. Holds the filter type (one of 7: lowpass, highpass, bandpass, notch, CAR, CMR, vrms_threshold), its parameters (cutoff frequencies, order, channel_groups, vrms_multiplier), a unique ID, and a bypass flag. Includes `to_dict()`/`from_dict()` for JSON serialization.
- `StreamState`: Per-stream state dataclass. Stores channel selection mode (single/overlay), active channels, view range, the ordered filter chain (`List[FilterConfig]`), scatter mode, transient Vrms values, and FFT/PSD settings. Each stream has its own `StreamState` so switching streams preserves all settings.
- `ChannelMode`: Enum — `SINGLE` or `OVERLAY`.

**`tdt_io/`** — TDT file reading layer.

- `TDTReader`: Wraps the `tdt` Python SDK. `load_block()` reads a TDT folder and returns a `TDTBlock` with stream metadata. `get_stream_data()` loads a slice of channel data for a given time range — this is the windowed loading that avoids reading the entire file into memory.
- `TDTBlock` / `StreamInfo`: Lightweight metadata containers (name, path, duration, per-stream channel count and sample rate).

**`dsp/`** — Stateless signal processing functions. No Qt or UI dependencies.

- `filters.py`: The central `apply_filter_chain()` function. Takes displayed channel data, the ordered filter list, sample rate, and optionally the full all-channel array (needed for CAR/CMR). Iterates filters in order: SOS filters (LP/HP/BP/notch) use `scipy.signal.sosfiltfilt` for zero-phase filtering; CAR/CMR operate on the all-channel array and extract displayed channels back; Vrms threshold computes RMS *before* zeroing. Always returns a 3-tuple: `(filtered_data, warnings, vrms_dict)`.
- `referencing.py`: `apply_car()` subtracts the per-group channel mean at each time point. `apply_cmr()` does the same with median. Both operate on the full multi-channel array and return a copy.
- `metrics.py`: `compute_vrms()` returns `sqrt(mean(x^2))` per channel. `apply_vrms_threshold()` zeros out samples where `|x| < multiplier * Vrms`.
- `decimation.py`: `decimate_for_display()` uses min/max decimation — for each block of samples, it keeps both the minimum and maximum, preserving waveform peaks while reducing point count by ~50x.
- `spectral.py`: `compute_fft()` and `compute_psd()` (Welch method via `scipy.signal.welch`).

**`core/`** — Application state and threading.

- `AppState`: Global singleton managing the loaded `TDTBlock`, per-stream `StreamState` dict, current selection, and callback registration (`on_block_loaded`, `on_stream_changed`, `on_state_updated`). Also handles session save/load (serializes all stream states to JSON).
- `WorkerManager` / Workers: `QThreadPool`-based background execution. `FilterWorker` accepts the full `apply_filter_chain` signature (including `all_channel_data` and `channel_indices`) and performs filtering + decimation off the UI thread. `SpectralWorker` and `DataLoadWorker` handle FFT/PSD and data loading respectively. All workers are cancellable.

**`ui/`** — PySide6 widgets. All inter-widget communication uses Qt signals.

- `MainWindow`: Orchestrator. Owns all panels and plots. Connects signals between them. Handles the data pipeline: load data → (optionally load all channels for CAR/CMR) → `apply_filter_chain()` → decimate → `set_data()` or `update_data()` on the plot. Implements the fast update path: if channels and scatter mode haven't changed since the last render, it calls `update_data()` (which reuses existing pyqtgraph `PlotDataItem` objects) instead of `set_data()` (which tears down and rebuilds them).
- `StreamPanel`: Left sidebar. Displays block metadata and a tree of streams. Emits `stream_selected(str)` on click.
- `ControlPanel`: Right sidebar, "Channels" tab. Channel mode radio buttons, single channel spinner, overlay channel list, view range controls, Vrms display box, and scatter mode checkbox. Emits signals for each user interaction.
- `FilterPanel`: Right sidebar, "Filters" tab. Filter list with add/edit/remove/reorder/bypass controls. Contains `FilterEditDialog` (modal dialog for configuring a filter) and `ChannelGroupWidget` (interactive subgroup assignment grid for CAR/CMR). Emits `filters_changed()` whenever the chain is modified.
- `SpectrumPanel`: Right sidebar, "Analysis" tab. Controls for FFT/PSD parameters and interval selection. Emits `analyze_requested(dict)`.
- `TimeSeriesPlot` / `SpectrumPlot` (in `plot_widget.py`): pyqtgraph-based plot widgets. `TimeSeriesPlot` supports both line and scatter rendering modes, region selection for FFT intervals, and the fast `update_data()` path.

### Data flow

The main data pipeline when a user changes filters or view range:

```
User action (filter change, zoom, channel switch, etc.)
  │
  ▼
MainWindow._refresh_plot()
  │
  ├─ reader.get_stream_data()        ← load displayed channels for view range
  ├─ reader.get_stream_data()        ← load ALL channels (only if CAR/CMR active)
  │
  ▼
MainWindow._apply_filters()
  │
  ├─ apply_filter_chain()            ← returns (filtered_data, warnings, vrms_dict)
  │    ├─ SOS filters: sosfiltfilt
  │    ├─ CAR/CMR: apply to all-channel array, extract displayed channels
  │    └─ Vrms threshold: compute Vrms first, then zero sub-threshold
  │
  ├─ control_panel.update_vrms()     ← update Vrms display
  ├─ decimate_for_display()          ← reduce points if > MAX_PLOT_POINTS
  │
  ▼
TimeSeriesPlot
  ├─ update_data()                   ← fast path (reuse plot items)
  └─ set_data()                      ← full rebuild (channels or mode changed)
```

### Key design decisions

- **Filter chain returns Vrms always**: Even with no filters active, `apply_filter_chain()` computes and returns Vrms so the display always has values to show.
- **Vrms computed before threshold**: The Vrms threshold filter computes RMS on the *pre-threshold* signal, then applies zeroing. This prevents the threshold from feeding back into its own reference value.
- **CAR/CMR loads all channels**: When a CAR or CMR filter is active, `_refresh_plot()` makes a second `get_stream_data()` call for all channels. The re-referencing operates on this full array, then the displayed channels are extracted back. This is necessary because the reference (mean/median) must be computed across the entire group.
- **Fast update vs full rebuild**: `update_data()` calls `setData()` on existing `PlotDataItem` objects (fast). `set_data()` removes all items and creates new ones (slow). The main window tracks `_last_plot_channels` and `_last_scatter_mode` to decide which path to take.
- **Per-stream state isolation**: Switching streams saves nothing explicitly — each stream's `StreamState` lives in `AppState.stream_states[name]` and is restored when the stream is selected again.

## Performance Notes

The application is designed to handle long recordings efficiently:

- **Fast update path**: When only filter parameters change (not channels or display mode), plot items are reused instead of rebuilt, avoiding expensive pyqtgraph teardown/creation
- **Decimation**: Data is automatically downsampled for display using min/max preservation for accurate waveform visualization
- **Windowed loading**: Only the visible time range is loaded from disk
- **Background workers**: `FilterWorker` and `SpectralWorker` are ready for async execution via `QThreadPool`
- **Debounced refresh**: View changes during zooming/panning are debounced at 100ms to avoid redundant redraws
- **Tested with**: Recordings up to 120 minutes at 24-30 kHz sample rates

## Troubleshooting

### "No TDT block found in folder"

Ensure the folder contains valid TDT recording files. The folder should have files with extensions like `.tdx`, `.tev`, `.tsq`, etc.

### Application freezes when loading large files

This shouldn't happen with the current implementation. If it does:
1. Try a smaller time window first
2. Check available system memory
3. File an issue with details about the recording

### Filter warnings

If you see filter warnings, the filter parameters may be invalid for the sampling rate:
- Cutoff frequencies must be less than half the sampling rate (Nyquist frequency)
- For a 24 kHz stream, maximum cutoff is ~11,999 Hz

### CAR/CMR filter shows "requires all channels loaded"

This warning appears if the all-channel data couldn't be loaded. Ensure the stream has data and the block is fully loaded (not headers-only).

### macOS: "App is damaged and can't be opened"

This happens with unsigned apps. Run:
```bash
xattr -cr /path/to/TDT_Viewer.app
```

## License

MIT License

## Acknowledgments

- [TDT Python SDK](https://www.tdt.com/docs/sdk/offline-data-analysis/offline-data-python/) for data reading
- [PySide6](https://www.qt.io/qt-for-python) for the Qt bindings
- [pyqtgraph](https://www.pyqtgraph.org/) for high-performance plotting
- [SciPy](https://scipy.org/) for signal processing
