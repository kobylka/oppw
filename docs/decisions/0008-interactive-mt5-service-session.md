# ADR 0008: Launch MT5 supervision in the owner's interactive session

- Status: Accepted
- Date: 2026-07-22
- Supersedes: the service-account launch detail in ADR 0006

## Context

The initial Windows host ran the Python supervisor directly as the service account in Session 0. The MetaTrader desktop terminal could not establish its Python IPC channel there, causing continuous `IPC timeout`, `IPC send failed`, and `IPC recv failed` exits. Starting executor and publisher simultaneously also allowed both clients to race initialization of the same per-account terminal.

## Decision

Run the durable `OPPWContinuousSupervisor` host as LocalSystem. The host resolves an explicitly configured runtime-user SID, finds that user's active or disconnected Windows session, and uses `CreateProcessAsUser` with the session token to launch the canonical Python supervisor on `winsta0\default`. No user password is stored. When no matching session exists, the host remains running and waits fail-closed for sign-in.

Within each account, start the executor first and delay publisher startup until the executor has survived the bounded MetaTrader initialization interval. Demo and Real remain independent. The service job object still owns and terminates the complete managed process tree.

## Consequences

- MetaTrader and its Python bridge run in the desktop context they require.
- The runtime user must remain signed in; locking and disconnected sessions are supported, but logging out stops the managed tree until the next sign-in.
- The LocalSystem host stores no runtime-user password and cannot start trading processes under an unrelated session.
- Backend assignment, global leases, fencing, weekly claims, and mobile desired state remain unchanged and authoritative.
