import json
import tempfile
import unittest
from pathlib import Path
from service.oppw_windows_supervisor import (
    ManagedAccount, assignments_fresh, load_config, managed_accounts, next_start_key,
    private_config_path, ready_capability_status, startup_order,
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

    def test_legacy_config_defaults_to_demo_and_real_process_keys(self):
        accounts = managed_accounts({})
        self.assertEqual(
            {("DEMO", "EXECUTOR"), ("DEMO", "PUBLISHER"), ("REAL", "EXECUTOR"), ("REAL", "PUBLISHER")},
            set(startup_order(accounts)),
        )

    def test_named_accounts_are_validated_and_apply_canonical_startup_priority(self):
        accounts = managed_accounts({
            "managedAccounts": [
                {"accountKey": "DEMO_ALPHA", "accountType": "demo"},
                {"accountKey": "DEMO_BETA", "accountType": "DEMO"},
                {"accountKey": "REAL_PROP", "accountType": "REAL"},
            ]
        })
        self.assertEqual(
            (
                ("DEMO_ALPHA", "EXECUTOR"), ("DEMO_BETA", "EXECUTOR"), ("REAL_PROP", "EXECUTOR"),
                ("DEMO_ALPHA", "PUBLISHER"), ("DEMO_BETA", "PUBLISHER"), ("REAL_PROP", "PUBLISHER"),
            ),
            startup_order(accounts),
        )
        priority_accounts = managed_accounts({"managedAccounts": [
            {"accountKey": "DEMO", "accountType": "DEMO"},
            {"accountKey": "DEMO_TMS", "accountType": "DEMO"},
            {"accountKey": "REAL", "accountType": "REAL"},
            {"accountKey": "REAL_TMS", "accountType": "REAL"},
        ]})
        self.assertEqual(
            (
                ("REAL", "EXECUTOR"), ("REAL_TMS", "EXECUTOR"),
                ("DEMO", "EXECUTOR"), ("DEMO_TMS", "EXECUTOR"),
                ("REAL", "PUBLISHER"), ("REAL_TMS", "PUBLISHER"),
                ("DEMO", "PUBLISHER"), ("DEMO_TMS", "PUBLISHER"),
            ),
            startup_order(priority_accounts),
        )
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            managed_accounts({"managedAccounts": [
                {"accountKey": "DEMO_ALPHA", "accountType": "DEMO"},
                {"accountKey": "demo_alpha", "accountType": "REAL"},
            ]})
        with self.assertRaisesRegex(RuntimeError, "accountType"):
            managed_accounts({"managedAccounts": [{"accountKey": "BROKER", "accountType": "OTHER"}]})
        with self.assertRaisesRegex(RuntimeError, "Reserved accountKey"):
            managed_accounts({"managedAccounts": [{"accountKey": "DEMO", "accountType": "REAL"}]})
        with self.assertRaisesRegex(RuntimeError, "1-8"):
            managed_accounts({"managedAccounts": [
                {"accountKey": f"DEMO_{index}", "accountType": "DEMO"}
                for index in range(9)
            ]})
        self.assertEqual(
            Path("repo/mt5/demo/demo_alpha_mt5_config.py"),
            private_config_path(Path("repo"), ManagedAccount("DEMO_ALPHA", "DEMO")),
        )

    def test_assignments_expire_fail_closed(self):
        self.assertTrue(assignments_fresh(100.0, 15.0, now=114.9))
        self.assertFalse(assignments_fresh(100.0, 15.0, now=115.0))
        self.assertFalse(assignments_fresh(0.0, 15.0, now=1.0))

    def test_installer_uses_locale_independent_builtin_sids(self):
        installer = (Path(__file__).resolve().parents[1] / "install-service.ps1").read_text(encoding="utf-8")
        self.assertIn("SecurityIdentifier]::new('S-1-5-18')", installer)
        self.assertIn("SecurityIdentifier]::new('S-1-5-32-544')", installer)
        self.assertNotIn("'Administrators:(F)'", installer)

    def test_installer_protects_local_system_host_from_runtime_user_writes(self):
        installer = (Path(__file__).resolve().parents[1] / "install-service.ps1").read_text(encoding="utf-8")
        self.assertIn("$acl.SetAccessRuleProtection($true, $false)", installer)
        self.assertIn("RemoveAccessRuleSpecific", installer)
        self.assertIn("$acl.SetOwner($administratorsIdentity)", installer)
        self.assertIn(
            "Set-ExactPathAcl -Path $programData -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Traverse -RuntimeChildrenInherit",
            installer,
        )
        self.assertIn("Set-ExactPathAcl -Path $binDir -RuntimeSid $runtimeSecurityIdentifier", installer)
        self.assertIn("Set-ExactPathAcl -Path $hostPath -RuntimeSid $runtimeSecurityIdentifier", installer)
        self.assertIn(
            "Set-ExactPathAcl -Path $runtimeDir -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Modify -RuntimeChildrenInherit",
            installer,
        )
        self.assertIn(
            "Set-ExactPathAcl -Path $logDir -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Modify -RuntimeChildrenInherit",
            installer,
        )
        self.assertIn(
            "Set-ExactPathAcl -Path $configPath -RuntimeSid $runtimeSecurityIdentifier -RuntimeAccess Read",
            installer,
        )
        self.assertNotIn("icacls.exe $programData", installer)
        self.assertNotIn('"*${runtimeSid}:(OI)(CI)(M)"', installer)
        self.assertNotRegex(
            installer,
            r"Set-ExactPathAcl -Path \$(?:programData|binDir|hostPath|configPath)[^\r\n]*-RuntimeAccess Modify",
        )

    def test_installer_runs_host_as_local_system_for_interactive_launch(self):
        installer = (Path(__file__).resolve().parents[1] / "install-service.ps1").read_text(encoding="utf-8")
        host = (Path(__file__).resolve().parents[1] / "OPPWServiceHost.cs").read_text(encoding="utf-8")
        self.assertIn("$runtimeSid", installer)
        self.assertNotIn("-Credential $ServiceCredential", installer)
        self.assertIn("WTSQueryUserToken", host)
        self.assertIn("CreateProcessAsUser", host)
        self.assertIn('startup.lpDesktop = "winsta0\\\\default"', host)

    def test_installer_persists_and_preserves_explicit_managed_accounts(self):
        installer = (Path(__file__).resolve().parents[1] / "install-service.ps1").read_text(encoding="utf-8")
        self.assertIn("[string[]]$Accounts = @()", installer)
        self.assertIn("$existing.managedAccounts", installer)
        self.assertIn("managedAccounts = $managedAccounts", installer)
        self.assertIn("DEMO:ACCOUNT_KEY or REAL:ACCOUNT_KEY", installer)

    def test_all_mt5_startups_are_serialized_by_explicit_readiness(self):
        order = startup_order((ManagedAccount("DEMO", "DEMO"), ManagedAccount("REAL", "REAL")))
        assignments = {key: True for key in order}
        states = {key: (False, False) for key in order}
        self.assertEqual(("REAL", "EXECUTOR"), next_start_key(order, assignments, states))
        states[("REAL", "EXECUTOR")] = (True, False)
        self.assertIsNone(next_start_key(order, assignments, states))
        states[("REAL", "EXECUTOR")] = (True, True)
        self.assertEqual(("DEMO", "EXECUTOR"), next_start_key(order, assignments, states))

    def test_failed_demo_backoff_does_not_block_real_startup(self):
        order = startup_order((ManagedAccount("DEMO", "DEMO"), ManagedAccount("REAL", "REAL")))
        assignments = {key: True for key in order}
        states = {key: (False, False) for key in order}
        eligible = {key: True for key in order}
        eligible[("DEMO", "EXECUTOR")] = False
        self.assertEqual(("REAL", "EXECUTOR"), next_start_key(order, assignments, states, eligible))
        states[("DEMO", "EXECUTOR")] = (True, False)
        self.assertIsNone(next_start_key(order, assignments, states, eligible))

    def test_supervisor_passes_unique_ready_file_to_each_child(self):
        supervisor = (Path(__file__).resolve().parents[1] / "oppw_windows_supervisor.py").read_text(encoding="utf-8")
        strategy = (Path(__file__).resolve().parents[2] / "mt5" / "oppw_mt5_continuous.py").read_text(encoding="utf-8")
        self.assertIn('f"ready-{account.account_key.lower()}-{role.lower()}.json"', supervisor)
        self.assertIn('"--service-ready-file", str(item.ready_file)', supervisor)
        self.assertIn('"--account-key", item.account', supervisor)
        self.assertIn('os.replace(temporary_ready_file, self.service_ready_file)', strategy)
        connect = strategy[strategy.index("    def connect(self) -> None:"):strategy.index("    def disconnect(self) -> None:")]
        ready_position = connect.index("os.replace(temporary_ready_file, self.service_ready_file)")
        self.assertGreater(ready_position, connect.index("mt5.account_info()"))
        self.assertGreater(ready_position, connect.index("mt5.symbol_select(self.cfg.signal_symbol"))
        self.assertGreater(ready_position, connect.index('self.ensure_autotrading_enabled("CONNECT"'))
        self.assertIn('"liveEnabled": bool(self.cfg.live_enabled)', connect)
        self.assertIn('"autotradingEnabled": bool(autotrading_enabled)', connect)
        self.assertIn("live={live_status} autotrading={autotrading_status}", supervisor)

    def test_ready_capability_status_reads_loop_readiness_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ready.json"
            path.write_text(
                json.dumps({"liveEnabled": True, "autotradingEnabled": False}),
                encoding="utf-8",
            )
            self.assertEqual(("ENABLED", "DISABLED"), ready_capability_status(path))
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(("UNKNOWN", "UNKNOWN"), ready_capability_status(path))

    def test_installer_accepts_service_already_marked_for_deletion(self):
        installer = (Path(__file__).resolve().parents[1] / "install-service.ps1").read_text(encoding="utf-8")
        self.assertIn("$exitCode -ne 1072", installer)
        self.assertIn("Remove-ServiceRegistration $serviceName", installer)
        self.assertIn("Close Services (services.msc)", installer)


if __name__ == "__main__":
    unittest.main()
