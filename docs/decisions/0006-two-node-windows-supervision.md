# ADR 0006: Two-node Windows supervision with backend assignment

- Status: Accepted
- Date: 2026-07-22

## Context

The canonical MT5 entrypoint had global leases and fencing, but processes still had to be launched manually. Leases prevented dual ownership but were first-come/first-served, so they did not provide master priority, automatic backup activation, continuous restart, or audited mobile desired-state controls.

## Decision

Install one canonical `OPPWContinuousSupervisor` Windows service on each of two machines. One node is `MASTER` and one is `BACKUP`. Each service reports to the canonical `service-control.php` endpoint and manages the same four canonical invocations: Demo and Real, each with Executor and Publisher roles.

The backend is the assignment authority. A fresh master heartbeat assigns all desired-running roles to the master and idles the backup. When the master heartbeat becomes stale, the backend assigns those roles to the backup. Returning master heartbeats revoke backup assignment. Existing global role leases, fencing tokens, trade gates, and weekly-entry claims remain authoritative during every transition.

Paired mobile devices may change desired state only when their account permission explicitly grants service control. Commands use unique request IDs and immutable audit records. They never grant a lease or bypass fencing. If the supervisor cannot refresh assignments, it starts nothing and stops managed children after the bounded assignment TTL.

## Consequences

- Both Windows services run continuously, but only the assigned node runs MT5 children.
- Master preference may briefly delay takeover while a safely released or expired lease changes owner; it never creates dual legitimate ownership.
- Stopping a role in Mobile applies globally to master and backup. The Windows supervisor remains alive so Mobile can start it again.
- The private service token and node identity live under `%ProgramData%\OPPW` with restricted ACLs and remain outside Git.
