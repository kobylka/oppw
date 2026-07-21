# v49 validation

Validated locally:

- Python syntax compilation;
- immutable stop is written once for one position identifier;
- later balance changes cannot recalculate it;
- persisted immutable fields survive state reload;
- hard-stop reads do not call `account_info()` after locking;
- first post-fill pass may correct the provisional SL;
- a confirmed tighter SL is never weakened;
- missing broker SL restores the immutable price;
- Thursday TSL tightens above the immutable floor;
- BEPRE uses the market-SELL path;
- BEO uses the market-SELL path;
- BH uses the market-SELL path;
- the former crossed-TP protection-latch reason is absent from v49;
- existing v48 lease recovery and break-even scheduling tests remain green;
- active root, Demo and Real runtime sources are byte-identical.

Twenty automated regression tests passed.

Not performed here:

- live broker BUY or SELL submission;
- a real account-currency conversion change during a held position;
- production database lease traffic;
- broker execution/fill verification.
