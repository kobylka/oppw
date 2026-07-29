# ADR 0017: Protect the LocalSystem service code boundary

- Status: Accepted
- Date: 2026-07-29
- Supersedes: the `%ProgramData%\OPPW` ACL detail in ADR 0006

## Context

The Windows supervisor host runs as LocalSystem so it can obtain the explicitly configured runtime user's interactive-session token. The original installer granted that runtime user inherited Modify access over the whole `%ProgramData%\OPPW` tree. Because `bin\OPPWServiceHost.exe` lived inside that tree, the lower-privileged runtime account could replace code that the Service Control Manager would execute as LocalSystem after a restart.

Protecting only the executable file is insufficient: write access to its containing directory can permit replacement, and write access to the configuration's parent can permit deletion or substitution of the protected file.

## Decision

The elevated installer assigns the built-in Administrators group as owner and applies exact, non-inherited allowlists to the service paths before registration or startup:

- SYSTEM and Administrators have Full Control over `%ProgramData%\OPPW` and every protected or runtime subtree;
- the runtime user has inherited read/traverse access at the root so it can read `service.json` and observe the service stop signal;
- only SYSTEM and Administrators can modify `bin` and `bin\OPPWServiceHost.exe`;
- the runtime user has inherited Modify access only within the dedicated `runtime` and `logs` directories.

Re-running the installer replaces legacy ownership, removes inherited and explicit access rules from these paths, and reapplies the canonical allowlists. Source validation and supervisor regression tests reject the former root-wide runtime Modify grant.

## Consequences

- Compromise of the interactive MT5 runtime account cannot be escalated to LocalSystem by replacing the service host or its configuration.
- Runtime readiness, stop files, and logs remain writable without weakening the privileged code boundary.
- Service installation and upgrades remain elevated operations; an administrator must use the canonical installer to replace the protected host.
- Deployment validation must preserve the separation between protected `bin`/configuration material and runtime-writable data.
