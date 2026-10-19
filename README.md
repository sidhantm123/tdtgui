# Multi-Channel Neural Viewer

A desktop app (Windows / macOS) for viewing and analyzing multi-channel neural recordings from **Tucker-Davis Technologies (TDT)** and **Blackrock Neurotech** systems.

## Features

- Single-channel or overlay (up to 8 channels) time-series plots, smooth on recordings of 2+ hours
- Filter chains: low-pass, high-pass, band-pass, notch, CAR, CMR and Vrms threshold, applied in any order
- Live per-channel Vrms readout
- FFT and Welch PSD on a selected time interval
- Probe geometry map (probeinterface JSON)
- Export a stream to int16 binary (`.i16` / `.bin`)
- Session save/load (filters, view ranges, channel selections)

## Supported data

Open a recording folder via **File → Open Recording Folder…**, drag-and-drop, or `python main.py /path/to/folder`. The format is detected automatically.

| System | Files | Notes |
|---|---|---|
| TDT | `.tev`, `.tsq`, `.tdx`, `.sev`, … | Read with the `tdt` package |
| Blackrock | `.ns1`–`.ns6`, `.ccf` | Read with `neo`. Each `.nsX` file is one stream. Channel labels come from the `.ccf`, and **View → Recording Info** (Ctrl+I) shows its channel settings. `.nev` (spikes/events) is not loaded yet. |

## Setup

Requires Python 3.11+.

```bash
python3 -m venv tdtgui
source tdtgui/bin/activate        # Windows: tdtgui\Scripts\activate
pip install -r requirements.txt
python main.py
```

Run the tests:

```bash
python -m unittest discover tests
```

Build a standalone app (output in `dist/`):

```bash
pyinstaller --clean tdt_viewer.spec
```

## Usage

1. **Open** a recording folder. Streams are listed on the left; click one to display it.
2. **Channels tab**: choose single or overlay mode, set the view range, toggle scatter (dot) mode and read Vrms values.
3. **Navigate**: scroll to zoom, drag to pan, double-click to reset.
4. **Filters tab**: add filters, reorder them (they run top to bottom) and bypass them individually or all at once.
   - For **CAR/CMR**, create subgroups and click channels to assign them. Every channel must be assigned before you can confirm.
   - The **Vrms threshold** filter zeros samples where `|x| < multiplier × Vrms`, using the Vrms measured before thresholding.
5. **Analysis tab**: pick FFT or PSD, choose an interval (type it in or drag on the plot), then click **Analyze**. Results appear in the Spectrum tab.
6. **File → Save/Load Session** stores settings as JSON. The recording must still exist at its original path to reload a session.

## Project structure

```
main.py              Entry point
core/                AppState, background workers, reader_factory (picks TDT or Blackrock)
tdt_io/              TDT reader
blackrock_io/        Blackrock .nsX reader and .ccf parser
models/              Data classes: recording metadata, per-stream state, filters, probe
dsp/                 Filtering, CAR/CMR, Vrms, decimation, FFT/PSD (no UI dependencies)
ui/                  PySide6 windows, panels and plots
tests/               Unit tests
```

Every reader exposes `load_block()` and `get_stream_data(stream, channels, start, end)`, which returns `(channels × samples)` data in volts. Only the visible time window is read from disk, and plots are min/max decimated for display.

## Troubleshooting

- **Filter warnings**: cutoff frequencies must be below half the sample rate (the Nyquist frequency).
- **macOS "app is damaged"** (unsigned build): run `xattr -cr dist/TDT_Viewer.app`.

## License

MIT. Built with [tdt](https://www.tdt.com/docs/sdk/offline-data-analysis/offline-data-python/), [neo](https://neo.readthedocs.io/), [PySide6](https://www.qt.io/qt-for-python), [pyqtgraph](https://www.pyqtgraph.org/) and [SciPy](https://scipy.org/).
