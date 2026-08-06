<?php
declare(strict_types=1);

const OPPW_ANALYTICS_WINDOW_TIME_ZONE = 'Europe/Warsaw';

function oppw_analytics_window_end_date(mixed $value): string
{
    $raw = trim((string)$value);
    if ($raw === '') return '';

    $zone = new DateTimeZone(OPPW_ANALYTICS_WINDOW_TIME_ZONE);
    $parsed = DateTimeImmutable::createFromFormat('!Y-m-d', $raw, $zone);
    $errors = DateTimeImmutable::getLastErrors();
    if ($parsed === false
        || ($errors !== false && ($errors['warning_count'] > 0 || $errors['error_count'] > 0))
        || $parsed->format('Y-m-d') !== $raw) {
        throw new InvalidArgumentException('window_end_date must use YYYY-MM-DD');
    }
    return $raw;
}

function oppw_analytics_warsaw_date(DateTimeImmutable $value): string
{
    return $value
        ->setTimezone(new DateTimeZone(OPPW_ANALYTICS_WINDOW_TIME_ZONE))
        ->format('Y-m-d');
}

/**
 * Resolve one fixed-duration analytics window. An empty end date anchors the
 * window to the latest stored observation. A supplied date is the inclusive
 * final Europe/Warsaw calendar date, so the SQL-exclusive boundary is the
 * following local midnight.
 *
 * @return array{
 *   availableWeeks:int,
 *   effectiveRollingWeeks:int,
 *   windowStartUtc:?DateTimeImmutable,
 *   windowEndUtc:?DateTimeImmutable,
 *   availableStartDate:string,
 *   availableEndDate:string
 * }
 */
function oppw_analytics_window_bounds(
    ?DateTimeImmutable $firstActivityUtc,
    ?DateTimeImmutable $latestActivityUtc,
    int $requestedRollingWeeks,
    bool $allHistory,
    string $windowEndDate = ''
): array {
    $empty = [
        'availableWeeks' => 0,
        'effectiveRollingWeeks' => 0,
        'windowStartUtc' => null,
        'windowEndUtc' => null,
        'availableStartDate' => '',
        'availableEndDate' => '',
    ];
    if ($firstActivityUtc === null || $latestActivityUtc === null) return $empty;
    if ($requestedRollingWeeks < 1) {
        throw new InvalidArgumentException('rolling weeks must be positive');
    }

    $utc = new DateTimeZone('UTC');
    $firstActivityUtc = $firstActivityUtc->setTimezone($utc);
    $latestActivityUtc = $latestActivityUtc->setTimezone($utc);
    if ($latestActivityUtc < $firstActivityUtc) {
        throw new InvalidArgumentException('latest analytics activity precedes first activity');
    }

    // MySQL timestamps have millisecond precision; this exclusive boundary
    // includes the latest stored observation.
    $latestEndUtc = $latestActivityUtc->modify('+1 millisecond');
    $weekSeconds = 7 * 24 * 60 * 60;
    $availableWeeks = max(1, (int)ceil(
        (((float)$latestEndUtc->format('U.u')) - ((float)$firstActivityUtc->format('U.u'))) / $weekSeconds
    ));
    $availableStartDate = oppw_analytics_warsaw_date($firstActivityUtc);
    $availableEndDate = oppw_analytics_warsaw_date($latestActivityUtc);

    if ($allHistory) {
        return [
            'availableWeeks' => $availableWeeks,
            'effectiveRollingWeeks' => $availableWeeks,
            'windowStartUtc' => $firstActivityUtc,
            'windowEndUtc' => $latestEndUtc,
            'availableStartDate' => $availableStartDate,
            'availableEndDate' => $availableEndDate,
        ];
    }

    $windowEndUtc = $latestEndUtc;
    if ($windowEndDate !== '') {
        if ($windowEndDate < $availableStartDate || $windowEndDate > $availableEndDate) {
            throw new OutOfRangeException('window_end_date is outside available analytics history');
        }
        $windowEndUtc = (new DateTimeImmutable(
            $windowEndDate,
            new DateTimeZone(OPPW_ANALYTICS_WINDOW_TIME_ZONE)
        ))->modify('+1 day')->setTimezone($utc);
        if ($windowEndUtc > $latestEndUtc) $windowEndUtc = $latestEndUtc;
    }

    $weeksBeforeEnd = max(1, (int)ceil(
        (((float)$windowEndUtc->format('U.u')) - ((float)$firstActivityUtc->format('U.u'))) / $weekSeconds
    ));
    $effectiveRollingWeeks = min($requestedRollingWeeks, $weeksBeforeEnd);
    $windowStartUtc = $windowEndUtc->modify('-' . $effectiveRollingWeeks . ' weeks');
    if ($windowStartUtc < $firstActivityUtc) $windowStartUtc = $firstActivityUtc;

    return [
        'availableWeeks' => $availableWeeks,
        'effectiveRollingWeeks' => $effectiveRollingWeeks,
        'windowStartUtc' => $windowStartUtc,
        'windowEndUtc' => $windowEndUtc,
        'availableStartDate' => $availableStartDate,
        'availableEndDate' => $availableEndDate,
    ];
}
