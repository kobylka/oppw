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

On success, `dist/OPPW-<VERSION>.zip` and its SHA-256 file are created, where `<VERSION>` is root `VERSION`. The archive contains both canonical version files, the Android APK, compiled Windows service host, installer/supervisor sources, and a per-file SHA-256 manifest. `dist/` remains ignored because releases are reproducible outputs, not source.

## Version change

Edit root `VERSION` using `MAJOR.MINOR.PATCH` when releasing the product/MT5/backend/service line. The MT5 build ID, strategy specification version, archive name, and manifest derive from it.

Edit `Mobile/VERSION` using `MAJOR.MINOR.PATCH` when releasing Android. Android `versionName` is that value. Android `versionCode` is `1,000,000 + major * 10,000 + minor * 100 + patch`; minor and patch must each be between 0 and 99. The epoch keeps the independent mobile line upgrade-safe after historical builds used the larger product-derived code.
