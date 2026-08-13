# Windows continuous supervisor

Install the same `OPPWContinuousSupervisor` service on two Windows machines. Install one with `-NodeRole Master` and the other with `-NodeRole Backup`. Both services remain running; the backend assigns every configured account/role process to the master while its heartbeat is fresh and assigns them to the backup after the master becomes stale.

Run from elevated PowerShell after placing the private Demo and Real configuration files in their canonical locations:

```powershell
.\service\install-service.ps1 -NodeRole Master -RepoRoot D:\oppw -PythonPath C:\Path\To\python.exe -RuntimeUser MACHINE\mt5user
```

Use `-NodeRole Backup` on the second computer. The installer uses the compiled host included in an official release, or builds it from source in a development checkout. It securely prompts for the backend write token. `RuntimeUser` must be the Windows account that owns that machine's Python and MetaTrader installations; it defaults to the account running the installer. The service itself runs as LocalSystem and launches the Python supervisor into that user's active or disconnected interactive session. Keep the runtime user signed in (locking or disconnecting is supported); while the user is logged out, the service remains online but starts no trading processes. The installer stores service material under `%ProgramData%\OPPW`, configures automatic delayed start, and enables Windows service recovery. Protected Administrators ownership and exact ACLs allow only SYSTEM and Administrators to modify `bin`, `OPPWServiceHost.exe`, and `service.json`; the runtime user has root read/traverse access for configuration and stop-signal observation, and can modify only `runtime` and `logs`. Re-running the elevated installer repairs legacy ownership and inherited permissions.

Named accounts are explicit and ordered. Register them in the backend, create each ignored private config, and pass the identical list on Master and Backup:

```powershell
php .\Mobile\backend\admin\register_account.php --account=DEMO_TMS --type=DEMO --display-name="DEMO TMS" --sort-order=40
php .\Mobile\backend\admin\register_account.php --account=REAL_TMS --type=REAL --display-name="REAL TMS" --sort-order=30
$accounts = @('DEMO:DEMO','DEMO:DEMO_TMS','REAL:REAL','REAL:REAL_TMS')
.\service\install-service.ps1 -NodeRole Master -Accounts $accounts -RepoRoot D:\oppw -PythonPath C:\Path\To\python.exe -RuntimeUser MACHINE\mt5user
```

Descriptors use `TYPE:ACCOUNT_KEY`; one to eight unique keys are supported. Re-running without `-Accounts` preserves an existing managed-account list and otherwise defaults to `DEMO:DEMO` plus `REAL:REAL`. Enabled backend accounts must exactly match the list or the supervisor fails closed. Every concurrent broker login requires its own MetaTrader installation/terminal path.

The Bossa accounts keep keys `DEMO` and `REAL` so historical authority remains intact; Mobile labels them `DEMO BOSSA` and `REAL BOSSA`. The account migration creates `DEMO_TMS` and `REAL_TMS` disabled. To activate them, first populate the TMS private files on both machines, stop both supervisors, enable/register the TMS accounts, and reinstall both services with the same four-account list.

Mobile start/stop controls affect the selected account and role globally. They do not stop the Windows supervisor itself, bypass leases, or allow two active owners. Devices must be paired using a pairing code with the explicit service-control permission.

Assigned processes start one at a time: all configured Executors in account-list order, then all Publishers in the same order. A child must confirm its MT5 connection, selected account and symbols, and executor AutoTrading state before the next child is launched. A failed or timed-out startup is backed off rather than allowing simultaneous MT5 IPC initialization.
