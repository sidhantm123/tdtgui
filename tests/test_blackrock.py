"""Tests for Blackrock (.nsX / .ccf) reading."""
import sys
import os
import shutil
import tempfile
import unittest
from pathlib import Path
import numpy as np

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blackrock_io import BlackrockReader, read_ccf
from blackrock_io.blackrock_reader import NEO_AVAILABLE
from core.reader_factory import open_reader
from models import StreamState


def write_nsx_23(path, data_blocks, period=1, labels=None, units=None):
    """
    Write a minimal NSx file spec 2.3.

    data_blocks: list of (timestamp, int16 array of shape (n_samples, n_channels)).
    Channels are scaled so 1 count = 0.25 units (digital ±1000 -> analog ±250).
    """
    n_ch = data_blocks[0][1].shape[1]
    labels = labels or [f"elec{i + 1}" for i in range(n_ch)]
    units = units or ["uV"] * n_ch

    basic = np.zeros(1, dtype=[
        ("file_id", "S8"), ("ver_major", "u1"), ("ver_minor", "u1"),
        ("bytes_in_headers", "<u4"), ("label", "S16"), ("comment", "S256"),
        ("period", "<u4"), ("timestamp_resolution", "<u4"),
        ("time", "<u2", (8,)), ("channel_count", "<u4"),
    ])
    ext = np.zeros(n_ch, dtype=[
        ("type", "S2"), ("electrode_id", "<u2"), ("electrode_label", "S16"),
        ("physical_connector", "u1"), ("connector_pin", "u1"),
        ("min_digital_val", "<i2"), ("max_digital_val", "<i2"),
        ("min_analog_val", "<i2"), ("max_analog_val", "<i2"),
        ("units", "S16"),
        ("hi_freq_corner", "<u4"), ("hi_freq_order", "<u4"), ("hi_freq_type", "<u2"),
        ("lo_freq_corner", "<u4"), ("lo_freq_order", "<u4"), ("lo_freq_type", "<u2"),
    ])
    basic["file_id"] = b"NEURALCD"
    basic["ver_major"], basic["ver_minor"] = 2, 3
    basic["bytes_in_headers"] = basic.itemsize + ext.itemsize * n_ch
    basic["label"] = b"test"
    basic["period"] = period
    basic["timestamp_resolution"] = 30000
    basic["channel_count"] = n_ch

    ext["type"] = b"CC"
    ext["electrode_id"] = np.arange(1, n_ch + 1)
    ext["electrode_label"] = [l.encode() for l in labels]
    ext["min_digital_val"], ext["max_digital_val"] = -1000, 1000
    ext["min_analog_val"], ext["max_analog_val"] = -250, 250
    ext["units"] = [u.encode() for u in units]

    with open(path, "wb") as f:
        f.write(basic.tobytes())
        f.write(ext.tobytes())
        for timestamp, samples in data_blocks:
            header = np.zeros(1, dtype=[("flag", "u1"), ("ts", "<u4"), ("n", "<u4")])
            header["flag"], header["ts"], header["n"] = 1, timestamp, samples.shape[0]
            f.write(header.tobytes())
            f.write(samples.astype("<i2").tobytes())


CCF_XML = """<?xml version="1.0" encoding="UTF-8"?>
<CCF Version="12">
  <ChanInfo>
    <ChanInfo_item Type="cbPKT_CHANINFO" label="M1-a">
      <chan Type="UINT32">1</chan>
      <scale>
        <physcalin Type="cbSCALING"><anagain Type="INT32">1</anagain><anaunit Type="cstring">uV</anaunit></physcalin>
      </scale>
      <filterdesc>
        <phyfiltin Type="cbFILTDESC"><label Type="cstring">Front End</label><hpfreq Type="UINT32">300</hpfreq></phyfiltin>
      </filterdesc>
      <label Type="cstring">M1-a</label>
      <sample><filter Type="UINT32">0</filter><group Type="UINT32">5</group></sample>
      <spike><threshold><level Type="INT32">-65</level></threshold></spike>
    </ChanInfo_item>
    <ChanInfo_item Type="cbPKT_CHANINFO" label="M1-b">
      <chan Type="UINT32">2</chan>
      <label Type="cstring">M1-b</label>
      <sample><group Type="UINT32">5</group></sample>
    </ChanInfo_item>
  </ChanInfo>
</CCF>
"""


@unittest.skipUnless(NEO_AVAILABLE, "neo not installed")
class TestBlackrockReader(unittest.TestCase):
    """Test reading synthetic .nsX files."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.n_samples = 3000
        rng = np.random.default_rng(0)
        self.counts = rng.integers(-1000, 1000, size=(self.n_samples, 3), dtype=np.int16)
        write_nsx_23(
            self.tmp / "rec001.ns5",
            [(0, self.counts)],
            units=["uV", "uV", "mV"],
        )

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_detects_folder(self):
        self.assertTrue(BlackrockReader.is_blackrock_folder(str(self.tmp)))
        self.assertIsInstance(open_reader(str(self.tmp)), BlackrockReader)

    def test_load_block_metadata(self):
        reader = BlackrockReader()
        block = reader.load_block(str(self.tmp))

        self.assertEqual(block.source, "blackrock")
        self.assertEqual(block.name, "rec001")
        self.assertEqual(list(block.streams), ["ns5"])
        info = block.streams["ns5"]
        self.assertEqual(info.num_channels, 3)
        self.assertEqual(info.sample_rate, 30000.0)
        self.assertEqual(info.num_samples, self.n_samples)
        self.assertAlmostEqual(info.duration, 0.1)
        self.assertEqual(info.channel_labels, ["elec1", "elec2", "elec3"])
        self.assertIsNone(block.metadata["ccf"])

    def test_windowed_read_in_volts(self):
        reader = BlackrockReader()
        reader.load_block(str(self.tmp))

        data, t = reader.get_stream_data("ns5", channels=[0, 2], start_time=0.01, end_time=0.02)

        self.assertEqual(data.shape, (2, 300))
        np.testing.assert_allclose(t, (300 + np.arange(300)) / 30000.0)
        # 1 count = 0.25 uV on ch 0, 0.25 mV on ch 2
        np.testing.assert_allclose(data[0], self.counts[300:600, 0] * 0.25e-6)
        np.testing.assert_allclose(data[1], self.counts[300:600, 2] * 0.25e-3)

    def test_read_clamps_to_stream_end(self):
        reader = BlackrockReader()
        reader.load_block(str(self.tmp))

        data, _ = reader.get_stream_data("ns5", channels=[1], start_time=0.09, end_time=5.0)
        self.assertEqual(data.shape, (1, 300))

    def test_paused_recording_splits_into_segments(self):
        counts = np.zeros((100, 2), dtype=np.int16)
        write_nsx_23(self.tmp / "rec001.ns2", [(0, counts), (90000, counts)], period=30)

        block = BlackrockReader().load_block(str(self.tmp))

        self.assertIn("ns2_seg1", block.streams)
        self.assertIn("ns2_seg2", block.streams)
        self.assertEqual(block.streams["ns2_seg1"].sample_rate, 1000.0)

    def test_ccf_labels_override_nsx_labels(self):
        (self.tmp / "rec001.ccf").write_text(CCF_XML)

        block = BlackrockReader().load_block(str(self.tmp))

        self.assertEqual(block.streams["ns5"].channel_labels, ["M1-a", "M1-b", "elec3"])
        self.assertEqual(len(block.metadata["ccf"]["channels"]), 2)


class TestCcfReader(unittest.TestCase):
    """Test .ccf parsing."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_xml_ccf(self):
        path = self.tmp / "a.ccf"
        path.write_text(CCF_XML)

        ccf = read_ccf(str(path))

        self.assertIsNone(ccf["error"])
        self.assertEqual(ccf["format"], "xml")
        self.assertEqual(ccf["version"], "12")
        self.assertEqual([c["chan"] for c in ccf["channels"]], [1, 2])
        first = ccf["channels"][0]
        self.assertEqual(first["label"], "M1-a")
        self.assertEqual(first["fields"]["spike/threshold/level"], "-65")
        self.assertEqual(first["fields"]["scale/physcalin/anaunit"], "uV")
        # The nested filter label must not shadow the channel label
        self.assertEqual(first["fields"]["filterdesc/phyfiltin/label"], "Front End")

    def test_binary_ccf_reports_error(self):
        path = self.tmp / "old.ccf"
        path.write_bytes(b"cbCCF\x00\x01\x02" + bytes(200))

        ccf = read_ccf(str(path))

        self.assertEqual(ccf["format"], "binary")
        self.assertIn("binary", ccf["error"])
        self.assertEqual(ccf["channels"], [])

    def test_malformed_xml_reports_error(self):
        path = self.tmp / "bad.ccf"
        path.write_text("<CCF><ChanInfo>")

        ccf = read_ccf(str(path))

        self.assertIsNotNone(ccf["error"])


class TestChannelLabel(unittest.TestCase):
    """Test StreamState channel display names."""

    def test_label_formatting(self):
        state = StreamState("ns5", 3, 30000.0, 1.0, channel_labels=["elec1", "", "Ch 3"])
        self.assertEqual(state.channel_label(0), "Ch 1 (elec1)")
        self.assertEqual(state.channel_label(1), "Ch 2")
        self.assertEqual(state.channel_label(2), "Ch 3")
        self.assertEqual(state.channel_label(0, "Channel"), "Channel 1 (elec1)")

    def test_no_labels(self):
        state = StreamState("Wav1", 2, 24000.0, 1.0)
        self.assertEqual(state.channel_label(1), "Ch 2")


class TestReaderFactory(unittest.TestCase):
    """Test format detection."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_tdt_folder(self):
        from tdt_io import TDTReader
        (self.tmp / "block.tev").write_bytes(b"")
        self.assertIsInstance(open_reader(str(self.tmp)), TDTReader)

    def test_unknown_folder(self):
        (self.tmp / "notes.txt").write_text("hi")
        with self.assertRaises(ValueError):
            open_reader(str(self.tmp))


if __name__ == "__main__":
    unittest.main()
