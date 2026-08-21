from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("json_converter.py")
SPEC = importlib.util.spec_from_file_location("json_converter_under_test", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {SCRIPT}")
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


class JsonConverterTest(unittest.TestCase):
    def test_empty_weekend_payload_with_null_prices_is_ignored(self) -> None:
        payload = {
            "timestamp": 1786752000000,
            "multiplier": 0.001,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "shift": 60000,
            "times": [],
            "opens": [],
            "highs": [],
            "lows": [],
            "closes": [],
        }

        with tempfile.TemporaryDirectory() as directory:
            json_file = Path(directory) / "2026-08-15.json"
            self.assertEqual([], converter.decode_json_file(json_file, payload))


if __name__ == "__main__":
    unittest.main()
