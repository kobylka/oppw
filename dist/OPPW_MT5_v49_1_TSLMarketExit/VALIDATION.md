# v49.1 validation

- Python compilation passed.
- A live bid exactly at the normalized TSL enters the market-SELL path.
- The crossed TSL never calls `arm_exit()` first.
- V49 immutable hard-stop tests remain green.
- V48 database lease recovery tests remain green.
- Twenty-one automated tests passed.
- Root, Demo and Real active runtime files are byte-identical.

Live MT5 order submission was not performed in this environment.
