# OPPW MT5 v50 — Session-indexed TPP and PRE H

Build:

```text
2026-07-21-session-indexed-tpp-premarket-ramp-v50
```

## TPP schedule

TPP is selected by the position of the actual XNYS trading session within the
ISO week, rather than by the calendar weekday number.

Normal week:

```text
Monday     0.7%
Tuesday    2.0%
Wednesday  5.0%
Thursday   5.0%
Friday     5.0%
```

Monday holiday / Tuesday-first week:

```text
Tuesday    0.7%
Wednesday  2.0%
Thursday   5.0%
Friday     5.0%
```

The same session-indexed value is used by OH execution, CH execution, minute
condition reports, closest-condition calculations, the full condition list,
and the mobile position's potential take-profit field.

## PRE H

On the second actual trading session after the weekly entry, PRE H scales
linearly from the first TPP at configured premarket start (00:00 by default) to
the second TPP at the exchange-calendar cash open.

This applies to:

- Tuesday after a normal Monday entry;
- Wednesday after Tuesday was the first trading day and entry day;
- the second actual session after entry if another exchange holiday intervenes.

With a 15:30 Warsaw cash open, the default ramp is:

```text
00:00  0.7000%
01:00  0.7839%
08:00  1.3710%
15:00  1.9581%
15:29  1.9986%
15:30  2.0000%
```

The exchange calendar determines cash open, so the ramp also remains aligned
during US/European DST mismatch weeks. PRE H checks each new M1 bar's opening
price. A crossed threshold submits the existing globally fenced market SELL
with exit reason `PRE H`.

During the ramp, every monitor snapshot contains a `PRE H` price condition with
the current target price, current market price, distance, and exact interpolated
`potentialTpPercent`. Mobile v14.3.1 shows it under Closest condition or All
other conditions as `Current potential TP level`.

## Installation

Stop both loops, then run from the extracted package directory:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\install_v50.ps1 `
  -RepoRoot D:\oppw
```

The installer updates the generic, Demo, and Real runtime copies and verifies
their SHA-256 hashes. It does not overwrite private configuration, state, logs,
or credentials.

Restart PUBLISHER first, then EXECUTOR.

No SQL, PHP, backend, Android, or configuration migration is required.
