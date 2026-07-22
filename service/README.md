# Windows continuous supervisor

Install the same `OPPWContinuousSupervisor` service on two Windows machines. Install one with `-NodeRole Master` and the other with `-NodeRole Backup`. Both services remain running; the backend assigns all four canonical processes to the master while its heartbeat is fresh and assigns them to the backup after the master becomes stale.

Run from elevated PowerShell after placing the private Demo and Real configuration files in their canonical locations:

```powershell
.\service\install-service.ps1 -NodeRole Master -RepoRoot D:\oppw -PythonPath C:\Path\To\python.exe
```

Use `-NodeRole Backup` on the second computer. The installer uses the compiled host included in an official release, or builds it from source in a development checkout. It securely prompts for the backend write token and a Windows service credential. Use the Windows account that owns and can launch that machine's MetaTrader installations; it must have the `Log on as a service` right. The installer stores service configuration under `%ProgramData%\OPPW`, restricts its ACL to SYSTEM, Administrators, and read-only access for the service account, configures automatic delayed start, and enables Windows service recovery.

Mobile start/stop controls affect the selected account and role globally. They do not stop the Windows supervisor itself, bypass leases, or allow two active owners. Devices must be paired using a pairing code with the explicit service-control permission.
