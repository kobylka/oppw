<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/authority.php';

$assert = static function (bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
};

$assert(
    oppw_projection_exit_reason('TSL') === 'TSL_0.4%',
    'unqualified TSL did not retain the unified label'
);
$assert(
    oppw_projection_exit_reason('TSL1PRE') === 'TSL1PRE',
    'explicit TSL1PRE label was changed'
);
$assert(
    oppw_projection_exit_reason('BEPRE') === 'BEPRE',
    'non-TSL exit label was changed'
);

echo "AUTHORITY PROJECTION TESTS PASSED cases=3\n";
