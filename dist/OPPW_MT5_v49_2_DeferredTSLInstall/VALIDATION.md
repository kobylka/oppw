# v49.2 validation

- bid at/below TSL sends market SELL;
- bid above TSL but inside broker distance preserves the hard SL;
- deferred TSL sends no SL/TP request and no exit bracket;
- deferred TSL installs when bid later creates sufficient distance;
- already installed TSL is accepted inside the freeze distance;
- identical active SL is not revalidated, clamped or weakened;
- immutable v49 hard-stop tests remain green;
- database lease recovery tests remain green;
- Python compilation passed;
- twenty-five automated tests passed.

Live MT5 order submission was not performed in this environment.
