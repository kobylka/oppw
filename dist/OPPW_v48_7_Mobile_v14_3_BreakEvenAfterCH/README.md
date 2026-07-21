# OPPW MT5 v48.7 / Mobile v14.3

Break-even arming no longer waits for the 22:01 close-processing pass. It is
evaluated immediately after the scheduled CH check using the same live signal
price.

## Close-action order

At the XNYS session close minus three seconds:

1. CH is evaluated first.
2. If CH is true, the position is closed by CH and no break-even check runs.
3. On the final trading day, if CH is false, TO closes the position and no
   break-even check runs.
4. On another eligible day, if CH is false, break-even arming is evaluated
   immediately using the same live signal price.

This normally occurs at `21:59:57 Europe/Warsaw`, at `20:59:57` during the
US/Europe DST mismatch, or three seconds before the actual XNYS close on an
early-close session.

The entry day is not eligible. A Tuesday entry therefore gets its first
break-even check on Wednesday at the close-minus-three-seconds action.

Break-even arming after CH does not retroactively apply the current day's
already-observed high to BH. BH becomes active from the following session.

## Mobile app

The first Position ticket displays the next break-even check and states that
arming occurs immediately after CH. Android version:

```text
versionName = 14.3.0
versionCode = 30
```

## Install

1. Stop PUBLISHER and EXECUTOR.
2. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass `
     -File .\install_v48_7.ps1 `
     -RepoRoot D:\oppw
   ```

3. Restart PUBLISHER first, then EXECUTOR.
4. Install `android/OPPW-Monitor-v14.3-debug.apk` over the existing app.

Expected MT5 build:

```text
2026-07-21-break-even-after-ch-v48.7
```

No backend or SQL migration is required for this release. The installer does
not overwrite private account configuration files.
