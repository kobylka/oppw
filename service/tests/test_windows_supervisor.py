import json
import tempfile
import unittest
from pathlib import Path
from service.oppw_windows_supervisor import ACCOUNTS, ROLES, assignments_fresh, load_config


class SupervisorConfigTests(unittest.TestCase):
    def test_requires_https_and_known_node_role(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "service.json"
            base = {
                "nodeId": "a" * 32, "nodeRole": "MASTER", "repoRoot": directory,
                "pythonPath": "python.exe", "controlUrl": "http://unsafe/service-control.php",
                "writeToken": "secret",
            }
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                load_config(path)
            base["controlUrl"] = "https://backend/service-control.php"
            base["nodeRole"] = "third"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "MASTER or BACKUP"):
                load_config(path)

    def test_exactly_four_canonical_process_keys(self):
        self.assertEqual(
            {("DEMO", "EXECUTOR"), ("DEMO", "PUBLISHER"), ("REAL", "EXECUTOR"), ("REAL", "PUBLISHER")},
            {(account, role) for account in ACCOUNTS for role in ROLES},
        )

    def test_assignments_expire_fail_closed(self):
        self.assertTrue(assignments_fresh(100.0, 15.0, now=114.9))
        self.assertFalse(assignments_fresh(100.0, 15.0, now=115.0))
        self.assertFalse(assignments_fresh(0.0, 15.0, now=1.0))


if __name__ == "__main__":
    unittest.main()
