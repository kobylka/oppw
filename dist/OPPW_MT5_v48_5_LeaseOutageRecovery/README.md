# OPPW MT5 v48.5 — lease outage recovery

The supplied log showed a five-second coordination timeout consuming the end
of a 15-second executor lease. The main loop reached its safety boundary while
the renewal worker was still waiting to retry, so it terminated permanently.

v48.5 changes coordination behavior only. Trading rules, sizing, order types,
SL/TP logic, and schedules are unchanged.

## Behavior

- Normal lease TTL defaults to 30 seconds, heartbeat to 3 seconds, and safety
  margin to 5 seconds.
- A transport timeout is retried after at most 0.5 seconds instead of waiting
  another complete heartbeat interval.
- An explicit renewal rejection or changed fencing token invalidates ownership
  immediately.
- Once the cached lease reaches its safety boundary, executor/publisher role
  activity is suspended. No BUY, SELL, SL/TP change, or publication is initiated
  under uncertain ownership.
- The process remains alive and attempts global MySQL lease acquisition.
- It resumes only after the backend returns a valid lease and fencing token.
- If another computer owns the lease, this process remains suspended and waits.
- No local filesystem lock is introduced.

Expected transient-outage log:

```text
EVENT GLOBAL_LEASE_RENEW_DEFERRED ... retry_in=0.50s safe_for=...
```

If the outage outlives the safe lease window:

```text
EVENT EXECUTOR_SUSPENDED_LEASE_INVALID ...
EVENT GLOBAL_LEASE_REACQUIRE_WAIT ...
EVENT GLOBAL_LEASE_REACQUIRED ... fencing_token=...
EVENT EXECUTOR_RESUMED_LEASE_REACQUIRED ...
```

## Install

Stop the account processes and run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\install_v48_5.ps1 `
  -RepoRoot D:\oppw
```

The installer replaces only continuous-loop source files. It does not overwrite
private account configuration or credentials.

Ensure each private config uses these values unless intentionally overridden by
environment variables:

```python
coordination_timeout_seconds = 5.0
role_lease_ttl_seconds = 30.0
role_lease_heartbeat_seconds = 3.0
role_lease_safety_margin_seconds = 5.0
```

Restart PUBLISHER first, followed by EXECUTOR. The startup build must be:

```text
2026-07-21-lease-outage-recovery-v48.5
```

No backend or SQL migration is required.

