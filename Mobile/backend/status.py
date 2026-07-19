#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

CANONICAL_REQUIRE = "require_once __DIR__ . '/oppw_latest_trade.php';"
OBSOLETE_REQUIRES = (
    "require_once __DIR__ . '/last-trade-authority.php';",
    "require_once __DIR__ . '/latest-trade.php';",
)
BLOCK = r'''// v45.3.1: last-trade enrichment is optional and must never break status JSON.
$oppwTradeBufferLevel = ob_get_level();
ob_start();
try {
    $authoritativeLastTrade = oppw_authoritative_last_trade($db, $accountKey);
    if ($authoritativeLastTrade !== null) $snapshot['lastClosedTrade'] = $authoritativeLastTrade;
} catch (Throwable $oppwTradeError) {
    error_log('OPPW status last-trade enrichment failed: ' . $oppwTradeError->getMessage());
} finally {
    while (ob_get_level() > $oppwTradeBufferLevel) ob_end_clean();
}

'''


def patch(path: Path) -> None:
    text = path.read_text(encoding='utf-8')
    backup = path.with_suffix(path.suffix + '.v45.3.1.bak')
    if not backup.exists(): shutil.copy2(path, backup)

    for old in OBSOLETE_REQUIRES:
        text = text.replace(old, CANONICAL_REQUIRE)

    if CANONICAL_REQUIRE not in text:
        markers = ("require __DIR__ . '/lib.php';", "require_once __DIR__ . '/lib.php';")
        marker = next((candidate for candidate in markers if candidate in text), None)
        if marker is None: raise RuntimeError(f'Could not find lib.php require in {path}')
        text = text.replace(marker, marker + '\n' + CANONICAL_REQUIRE, 1)

    # Keep exactly one canonical include.
    lines = text.splitlines()
    result: list[str] = []
    seen = False
    for line in lines:
        if line.strip() == CANONICAL_REQUIRE:
            if seen: continue
            seen = True
        result.append(line)
    text = '\n'.join(result) + ('\n' if text.endswith('\n') else '')

    # Remove all earlier v45.2/v45.3 enrichment implementations.
    patterns = (
        r"// v45\.2:.*?\n\$authoritativeLastTrade\s*=\s*oppw_authoritative_last_trade\(\$db,\s*\$accountKey\);\s*\nif \(\$authoritativeLastTrade !== null\) \$snapshot\['lastClosedTrade'\] = \$authoritativeLastTrade;\s*\n",
        r"// v45\.3:.*?\n\$authoritativeLastTrade\s*=\s*oppw_authoritative_last_trade\(\$db,\s*\$accountKey\);\s*\nif \(\$authoritativeLastTrade !== null\) \$snapshot\['lastClosedTrade'\] = \$authoritativeLastTrade;\s*\n",
        r"\$authoritativeLastTrade\s*=\s*oppw_authoritative_last_trade\(\$db,\s*\$accountKey\);\s*\nif \(\$authoritativeLastTrade !== null\) \$snapshot\['lastClosedTrade'\] = \$authoritativeLastTrade;\s*\n",
        r"// v45\.3\.1: last-trade enrichment.*?while \(ob_get_level\(\) > \$oppwTradeBufferLevel\) ob_end_clean\(\);\s*\n}\s*\n",
    )
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL)

    marker = '$serverNowUtc = utc_now();'
    if marker not in text: raise RuntimeError(f'Could not find status insertion marker in {path}')
    text = text.replace(marker, BLOCK + marker, 1)

    path.write_text(text, encoding='utf-8')
    print(f'Patched {path}')


def main() -> int:
    if len(sys.argv) != 2:
        print(r'Usage: py patch_status_v45_3_1.py D:\oppw\Mobile\backend\status.php', file=sys.stderr)
        return 2
    path = Path(sys.argv[1]).resolve()
    if not path.is_file(): raise FileNotFoundError(path)
    patch(path)
    return 0


if __name__ == '__main__': raise SystemExit(main())