from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("update_quotes.py")
SPEC = importlib.util.spec_from_file_location("update_quotes_under_test", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {SCRIPT}")
update_quotes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_quotes)


class UpdateQuotesTest(unittest.TestCase):
    def test_reads_first_and_last_intraday_dates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qqq.csv"
            path.write_bytes(
                b"20180413;00:00;1;2;0;1\r\n"
                b"20180413;00:01;1;2;0;1\r\n"
                b"20260820;22:14;1;2;0;1\r\n"
            )

            self.assertEqual(date(2018, 4, 13), update_quotes.read_intraday_boundary(path, first=True))
            self.assertEqual(date(2026, 8, 20), update_quotes.read_intraday_boundary(path, first=False))

    def test_converted_day_requires_exact_session_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "combined_dst_adjusted.csv"
            rows = [f"20260820;00:00;1;2;0;1\n"] * update_quotes.ROWS_PER_INTRADAY_DAY
            path.write_text("".join(rows), encoding="utf-8")

            counts = update_quotes.inspect_converted_days(
                path,
                last_existing_day=date(2026, 8, 19),
                through_day=date(2026, 8, 20),
            )

            self.assertEqual({date(2026, 8, 20): update_quotes.ROWS_PER_INTRADAY_DAY}, counts)

            path.write_text("".join(rows[:-1]), encoding="utf-8")
            with self.assertRaises(update_quotes.UpdateError):
                update_quotes.inspect_converted_days(
                    path,
                    last_existing_day=date(2026, 8, 19),
                    through_day=date(2026, 8, 20),
                )

    def test_extracts_and_validates_qqq_from_stooq_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "d_us_txt.zip"
            destination = root / "qqq.us.txt"
            content = (
                "<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>\n"
                "QQQ.US,D,20260819,000000,1,2,0,1.5,100,0\n"
                "QQQ.US,D,20260820,000000,2,3,1,2.5,200,0\n"
            )
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("data/daily/us/nasdaq etfs/qqq.us.txt", content)

            update_quotes.extract_stooq_qqq(archive, destination)

            self.assertEqual(
                (date(2026, 8, 19), date(2026, 8, 20), 2),
                update_quotes.inspect_stooq_daily(destination),
            )

    def test_promoted_artifacts_receive_parent_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.csv"
            staged = root / "staged.csv"
            target.write_text("old", encoding="utf-8")
            staged.write_text("new", encoding="utf-8")

            with mock.patch.object(update_quotes, "reset_windows_acl_to_parent") as reset_acl:
                update_quotes.replace_artifacts({target: staged})

            self.assertEqual("new", target.read_text(encoding="utf-8"))
            reset_acl.assert_called_once_with(target)


if __name__ == "__main__":
    unittest.main()
