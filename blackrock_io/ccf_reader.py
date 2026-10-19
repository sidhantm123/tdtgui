"""Blackrock Central configuration (.ccf) file parsing.

Central 6+ writes .ccf files as XML. Each channel's settings live in an element
(typically ``ChanInfo/ChanInfo_item``) that has a ``chan`` child holding the
1-based channel ID, plus a ``label`` and many nested settings. Older Central
versions wrote a binary format, which is detected and reported but not parsed.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

# Settings shown first in the Recording Info table when present (flattened keys)
PREFERRED_FIELDS = [
    "label",
    "smpgroup",
    "smpfilter",
    "spkfilter",
    "spkthrlevel",
    "spkopts",
    "ainpopts",
    "refelecchan",
    "lncrate",
    "physcalin/anagain",
    "physcalin/anaunit",
    "scalin/anaunit",
]


def _local(tag: str) -> str:
    """Strip any XML namespace from a tag and lowercase it."""
    return tag.rsplit("}", 1)[-1].lower()


def _flatten(elem: ET.Element, prefix: str = "") -> Dict[str, str]:
    """Flatten an element's descendants into {"a/b/c": text} for leaf nodes."""
    out: Dict[str, str] = {}
    for child in elem:
        key = f"{prefix}{_local(child.tag)}"
        if len(child):
            out.update(_flatten(child, key + "/"))
        else:
            text = (child.text or "").strip()
            if text:
                # Repeated leaves (e.g. arrays) get an index suffix
                if key in out:
                    i = 1
                    while f"{key}[{i}]" in out:
                        i += 1
                    key = f"{key}[{i}]"
                out[key] = text
    return out


def _find_channel_items(root: ET.Element) -> List[ET.Element]:
    """Return elements describing per-channel settings."""

    def has_chan(elem):
        return any(_local(c.tag) == "chan" and not len(c) for c in elem)

    # Prefer items inside a ChanInfo container; other sections (e.g. spike
    # sorting) can also carry a <chan> child.
    items = []
    for parent in root.iter():
        if _local(parent.tag) == "chaninfo":
            items.extend(c for c in parent if has_chan(c))
    if items:
        return items
    return [e for e in root.iter() if has_chan(e) and any(_local(c.tag) == "label" for c in e)]


def read_ccf(path: str) -> dict:
    """
    Parse a Blackrock .ccf file.

    Returns:
        dict with keys:
            path: source file path
            format: "xml" or "binary"
            version: file version string if present, else None
            channels: list of {"chan": int, "label": str, "fields": {key: value}}
            error: None, or a message describing why the file could not be read
    """
    result = {"path": str(path), "format": None, "version": None, "channels": [], "error": None}

    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError as e:
        result["error"] = f"Could not open .ccf file: {e}"
        return result

    if not head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        result["format"] = "binary"
        result["error"] = (
            "This .ccf uses the older binary format (pre-Central 6), which is not supported. "
            "Re-save it from a recent version of Central to view its settings."
        )
        return result

    result["format"] = "xml"
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        result["error"] = f"Could not parse .ccf XML: {e}"
        return result

    result["version"] = root.attrib.get("Version") or root.attrib.get("version")

    channels = []
    for item in _find_channel_items(root):
        fields = _flatten(item)
        try:
            chan = int(fields.pop("chan"))
        except (KeyError, ValueError):
            continue
        channels.append({"chan": chan, "label": fields.get("label", ""), "fields": fields})

    result["channels"] = channels
    if not channels:
        result["error"] = "No channel settings found in .ccf file."
    return result


def ccf_labels(ccf: dict) -> Dict[int, str]:
    """Map channel ID -> label for channels with a non-empty label."""
    return {c["chan"]: c["label"] for c in ccf.get("channels", []) if c["label"]}


def find_ccf(folder: Path, basename: Optional[str] = None) -> Optional[Path]:
    """Find the .ccf in a folder, preferring one that shares the recording's basename."""
    ccfs = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".ccf")
    if basename:
        for p in ccfs:
            if p.stem == basename:
                return p
    return ccfs[0] if ccfs else None
