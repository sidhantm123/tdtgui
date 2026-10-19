"""Pick the right reader for a recording folder."""
from pathlib import Path

from tdt_io import TDTReader
from blackrock_io import BlackrockReader


def open_reader(folder_path: str):
    """
    Return a reader instance suited to the data in folder_path.

    Raises:
        FileNotFoundError: If the folder doesn't exist
        ValueError: If no supported recording files are found
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    if BlackrockReader.is_blackrock_folder(folder_path):
        return BlackrockReader()

    if any(f.suffix.lower() in TDTReader.TDT_EXTENSIONS for f in folder.iterdir()):
        return TDTReader()

    raise ValueError(
        "No supported recording files found. Expected a TDT block "
        "(.tev, .tsq, .tdx, ...) or Blackrock data (.ns1-.ns6)."
    )
