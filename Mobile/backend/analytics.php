<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

require_method('GET');
$db = pdo();
$requested = trim((string)($_GET['account'] ?? ''));
$session = require_mobile_session($requested !== '' ? $requested : null);

$accountKey = $requested;
if ($accountKey === '') {
    $stmt = $db->prepare(
        'SELECT a.account_key FROM monitor_device_accounts da JOIN monitor_accounts a ON a.account_key=da.account_key
          WHERE da.device_id=? AND a.enabled=TRUE ORDER BY a.is_default DESC,a.sort_order,a.display_name LIMIT 1'
    );
    $stmt->execute([$session['device_id']]);
    $accountKey = (string)($stmt->fetchColumn() ?: '');
}
if ($accountKey === '') json_response(['ok' => false, 'error' => 'No permitted account configured'], 404);
$permission = $db->prepare(
    'SELECT a.account_key FROM monitor_device_accounts da JOIN monitor_accounts a ON a.account_key=da.account_key
      WHERE da.device_id=? AND a.account_key=? AND a.enabled=TRUE'
);
$permission->execute([$session['device_id'], $accountKey]);
if (!$permission->fetch()) json_response(['ok' => false, 'error' => 'Forbidden for selected account'], 403);

function f(mixed $value): float { return is_numeric($value) ? (float)$value : 0.0; }
function safe_div(float $a, float $b): float { return abs($b) > 1e-15 ? $a / $b : 0.0; }
function mean(array $values): float { return $values ? array_sum($values) / count($values) : 0.0; }
function median(array $values): float {
    if (!$values) return 0.0;
    sort($values, SORT_NUMERIC); $n=count($values); $m=intdiv($n,2);
    return $n%2 ? (float)$values[$m] : ((float)$values[$m-1]+(float)$values[$m])/2.0;
}
function sample_std(array $values): float {
    $n=count($values); if ($n < 2) return 0.0; $avg=mean($values); $sum=0.0;
    foreach ($values as $v) $sum += ((float)$v-$avg)**2;
    return sqrt($sum/($n-1));
}
function percentile(array $values, float $probability): float {
    if (!$values) return 0.0;
    sort($values, SORT_NUMERIC); $n=count($values); if ($n===1) return (float)$values[0];
    $position=max(0.0,min(1.0,$probability))*($n-1); $lower=(int)floor($position); $upper=(int)ceil($position);
    if ($lower===$upper) return (float)$values[$lower];
    $weight=$position-$lower; return (float)$values[$lower]*(1.0-$weight)+(float)$values[$upper]*$weight;
}
function annualized_sharpe(array $returns, int $periods=52): ?float {
    if (count($returns) < 2) return null;
    $sd=sample_std($returns); if ($sd <= 1e-15) return null;
    return mean($returns)/$sd*sqrt($periods);
}
function annualized_sortino(array $returns, int $periods=52): array {
    if (count($returns) < 2) return [null,false];
    $sum=0.0; foreach ($returns as $r) { $d=min(0.0,(float)$r); $sum += $d*$d; }
    $down=sqrt($sum/count($returns));
    if ($down <= 1e-15) return [null, mean($returns) > 0.0];
    return [mean($returns)/$down*sqrt($periods),false];
}
function trade_class(float $return, string $reason): string {
    if ($return >= 0.007) return 'A';
    if ($return >= 0.0) return 'B';
    $r=strtoupper(str_replace('-', '_', trim($reason)));
    if (str_starts_with($r,'TSL') || in_array($r,['BE','BH','BEO','BEPRE','BREAK_EVEN','BREAK_EVEN_EXIT'],true) || str_contains($r,'BREAK_EVEN')) return 'C';
    return 'D';
}
function longest_streak(array $profits, bool $wins): int {
    $best=0; $run=0; foreach ($profits as $p) { $ok=$wins ? $p>0 : $p<0; $run=$ok ? $run+1 : 0; $best=max($best,$run); } return $best;
}
function week_key(string $date): string {
    try { return (new DateTimeImmutable($date,new DateTimeZone('UTC')))->format('o-\\WW'); } catch (Throwable) { return ''; }
}

$tradeStmt=$db->prepare(
    'SELECT id,position_ticket,symbol,side,volume,opened_at,closed_at,open_price,close_price,profit,profit_percent,preleverage_return_percent,trade_class,exit_reason,
            balance_before,balance_after,mfe_points,mae_points,entry_slippage_points,exit_slippage_points,max_profit,max_drawdown
       FROM strategy_trades WHERE strategy_key=? ORDER BY opened_at,id'
);
$tradeStmt->execute([$accountKey]);
$rows=$tradeStmt->fetchAll();
$closed=[]; $open=[];
foreach ($rows as $row) {
    $isClosed=$row['closed_at']!==null && $row['close_price']!==null && f($row['open_price'])>0 && f($row['close_price'])>0;
    $calculatedPre=$isClosed ? f($row['close_price'])/f($row['open_price'])-1.0 : 0.0;
    $pre=$isClosed && is_numeric($row['preleverage_return_percent'] ?? null) ? f($row['preleverage_return_percent'])/100.0 : $calculatedPre;
    $profit=f($row['profit']);
    $balanceBefore=f($row['balance_before']);
    $accountReturn=$balanceBefore>0 ? $profit/$balanceBefore : (is_numeric($row['profit_percent']) ? f($row['profit_percent'])/100.0 : null);
    $opened=(string)$row['opened_at']; $closedAt=(string)($row['closed_at'] ?? '');
    $duration=0; if ($isClosed) { try { $duration=max(0,(new DateTimeImmutable($closedAt))->getTimestamp()-(new DateTimeImmutable($opened))->getTimestamp()); } catch(Throwable){} }
    $item=[
        'ticket'=>(int)$row['position_ticket'],'symbol'=>(string)$row['symbol'],'side'=>(string)$row['side'],'volume'=>f($row['volume']),
        'openedAt'=>$opened,'closedAt'=>$closedAt,'openPrice'=>f($row['open_price']),'closePrice'=>f($row['close_price']),
        'profit'=>$profit,'profitPercent'=>f($row['profit_percent']),'exitReason'=>(string)$row['exit_reason'],'durationSeconds'=>$duration,
        'mfePoints'=>f($row['mfe_points']),'maePoints'=>f($row['mae_points']),'entrySlippagePoints'=>f($row['entry_slippage_points']),
        'exitSlippagePoints'=>f($row['exit_slippage_points']),'maxProfit'=>f($row['max_profit']),'maxDrawdown'=>f($row['max_drawdown']),
        'balanceBefore'=>$balanceBefore,'balanceAfter'=>f($row['balance_after']),'closed'=>$isClosed,
        'accountReturn'=>$accountReturn,'accountReturnPercent'=>$accountReturn===null ? null : $accountReturn*100.0,
        'preleverageReturn'=>$pre,'preleverageReturnPercent'=>$pre*100.0,'tradeClass'=>$isClosed ? (in_array(strtoupper((string)($row['trade_class'] ?? '')),['A','B','C','D'],true) ? strtoupper((string)$row['trade_class']) : trade_class($pre,(string)$row['exit_reason'])) : '',
    ];
    if ($isClosed) $closed[]=$item; else $open[]=$item;
}

$profits=array_map(static fn(array $t):float=>(float)$t['profit'],$closed);
$accountReturns=[]; foreach($closed as $t) if ($t['accountReturn']!==null && is_finite((float)$t['accountReturn'])) $accountReturns[]=(float)$t['accountReturn'];
$wins=array_values(array_filter($closed,static fn(array $t):bool=>(float)$t['profit']>0));
$losses=array_values(array_filter($closed,static fn(array $t):bool=>(float)$t['profit']<0));
$grossProfit=array_sum(array_map(static fn(array $t):float=>max(0.0,(float)$t['profit']),$closed));
$grossLoss=array_sum(array_map(static fn(array $t):float=>min(0.0,(float)$t['profit']),$closed));
$sharpe=annualized_sharpe($accountReturns,52); [$sortino,$sortinoInfinite]=annualized_sortino($accountReturns,52);

$classStats=[]; foreach(['A','B','C','D'] as $class) $classStats[$class]=['class'=>$class,'trades'=>0,'profit'=>0.0,'averagePreleverageReturnPercent'=>0.0,'winRate'=>0.0];
$classReturns=['A'=>[],'B'=>[],'C'=>[],'D'=>[]]; $classWins=['A'=>0,'B'=>0,'C'=>0,'D'=>0];
foreach($closed as $t){$c=$t['tradeClass'];$classStats[$c]['trades']++;$classStats[$c]['profit']+=(float)$t['profit'];$classReturns[$c][]=(float)$t['preleverageReturnPercent'];if((float)$t['profit']>0)$classWins[$c]++;}
foreach(['A','B','C','D'] as $c){$classStats[$c]['averagePreleverageReturnPercent']=mean($classReturns[$c]);$classStats[$c]['winRate']=safe_div($classWins[$c]*100.0,$classStats[$c]['trades']);}

$distribution=$closed;
usort($distribution,static fn(array $a,array $b):int=>(float)$b['preleverageReturn']<=>(float)$a['preleverageReturn']);
$distribution=array_values(array_map(static function(array $t,int $i):array{return [
    'rank'=>$i+1,'ticket'=>$t['ticket'],'returnPercent'=>$t['preleverageReturnPercent'],'tradeClass'=>$t['tradeClass'],
    'exitReason'=>$t['exitReason'],'closedAt'=>$t['closedAt'],'profit'=>$t['profit'],
];},$distribution,array_keys($distribution)));
$meanPre=mean(array_map(static fn(array $t):float=>(float)$t['preleverageReturnPercent'],$closed));

$weeks=[]; foreach($closed as $t){$w=week_key($t['closedAt']);if($w==='')continue;if(!isset($weeks[$w]))$weeks[$w]=['week'=>$w,'trades'=>0,'wins'=>0,'profit'=>0.0,'bestTrade'=>-INF,'worstTrade'=>INF,'durations'=>[]];$weeks[$w]['trades']++;$weeks[$w]['wins']+=(float)$t['profit']>0?1:0;$weeks[$w]['profit']+=(float)$t['profit'];$weeks[$w]['bestTrade']=max($weeks[$w]['bestTrade'],(float)$t['profit']);$weeks[$w]['worstTrade']=min($weeks[$w]['worstTrade'],(float)$t['profit']);$weeks[$w]['durations'][]=(float)$t['durationSeconds'];}
$weekly=[]; foreach($weeks as $w){$weekly[]=['week'=>$w['week'],'trades'=>$w['trades'],'winRate'=>safe_div($w['wins']*100.0,$w['trades']),'profit'=>$w['profit'],'bestTrade'=>is_finite($w['bestTrade'])?$w['bestTrade']:0.0,'worstTrade'=>is_finite($w['worstTrade'])?$w['worstTrade']:0.0,'averageDurationSeconds'=>mean($w['durations'])];} usort($weekly,static fn(array $a,array $b):int=>strcmp($b['week'],$a['week']));

$reasons=[]; foreach($closed as $t){$r=$t['exitReason']?:'UNKNOWN';if(!isset($reasons[$r]))$reasons[$r]=['reason'=>$r,'trades'=>0,'wins'=>0,'profit'=>0.0,'mfe'=>[],'mae'=>[]];$reasons[$r]['trades']++;$reasons[$r]['wins']+=(float)$t['profit']>0?1:0;$reasons[$r]['profit']+=(float)$t['profit'];$reasons[$r]['mfe'][]=(float)$t['mfePoints'];$reasons[$r]['mae'][]=(float)$t['maePoints'];}
$exitReasons=[]; foreach($reasons as $r)$exitReasons[]=['reason'=>$r['reason'],'trades'=>$r['trades'],'winRate'=>safe_div($r['wins']*100.0,$r['trades']),'profit'=>$r['profit'],'averageProfit'=>safe_div($r['profit'],$r['trades']),'averageMfePoints'=>mean($r['mfe']),'averageMaePoints'=>mean($r['mae'])]; usort($exitReasons,static fn(array $a,array $b):int=>$b['trades']<=>$a['trades']);

$cash=$db->prepare('SELECT flow_type,amount,balance_after,occurred_at FROM account_cash_flows WHERE strategy_key=? ORDER BY occurred_at,id');
$cash->execute([$accountKey]); $cashRows=$cash->fetchAll();
$initial=0.0; $topUps=0.0; $withdrawals=0.0; $cashByDay=[];
foreach($cashRows as $row){
    $type=strtoupper((string)$row['flow_type']); $amount=f($row['amount']); $day=substr((string)$row['occurred_at'],0,10);
    if($type==='INITIAL'&&$initial===0.0){$initial=abs($amount);continue;}
    if($type==='TOP_UP'){$value=abs($amount);$topUps+=$value;$cashByDay[$day]=($cashByDay[$day]??0.0)+$value;}
    elseif($type==='WITHDRAWAL'){$value=abs($amount);$withdrawals+=$value;$cashByDay[$day]=($cashByDay[$day]??0.0)-$value;}
}
if($initial===0.0&&$closed)$initial=(float)$closed[0]['balanceBefore'];
$netContributions=$initial+$topUps-$withdrawals;

$equityStmt=$db->prepare('SELECT captured_minute,equity FROM strategy_equity_points WHERE strategy_key=? ORDER BY captured_minute');
$equityStmt->execute([$accountKey]); $equityRows=$equityStmt->fetchAll();
$daily=[]; foreach($equityRows as $row){$day=substr((string)$row['captured_minute'],0,10);$daily[$day]=['day'=>$day,'equity'=>f($row['equity'])];}
$daily=array_values($daily); usort($daily,static fn(array $a,array $b):int=>strcmp($a['day'],$b['day']));
$dailyReturns=[]; $adjustedCurve=[]; $adjustedIndex=1.0;
for($i=0;$i<count($daily);$i++){
    if($i>0){$previous=(float)$daily[$i-1]['equity'];$flow=(float)($cashByDay[$daily[$i]['day']]??0.0);$return=$previous>0?(((float)$daily[$i]['equity']-$flow)/$previous-1.0):0.0;if(is_finite($return)){$dailyReturns[]=$return;$adjustedIndex*=max(0.0000001,1.0+$return);}}
    $adjustedCurve[]=$adjustedIndex;
}
$peakIndex=0.0;$maxDrawdownPercent=0.0;$ulcerSquares=[];foreach($adjustedCurve as $value){$peakIndex=max($peakIndex,(float)$value);if($peakIndex>0){$dd=((float)$value/$peakIndex-1.0)*100.0;$maxDrawdownPercent=min($maxDrawdownPercent,$dd);$ulcerSquares[]=$dd*$dd;}}
$ulcerIndex=$ulcerSquares?sqrt(mean($ulcerSquares)):0.0;
$peakEquity=null;$maxDrawdown=0.0;foreach($equityRows as $row){$e=f($row['equity']);if($peakEquity===null||$e>$peakEquity)$peakEquity=$e;if($peakEquity>0)$maxDrawdown=min($maxDrawdown,$e-$peakEquity);}
$annualizedReturnPercent=0.0;if(count($daily)>=2&&$adjustedIndex>0){$startDate=new DateTimeImmutable($daily[0]['day'],new DateTimeZone('UTC'));$endDate=new DateTimeImmutable($daily[count($daily)-1]['day'],new DateTimeZone('UTC'));$days=max(1,$endDate->diff($startDate)->days);$annualizedReturnPercent=(pow($adjustedIndex,365.25/$days)-1.0)*100.0;}
$calmarRatio=abs($maxDrawdownPercent)>1e-12?$annualizedReturnPercent/abs($maxDrawdownPercent):0.0;
$positiveDaily=array_values(array_filter($dailyReturns,static fn(float $v):bool=>$v>0));$negativeDaily=array_values(array_filter($dailyReturns,static fn(float $v):bool=>$v<0));
$omegaRatio=abs(array_sum($negativeDaily))>1e-15?array_sum($positiveDaily)/abs(array_sum($negativeDaily)):($positiveDaily?999.999:0.0);
$var95=$dailyReturns?percentile($dailyReturns,0.05)*100.0:0.0;$tail=array_values(array_filter($dailyReturns,static fn(float $v):bool=>$v<=($var95/100.0+1e-15)));$expectedShortfall95=$tail?mean($tail)*100.0:$var95;

$durations=array_map(static fn(array $t):float=>(float)$t['durationSeconds'],$closed);$mfe=array_map(static fn(array $t):float=>(float)$t['mfePoints'],$closed);$mae=array_map(static fn(array $t):float=>(float)$t['maePoints'],$closed);$entrySlip=array_map(static fn(array $t):float=>(float)$t['entrySlippagePoints'],$closed);$exitSlip=array_map(static fn(array $t):float=>(float)$t['exitSlippagePoints'],$closed);
$positiveWeeks=count(array_filter($weekly,static fn(array $w):bool=>(float)$w['profit']>0));$netProfit=array_sum($profits);$avgMfe=mean($mfe);$avgMae=mean($mae);
$captureValues=[];foreach($closed as $trade){$maximum=(float)$trade['maxProfit'];if($maximum>1e-12)$captureValues[]=max(-1.0,min(1.0,(float)$trade['profit']/$maximum))*100.0;}$captureEfficiency=mean($captureValues);
$timeInMarket=0.0;if($closed){try{$first=new DateTimeImmutable((string)$closed[0]['openedAt'],new DateTimeZone('UTC'));$lastText=(string)$closed[count($closed)-1]['closedAt'];$last=new DateTimeImmutable($lastText,new DateTimeZone('UTC'));$span=max(1,$last->getTimestamp()-$first->getTimestamp());$timeInMarket=min(100.0,array_sum($durations)/$span*100.0);}catch(Throwable){}}
$summary=[
    'totalTrades'=>count($rows),'closedTrades'=>count($closed),'openTrades'=>count($open),'wins'=>count($wins),'losses'=>count($losses),
    'winRate'=>safe_div(count($wins)*100.0,count($closed)),'netProfit'=>$netProfit,'initialBalance'=>$initial,'topUps'=>$topUps,'withdrawals'=>$withdrawals,
    'netContributions'=>$netContributions,'capitalAdjustedReturnPercent'=>safe_div($netProfit*100.0,$netContributions),'positiveWeeksPercent'=>safe_div($positiveWeeks*100.0,count($weekly)),
    'averageWeeklyProfit'=>mean(array_map(static fn(array $w):float=>(float)$w['profit'],$weekly)),'totalSlippagePoints'=>array_sum($entrySlip)+array_sum($exitSlip),
    'grossProfit'=>$grossProfit,'grossLoss'=>$grossLoss,'profitFactor'=>abs($grossLoss)>1e-15?$grossProfit/abs($grossLoss):($grossProfit>0?999.999:0.0),
    'expectancy'=>mean($profits),'medianProfit'=>median($profits),'averageWin'=>mean(array_map(static fn(array $t):float=>(float)$t['profit'],$wins)),
    'averageLoss'=>mean(array_map(static fn(array $t):float=>(float)$t['profit'],$losses)),'payoffRatio'=>safe_div(mean(array_map(static fn(array $t):float=>(float)$t['profit'],$wins)),abs(mean(array_map(static fn(array $t):float=>(float)$t['profit'],$losses)))),
    'averageDurationSeconds'=>mean($durations),'averageMfePoints'=>$avgMfe,'averageMaePoints'=>$avgMae,'averageEntrySlippagePoints'=>mean($entrySlip),'averageExitSlippagePoints'=>mean($exitSlip),
    'captureEfficiencyPercent'=>$captureEfficiency,'edgeRatio'=>safe_div($avgMfe,abs($avgMae)),'maxDrawdown'=>$maxDrawdown,'recoveryFactor'=>safe_div($netProfit,abs($maxDrawdown)),
    'consistencyScore'=>safe_div($positiveWeeks*100.0,count($weekly)),'maxWinStreak'=>longest_streak($profits,true),'maxLossStreak'=>longest_streak($profits,false),
    'timeInMarketPercent'=>$timeInMarket,'bestTrade'=>$profits?max($profits):0.0,'worstTrade'=>$profits?min($profits):0.0,
    'sharpeRatio'=>$sharpe,'sharpeAvailable'=>$sharpe!==null,'sortinoRatio'=>$sortino,'sortinoAvailable'=>$sortino!==null||$sortinoInfinite,'sortinoInfinite'=>$sortinoInfinite,'ratiosAnnualized'=>true,'periodsPerYear'=>52,'ratioSampleTrades'=>count($accountReturns),
    'calmarRatio'=>$calmarRatio,'omegaRatio'=>$omegaRatio,'ulcerIndexPercent'=>$ulcerIndex,'valueAtRisk95Percent'=>$var95,'expectedShortfall95Percent'=>$expectedShortfall95,'riskSampleDays'=>count($dailyReturns),
];

$recent=array_reverse($closed);$recent=array_slice($recent,0,100);
json_response([
    'ok'=>true,'generatedAt'=>atom_datetime(utc_now()),'summary'=>$summary,'exitReasons'=>$exitReasons,'weekly'=>$weekly,'recentTrades'=>$recent,
    'tradeClasses'=>array_values($classStats),'tradeDistribution'=>['sortOrder'=>'BEST_TO_WORST','meanReturnPercent'=>$meanPre,'trades'=>$distribution],
    'methodology'=>[
        'sharpe'=>'Closed-trade account returns, annualized with sqrt(52), sample standard deviation.',
        'sortino'=>'Closed-trade account returns, annualized with sqrt(52), zero target; infinity is flagged when there are no downside returns.',
        'tradeClass'=>'A if pre-leverage return >=0.7%; otherwise B if >=0%; otherwise C for BE/TSL exits; otherwise D.',
    ],
]);
