import json
import tempfile
import unittest
from pathlib import Path
from service.oppw_windows_supervisor import (
    ACCOUNTS, ROLES, STARTUP_ORDER, assignments_fresh, load_config, next_start_key,
)


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

    def test_installer_uses_locale_independent_builtin_sids(self):
        installer = (Path(__file__).resolve().parents[1] / "install-service.ps1").read_text(encoding="utf-8")
        self.assertIn("*S-1-5-18:(F)", installer)
        self.assertIn("*S-1-5-32-544:(F)", installer)
        self.assertNotIn("'Administrators:(F)'", installer)

    def test_installer_runs_host_as_local_system_for_interactive_launch(self):
        installer = (Path(__file__).resolve().parents[1] / "install-service.ps1").read_text(encoding="utf-8")
        host = (Path(__file__).resolve().parents[1] / "OPPWServiceHost.cs").read_text(encoding="utf-8")
        self.assertIn("$runtimeSid", installer)
        self.assertNotIn("-Credential $ServiceCredential", installer)
        self.assertIn("WTSQueryUserToken", host)
        self.assertIn("CreateProcessAsUser", host)
        self.assertIn('startup.lpDesktop = "winsta0\\\\default"', host)

    def test_all_mt5_startups_are_serialized_by_explicit_readiness(self):
        assignments = {key: True for key in STARTUP_ORDER}
        states = {key: (False, False) for key in STARTUP_ORDER}
        self.assertEqual(("DEMO", "EXECUTOR"), next_start_key(assignments, states))
        states[("DEMO", "EXECUTOR")] = (True, False)
        self.assertIsNone(next_start_key(assignments, states))
        states[("DEMO", "EXECUTOR")] = (True, True)
        self.assertEqual(("REAL", "EXECUTOR"), next_start_key(assignments, states))
        states[("REAL", "EXECUTOR")] = (True, True)
        self.assertEqual(("DEMO", "PUBLISHER"), next_start_key(assignments, states))

    def test_failed_demo_backoff_does_not_block_real_startup(self):
        assignments = {key: True for key in STARTUP_ORDER}
        states = {key: (False, False) for key in STARTUP_ORDER}
        eligible = {key: True for key in STARTUP_ORDER}
        eligible[("DEMO", "EXECUTOR")] = False
        self.assertEqual(("REAL", "EXECUTOR"), next_start_key(assignments, states, eligible))
        states[("DEMO", "EXECUTOR")] = (True, False)
        self.assertIsNone(next_start_key(assignments, states, eligible))

    def test_supervisor_passes_unique_ready_file_to_each_child(self):
        supervisor = (Path(__file__).resolve().parents[1] / "oppw_windows_supervisor.py").read_text(encoding="utf-8")
        strategy = (Path(__file__).resolve().parents[2] / "mt5" / "oppw_mt5_continuous.py").read_text(encoding="utf-8")
        self.assertIn('f"ready-{account.lower()}-{role.lower()}.json"', supervisor)
        self.assertIn('"--service-ready-file", str(item.ready_file)', supervisor)
        self.assertIn('os.replace(temporary_ready_file, self.service_ready_file)', strategy)
        connect = strategy[strategy.index("    def connect(self) -> None:"):strategy.index("    def disconnect(self) -> None:")]
        ready_position = connect.index("os.replace(temporary_ready_file, self.service_ready_file)")
        self.assertGreater(ready_position, connect.index("mt5.account_info()"))
        self.assertGreater(ready_position, connect.index("mt5.symbol_select(self.cfg.signal_symbol"))
        self.assertGreater(ready_position, connect.index('self.ensure_autotrading_enabled("CONNECT"'))

    def test_installer_accepts_service_already_marked_for_deletion(self):
        installer = (Path(__file__).resolve().parents[1] / "install-service.ps1").read_text(encoding="utf-8")
        self.assertIn("$exitCode -ne 1072", installer)
        self.assertIn("Remove-ServiceRegistration $serviceName", installer)
        self.assertIn("Close Services (services.msc)", installer)


if __name__ == "__main__":
    unittest.main()
