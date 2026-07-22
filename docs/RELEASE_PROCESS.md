# Release process

## Purpose

`tools/release.ps1` is the only supported release path. It packages committed canonical sources rather than copying whichever versioned files happen to be present in an account directory.

Repository work is governed by root `AGENTS.md`, `CURRENT_ARCHITECTURE.md`, `CONTRACT_POLICY.md`, the change checklist, and accepted records under `docs/decisions/`. The source validator requires these controls to remain present.

## Preconditions

- Work from a clean Git commit.
- Keep populated MT5/backend/Android secrets outside Git.
- Install Python, PHP CLI, Docker with a running engine, JDK 17, the Android SDK, and the Windows .NET Framework C# compiler.
- Do not manually edit or commit `dist/`.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release.ps1 -RepoRoot D:\oppw
```

Use `-ValidateOnly` to run the complete gate without creating an archive.

## Enforced gate

The release stops on any failure:

1. repository is dirty or contains unignored files;
2. source layout violates canonical-source rules;
3. Python compilation, MT5/supervisor regression tests, or Windows service-host compilation fail;
4. a PHP file fails linting;
5. the ordered SQL chain fails against temporary MySQL or immutable tables/triggers are missing;
6. the executable publisher/PHP/MySQL/read-API/Android contract fails;
7. Android unit tests or APK build fail.

On success, `dist/OPPW-<VERSION>.zip` and its SHA-256 file are created. The archive contains the Android APK, compiled Windows service host, installer/supervisor sources, and a per-file SHA-256 manifest. `dist/` remains ignored because releases are reproducible outputs, not source.

## Version change

Edit only `VERSION` using `MAJOR.MINOR.PATCH`. The MT5 build ID, strategy specification version, Android version name, Android version code, archive name, and manifest all derive from it.
