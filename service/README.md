# Windows continuous supervisor

Install the same `OPPWContinuousSupervisor` service on two Windows machines. Install one with `-NodeRole Master` and the other with `-NodeRole Backup`. Both services remain running; the backend assigns all four canonical processes to the master while its heartbeat is fresh and assigns them to the backup after the master becomes stale.

Run from elevated PowerShell after placing the private Demo and Real configuration files in their canonical locations:

```powershell
.\service\install-service.ps1 -NodeRole Master -RepoRoot D:\oppw -PythonPath C:\Path\To\python.exe -RuntimeUser MACHINE\mt5user
```

Use `-NodeRole Backup` on the second computer. The installer uses the compiled host included in an official release, or builds it from source in a development checkout. It securely prompts for the backend write token. `RuntimeUser` must be the Windows account that owns that machine's Python and MetaTrader installations; it defaults to the account running the installer. The service itself runs as LocalSystem and launches the Python supervisor into that user's active or disconnected interactive session. Keep the runtime user signed in (locking or disconnecting is supported); while the user is logged out, the service remains online but starts no trading processes. The installer stores service configuration under `%ProgramData%\OPPW`, restricts its ACL to SYSTEM, Administrators, and the runtime account, configures automatic delayed start, and enables Windows service recovery.

Mobile start/stop controls affect the selected account and role globally. They do not stop the Windows supervisor itself, bypass leases, or allow two active owners. Devices must be paired using a pairing code with the explicit service-control permission.
