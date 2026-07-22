<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('GET');
$db = pdo();
$requested = trim((string)($_GET['account'] ?? ''));
$session = require_mobile_session($requested !== '' ? $requested : null);

function n(mixed $value): float { return is_numeric($value) ? (float)$value : 0.0; }
function avg_values(array $values): float { return $values ? array_sum($values)/count($values) : 0.0; }
function sample_std_values(array $values): float { $count=count($values); if($count<2)return 0.0; $mean=avg_values($values); $sum=0.0; foreach($values as $value)$sum+=(floatval($value)-$mean)**2; return sqrt($sum/($count-1)); }
function percentile_values(array $values,float $percentile): ?float { if(!$values)return null; sort($values,SORT_NUMERIC); $index=($percentile/100.0)*(count($values)-1); $lower=(int)floor($index); $upper=(int)ceil($index); if($lower===$upper)return (float)$values[$lower]; $weight=$index-$lower; return (float)$values[$lower]*(1-$weight)+(float)$values[$upper]*$weight; }
function annualized_sharpe(array $returns,int $periods=52): ?float { if(count($returns)<2)return null; $sd=sample_std_values($returns); return $sd>1e-15?avg_values($returns)/$sd*sqrt($periods):null; }
function annualized_sortino(array $returns,int $periods=52): array { if(count($returns)<2)return [null,false]; $sum=0.0; foreach($returns as $return){$down=min(0.0,(float)$return);$sum+=$down*$down;} $deviation=sqrt($sum/count($returns)); if($deviation<=1e-15)return [null,avg_values($returns)>0]; return [avg_values($returns)/$deviation*sqrt($periods),false]; }
function compounded_return_percent(array $returns): float { $index=1.0; foreach($returns as $return)$index*=1.0+(float)$return; return ($index-1.0)*100.0; }
function wilson_interval(int $wins,int $count,float $z=1.96): array { if($count<=0)return [0.0,0.0]; $p=$wins/$count; $den=1+$z*$z/$count; $centre=($p+$z*$z/(2*$count))/$den; $margin=$z*sqrt(($p*(1-$p)+$z*$z/(4*$count))/$count)/$den; return [max(0.0,$centre-$margin)*100,min(1.0,$centre+$margin)*100]; }
function mean_interval(array $values,float $z=1.96): array { $count=count($values); if($count===0)return [0.0,0.0]; $mean=avg_values($values); if($count<2)return [$mean,$mean]; $margin=$z*sample_std_values($values)/sqrt($count); return [$mean-$margin,$mean+$margin]; }
function iso_value(?string $value): string { if(!$value)return ''; try{return (new DateTimeImmutable($value,new DateTimeZone('UTC')))->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\\TH:i:s.u\\Z');}catch(Throwable){return $value;} }
function trade_key(array $trade): string { return (string)$trade['strategyKey'].':'.(string)$trade['ticket']; }
function metric_sample(array $trades): array { return array_values(array_map('trade_key',$trades)); }
function duration_seconds(array $trade): int { if(!$trade['openedAt']||!$trade['closedAt'])return 0; try{return max(0,(new DateTimeImmutable($trade['closedAt']))->getTimestamp()-(new DateTimeImmutable($trade['openedAt']))->getTimestamp());}catch(Throwable){return 0;} }
function stage_millis(string $value): ?float { if($value==='')return null; try{$dt=new DateTimeImmutable($value);return ((float)$dt->format('U')*1000.0)+((float)$dt->format('u')/1000.0);}catch(Throwable){return null;} }
function longest_streak(array $profits,bool $wins): int { $best=0;$run=0;foreach($profits as $profit){$match=$wins?(float)$profit>0:(float)$profit<0;$run=$match?$run+1:0;$best=max($best,$run);}return $best; }
function longest_streak_trades(array $trades,bool $wins): array { $best=[];$run=[];foreach($trades as $trade){$match=$wins?(float)$trade['profit']>0:(float)$trade['profit']<0;if($match){$run[]=$trade;if(count($run)>count($best))$best=$run;}else{$run=[];}}return $best; }
function trade_class_v13(float $returnPercent,string $reason): string { if($returnPercent>=0.7)return 'A';if($returnPercent>=0.0)return 'B';$normalized=strtoupper(str_replace('-','_',trim($reason)));if(str_starts_with($normalized,'TSL')||in_array($normalized,['BE','BH','BEO','BEPRE','BREAK_EVEN','BREAK_EVEN_EXIT'],true)||str_contains($normalized,'BREAK_EVEN'))return 'C';return 'D'; }
function warsaw_day(string $value): string { try{return (new DateTimeImmutable($value,new DateTimeZone('UTC')))->setTimezone(new DateTimeZone('Europe/Warsaw'))->format('Y-m-d');}catch(Throwable){return substr($value,0,10);} }
function warsaw_week_start(string $value): ?DateTimeImmutable { try{$local=(new DateTimeImmutable($value,new DateTimeZone('UTC')))->setTimezone(new DateTimeZone('Europe/Warsaw'))->setTime(0,0,0,0);return $local->modify('monday this week');}catch(Throwable){return null;} }

$allowedStmt=$db->prepare('SELECT a.account_key,a.display_name,a.account_type FROM monitor_device_accounts da JOIN monitor_accounts a ON a.account_key=da.account_key WHERE da.device_id=? AND a.enabled=TRUE ORDER BY a.is_default DESC,a.sort_order,a.display_name');
$allowedStmt->execute([$session['device_id']]);
$allowed=$allowedStmt->fetchAll();
if(!$allowed)json_response(['ok'=>false,'error'=>'No permitted account configured'],404);
$allowedByKey=[]; foreach($allowed as $row)$allowedByKey[(string)$row['account_key']]=$row;
$scope=strtoupper(trim((string)($_GET['scope']??'SELECTED')));
if(!in_array($scope,['SELECTED','ALL','REAL','DEMO'],true))$scope='SELECTED';
if($requested===''||!isset($allowedByKey[$requested]))$requested=(string)$allowed[0]['account_key'];
$accountKeys=[];
if($scope==='SELECTED')$accountKeys=[$requested];
elseif($scope==='ALL')$accountKeys=array_keys($allowedByKey);
else foreach($allowed as $row)if(strtoupper((string)$row['account_type'])===$scope)$accountKeys[]=(string)$row['account_key'];
if(!$accountKeys)json_response(['ok'=>false,'error'=>'No permitted account matches selected scope'],404);

$placeholders=implode(',',array_fill(0,count($accountKeys),'?'));
$optionSql="SELECT entry_leverage,exit_reason,COALESCE(closed_at,opened_at) AS activity_at FROM strategy_trades WHERE strategy_key IN ($placeholders)";
$optionStmt=$db->prepare($optionSql);$optionStmt->execute($accountKeys);$optionRows=$optionStmt->fetchAll();
$weekStarts=[];foreach($optionRows as $row){$week=warsaw_week_start((string)($row['activity_at']??''));if($week!==null)$weekStarts[$week->format('Y-m-d')]=$week;}ksort($weekStarts);
$firstWeek=$weekStarts?reset($weekStarts):null;$latestWeek=$weekStarts?end($weekStarts):null;$availableWeeks=0;
if($firstWeek instanceof DateTimeImmutable&&$latestWeek instanceof DateTimeImmutable){$firstDate=new DateTimeImmutable($firstWeek->format('Y-m-d'),new DateTimeZone('UTC'));$latestDate=new DateTimeImmutable($latestWeek->format('Y-m-d'),new DateTimeZone('UTC'));$availableWeeks=max(1,intdiv((int)$firstDate->diff($latestDate)->days,7)+1);}
$requestedRollingWeeks=filter_var($_GET['rolling_weeks']??4,FILTER_VALIDATE_INT,['options'=>['min_range'=>1,'max_range'=>520]]);if($requestedRollingWeeks===false)$requestedRollingWeeks=4;
$effectiveRollingWeeks=$availableWeeks>0?min((int)$requestedRollingWeeks,$availableWeeks):0;$windowStartUtc=null;$windowEndUtc=null;
if($latestWeek instanceof DateTimeImmutable&&$effectiveRollingWeeks>0){$windowStartUtc=$latestWeek->modify('-'.($effectiveRollingWeeks-1).' weeks')->setTimezone(new DateTimeZone('UTC'));$windowEndUtc=$latestWeek->modify('+1 week')->setTimezone(new DateTimeZone('UTC'));}
$activeOptionRows=$optionRows;if($windowStartUtc!==null&&$windowEndUtc!==null){$startTs=$windowStartUtc->getTimestamp();$endTs=$windowEndUtc->getTimestamp();$activeOptionRows=array_values(array_filter($optionRows,function(array $row)use($startTs,$endTs):bool{try{$ts=(new DateTimeImmutable((string)($row['activity_at']??''),new DateTimeZone('UTC')))->getTimestamp();return $ts>=$startTs&&$ts<$endTs;}catch(Throwable){return false;}}));}
$baseSql="SELECT t.*,a.account_type FROM strategy_trades t JOIN monitor_accounts a ON a.account_key=t.strategy_key WHERE t.strategy_key IN ($placeholders)";
$params=$accountKeys;
$leverage=trim((string)($_GET['leverage']??''));
$exitReason=trim((string)($_GET['exit_reason']??''));
$class=strtoupper(trim((string)($_GET['class']??'')));
if($windowStartUtc!==null&&$windowEndUtc!==null){$baseSql.=' AND COALESCE(t.closed_at,t.opened_at)>=? AND COALESCE(t.closed_at,t.opened_at)<?';$params[]=mysql_datetime($windowStartUtc);$params[]=mysql_datetime($windowEndUtc);}
if($leverage!==''&&is_numeric($leverage)){ $baseSql.=' AND ROUND(COALESCE(t.entry_leverage,0),3)=?'; $params[]=(float)$leverage; }
if($exitReason!==''){ $baseSql.=' AND t.exit_reason=?'; $params[]=$exitReason; }
if(in_array($class,['A','B','C','D'],true)){ $baseSql.=' AND t.trade_class=?'; $params[]=$class; }
$baseSql.=' ORDER BY COALESCE(t.closed_at,t.opened_at),t.id';
$tradeStmt=$db->prepare($baseSql); $tradeStmt->execute($params); $rows=$tradeStmt->fetchAll();
$trades=[];
foreach($rows as $row){
    $balanceBefore=n($row['balance_before']??0);$profit=n($row['profit']??0);$accountReturn=$balanceBefore!=0?$profit/$balanceBefore:(is_numeric($row['profit_percent']??null)?n($row['profit_percent'])/100.0:0.0);
    $isClosed=$row['closed_at']!==null&&n($row['open_price']??0)>0&&n($row['close_price']??0)>0;
    $prelev=n($row['preleverage_return_percent']??($isClosed?(n($row['close_price'])/n($row['open_price'])-1)*100:0));
    $exit=(string)($row['exit_reason']??'');$storedClass=strtoupper(trim((string)($row['trade_class']??'')));$tradeClass=$isClosed?(in_array($storedClass,['A','B','C','D'],true)?$storedClass:trade_class_v13($prelev,$exit)):'';
    $openedAt=iso_value((string)$row['opened_at']);$closedAt=iso_value($isClosed?(string)$row['closed_at']:null);$duration=0;if($isClosed){try{$duration=max(0,(new DateTimeImmutable($closedAt))->getTimestamp()-(new DateTimeImmutable($openedAt))->getTimestamp());}catch(Throwable){}}
    $trades[]=[
        'strategyKey'=>(string)$row['strategy_key'],'accountType'=>(string)$row['account_type'],'ticket'=>(int)$row['position_ticket'],'decisionId'=>(string)($row['decision_id']??''),
        'strategyBuild'=>(string)($row['strategy_build']??''),'parameterHash'=>(string)($row['parameter_hash']??''),'entryLeverage'=>n($row['entry_leverage']??0),
        'symbol'=>(string)$row['symbol'],'side'=>(string)$row['side'],'volume'=>n($row['volume']),'openedAt'=>$openedAt,'closedAt'=>$closedAt,'openPrice'=>n($row['open_price']),'closePrice'=>n($row['close_price']),
        'profit'=>$profit,'profitPercent'=>n($row['profit_percent']),'balanceBefore'=>$balanceBefore,'balanceAfter'=>n($row['balance_after']??0),'tradeReturn'=>$accountReturn,
        'preleverageReturnPercent'=>$prelev,'tradeClass'=>$tradeClass,'exitReason'=>$exit,'durationSeconds'=>$duration,
        'mfePoints'=>n($row['mfe_points']),'mfePercent'=>n($row['mfe_percent']),'maePoints'=>n($row['mae_points']),'maePercent'=>n($row['mae_percent']),
        'entrySlippagePoints'=>n($row['entry_slippage_points']),'exitSlippagePoints'=>n($row['exit_slippage_points']),
        'maxProfit'=>n($row['max_profit']),'maxDrawdown'=>n($row['max_drawdown']),'closed'=>$isClosed,
    ];
}
$closed=array_values(array_filter($trades,fn($trade)=>$trade['closed'])); $open=array_values(array_filter($trades,fn($trade)=>!$trade['closed']));
$wins=array_values(array_filter($closed,fn($trade)=>$trade['profit']>0)); $losses=array_values(array_filter($closed,fn($trade)=>$trade['profit']<0));
$returns=array_map(fn($trade)=>(float)$trade['tradeReturn'],$closed); $profits=array_map(fn($trade)=>(float)$trade['profit'],$closed);
$grossProfit=array_sum(array_map(fn($trade)=>max(0.0,$trade['profit']),$closed));$grossLoss=array_sum(array_map(fn($trade)=>min(0.0,$trade['profit']),$closed));$grossLossAbs=abs($grossLoss);
$sharpe=annualized_sharpe($returns); [$sortino,$sortinoInfinite]=annualized_sortino($returns);
$allSample=metric_sample($closed); $winnerSample=metric_sample($wins); $loserSample=metric_sample($losses);
$bestTradeGroup=[];$worstTradeGroup=[];
if($closed){$bestTradeGroup=[array_reduce($closed,fn($best,$trade)=>$best===null||$trade['profit']>$best['profit']?$trade:$best)];$worstTradeGroup=[array_reduce($closed,fn($worst,$trade)=>$worst===null||$trade['profit']<$worst['profit']?$trade:$worst)];}
$winStreakSample=metric_sample(longest_streak_trades($closed,true));$lossStreakSample=metric_sample(longest_streak_trades($closed,false));
$metricSamples=[
    'totalTrades'=>array_values(array_map('trade_key',$trades)),'closedTrades'=>$allSample,'wins'=>$winnerSample,'losses'=>$loserSample,
    'netProfit'=>$allSample,'winRate'=>$allSample,'grossProfit'=>$winnerSample,'grossLoss'=>$loserSample,'profitFactor'=>$allSample,'expectancy'=>$allSample,
    'medianProfit'=>$allSample,'averageWin'=>$winnerSample,'averageLoss'=>$loserSample,'payoffRatio'=>$allSample,
    'averageDuration'=>$allSample,'averageMfe'=>$allSample,'averageMae'=>$allSample,'entrySlippage'=>$allSample,'exitSlippage'=>$allSample,'totalSlippage'=>$allSample,
    'captureEfficiency'=>$allSample,'edgeRatio'=>$allSample,'maxDrawdown'=>$allSample,'recoveryFactor'=>$allSample,'consistencyScore'=>$allSample,
    'maxWinStreak'=>$winStreakSample,'maxLossStreak'=>$lossStreakSample,'timeInMarket'=>$allSample,'bestTrade'=>metric_sample($bestTradeGroup),'worstTrade'=>metric_sample($worstTradeGroup),
    'sharpeRatio'=>$allSample,'sortinoRatio'=>$allSample,'calmarRatio'=>$allSample,'omegaRatio'=>$allSample,'ulcerIndex'=>$allSample,'valueAtRisk95'=>$allSample,'expectedShortfall95'=>$allSample,
    'capitalAdjustedReturn'=>$allSample,'positiveWeeks'=>$allSample,'averageWeeklyProfit'=>$allSample,
    'averageWeeklyPreleverageReturn'=>$allSample,'averageWeeklyLeveragedReturn'=>$allSample,
    'averageLossPreleverageReturn'=>$loserSample,'averageLossLeveragedReturn'=>$loserSample,
    'averageWinPreleverageReturn'=>$winnerSample,'averageWinLeveragedReturn'=>$winnerSample,'benchmark'=>$allSample,
];

$equity=100.0;$peak=100.0;$closedTradeMaxDrawdownPercent=0.0;$drawdownSeries=[];
foreach($closed as $index=>$trade){$equity*=1+(float)$trade['tradeReturn'];$peak=max($peak,$equity);$dd=$peak>0?($equity/$peak-1)*100:0;$closedTradeMaxDrawdownPercent=min($closedTradeMaxDrawdownPercent,$dd);$drawdownSeries[]=['index'=>$index+1,'tradeKey'=>trade_key($trade),'closedAt'=>$trade['closedAt'],'equityIndex'=>$equity,'drawdownPercent'=>$dd,'maePercent'=>$trade['maePercent']];}

$rolling=[];
for($i=0;$i<count($closed);$i++){
    $start=max(0,$i-19);$window=array_slice($closed,$start,$i-$start+1);$windowReturns=array_map(fn($trade)=>(float)$trade['tradeReturn'],$window);
    [$windowSortino,$windowInfinite]=annualized_sortino($windowReturns);
    $rolling[]=['endingTradeKey'=>trade_key($closed[$i]),'closedAt'=>$closed[$i]['closedAt'],'sampleCount'=>count($window),'sharpe'=>annualized_sharpe($windowReturns),'sortino'=>$windowSortino,'sortinoInfinite'=>$windowInfinite,'tradeKeys'=>metric_sample($window)];
}
[$meanLow,$meanHigh]=mean_interval(array_map(fn($value)=>$value*100,$returns)); [$winLow,$winHigh]=wilson_interval(count($wins),count($closed));
$confidence=[
    ['key'=>'meanReturn','label'=>'Mean account return','estimate'=>avg_values($returns)*100,'lower95'=>$meanLow,'upper95'=>$meanHigh,'unit'=>'%','sampleCount'=>count($closed),'tradeKeys'=>$allSample],
    ['key'=>'winRate','label'=>'Win rate','estimate'=>count($closed)?count($wins)/count($closed)*100:0,'lower95'=>$winLow,'upper95'=>$winHigh,'unit'=>'%','sampleCount'=>count($closed),'tradeKeys'=>$allSample],
];

$classGroups=[];$classProfitTotal=array_sum($profits);
foreach(['A','B','C','D'] as $className){$group=array_values(array_filter($closed,fn($trade)=>strtoupper($trade['tradeClass'])===$className));$profit=array_sum(array_column($group,'profit'));$classGroups[]=['tradeClass'=>$className,'trades'=>count($group),'profit'=>$profit,'profitContributionPercent'=>abs($classProfitTotal)>1e-12?$profit/$classProfitTotal*100:0,'cumulativeProfit'=>0.0,'averagePreleverageReturnPercent'=>avg_values(array_column($group,'preleverageReturnPercent')),'winRate'=>count($group)?count(array_filter($group,fn($trade)=>$trade['profit']>0))/count($group)*100:0,'tradeKeys'=>metric_sample($group)];$metricSamples['class'.$className]=metric_sample($group);}
$cumulative=0.0;foreach($classGroups as &$group){$cumulative+=$group['profit'];$group['cumulativeProfit']=$cumulative;}unset($group);
$classDistribution=[];
foreach($closed as $trade){$distributionKey=substr($trade['closedAt'],0,4).'|'.($trade['entryLeverage']?:0).'|'.$trade['tradeClass'];if(!isset($classDistribution[$distributionKey]))$classDistribution[$distributionKey]=['year'=>(int)substr($trade['closedAt'],0,4),'leverage'=>$trade['entryLeverage'],'tradeClass'=>$trade['tradeClass'],'trades'=>0,'profit'=>0.0,'tradeKeys'=>[]];$classDistribution[$distributionKey]['trades']++;$classDistribution[$distributionKey]['profit']+=$trade['profit'];$classDistribution[$distributionKey]['tradeKeys'][]=trade_key($trade);}
$classDistribution=array_values($classDistribution);

$exitReasons=[];$exitGroups=[];foreach($closed as $trade){$key=$trade['exitReason']?:'Unknown';$exitGroups[$key][]=$trade;}
foreach($exitGroups as $reason=>$group){$exitReasons[]=['reason'=>$reason,'trades'=>count($group),'winRate'=>count(array_filter($group,fn($trade)=>$trade['profit']>0))/count($group)*100,'profit'=>array_sum(array_column($group,'profit')),'averageProfit'=>avg_values(array_column($group,'profit')),'averageMfePoints'=>avg_values(array_column($group,'mfePoints')),'averageMaePoints'=>avg_values(array_column($group,'maePoints')),'tradeKeys'=>metric_sample($group)];$metricSamples['exit:'.$reason]=metric_sample($group);}
usort($exitReasons,fn($a,$b)=>$b['trades']<=>$a['trades']);

$weeklyGroups=[];foreach($closed as $trade){try{$week=(new DateTimeImmutable($trade['closedAt']))->format('o-\WW');}catch(Throwable){$week='Unknown';}$weeklyGroups[$week][]=$trade;}
$weekly=[];foreach($weeklyGroups as $week=>$group){$weekly[]=['week'=>$week,'trades'=>count($group),'winRate'=>count(array_filter($group,fn($trade)=>$trade['profit']>0))/count($group)*100,'profit'=>array_sum(array_column($group,'profit')),'bestTrade'=>max(array_column($group,'profit')),'worstTrade'=>min(array_column($group,'profit')),'averageDurationSeconds'=>avg_values(array_map('duration_seconds',$group)),'preleverageReturnPercent'=>compounded_return_percent(array_map(fn($trade)=>(float)$trade['preleverageReturnPercent']/100.0,$group)),'leveragedReturnPercent'=>compounded_return_percent(array_map(fn($trade)=>(float)$trade['tradeReturn'],$group)),'tradeKeys'=>metric_sample($group)];}
usort($weekly,fn($a,$b)=>strcmp($b['week'],$a['week']));

$buildGroups=[];foreach($closed as $trade){$buildLabel=$trade['strategyBuild']?:'Legacy';$parameterLabel=$trade['parameterHash']?:'no-parameter-hash';$buildGroups[$buildLabel.'|'.$parameterLabel][]=$trade;}
$buildComparison=[];foreach($buildGroups as $_buildKey=>$group){$groupReturns=array_column($group,'tradeReturn');$closedDates=array_values(array_filter(array_column($group,'closedAt')));sort($closedDates);$buildComparison[]=['build'=>$group[0]['strategyBuild']?:'Legacy','parameterHash'=>$group[0]['parameterHash'],'firstClosedAt'=>$closedDates[0]??'','lastClosedAt'=>$closedDates?end($closedDates):'','trades'=>count($group),'netProfit'=>array_sum(array_column($group,'profit')),'meanAccountReturnPercent'=>avg_values($groupReturns)*100,'winRate'=>count(array_filter($group,fn($trade)=>$trade['profit']>0))/count($group)*100,'sharpe'=>annualized_sharpe($groupReturns),'sortino'=>annualized_sortino($groupReturns)[0],'tradeKeys'=>metric_sample($group)];}
usort($buildComparison,fn($a,$b)=>strcmp((string)$a['firstClosedAt'],(string)$b['firstClosedAt']));

$strategyIndex=100.0;$benchmarkIndex=100.0;$benchmarkSeries=[];
foreach($closed as $trade){$strategyIndex*=1+$trade['tradeReturn'];$benchmarkIndex*=1+$trade['preleverageReturnPercent']/100.0;$benchmarkSeries[]=['tradeKey'=>trade_key($trade),'closedAt'=>$trade['closedAt'],'strategyIndex'=>$strategyIndex,'benchmarkIndex'=>$benchmarkIndex];}
$benchmark=['label'=>'Unleveraged US100 over the same trade windows','strategyReturnPercent'=>$strategyIndex-100,'benchmarkReturnPercent'=>$benchmarkIndex-100,'excessReturnPercent'=>$strategyIndex-$benchmarkIndex,'sampleCount'=>count($closed),'series'=>$benchmarkSeries,'tradeKeys'=>$allSample];

$hasTradeSpecificFilter=$effectiveRollingWeeks>0||$leverage!==''||$exitReason!==''||in_array($class,['A','B','C','D'],true);
$filteredDecisionSet=[];$filteredTicketSet=[];$tradeKeyByDecision=[];$tradeKeyByTicket=[];
foreach($trades as $trade){$tradeKey=trade_key($trade);if($trade['decisionId']!==''){$compound=$trade['strategyKey'].'|'.$trade['decisionId'];$filteredDecisionSet[$compound]=true;$tradeKeyByDecision[$compound]=$tradeKey;}if($trade['ticket']>0){$compound=$trade['strategyKey'].'|'.$trade['ticket'];$filteredTicketSet[$compound]=true;$tradeKeyByTicket[$compound]=$tradeKey;}}
$lifecycleGroups=[];
$appendLifecycle=function(array $row)use(&$lifecycleGroups,$hasTradeSpecificFilter,$filteredDecisionSet,$filteredTicketSet):void{$executionId=trim((string)($row['execution_id']??''));if($executionId==='')return;$stage=strtoupper((string)($row['stage']??''));if($stage==='')return;$eventStrategyKey=(string)$row['strategy_key'];$eventDecisionId=(string)($row['decision_id']??'');$eventTicket=(int)($row['position_ticket']??0);if($hasTradeSpecificFilter&&!isset($filteredDecisionSet[$eventStrategyKey.'|'.$eventDecisionId])&&!isset($filteredTicketSet[$eventStrategyKey.'|'.$eventTicket]))return;$entry=['stage'=>$stage,'eventAt'=>iso_value((string)$row['event_time']),'result'=>$row['result']===null?null:(bool)$row['result'],'retcode'=>$row['retcode']??null,'fillingMode'=>(string)($row['filling_mode']??''),'referencePrice'=>n($row['reference_price']??0),'actualPrice'=>n($row['actual_price']??0),'latencyMs'=>isset($row['latency_ms'])&&is_numeric($row['latency_ms'])?(float)$row['latency_ms']:null,'reason'=>(string)($row['reason']??'')];if(!isset($lifecycleGroups[$executionId]))$lifecycleGroups[$executionId]=['executionId'=>$executionId,'strategyKey'=>$eventStrategyKey,'decisionId'=>$eventDecisionId,'positionTicket'=>$eventTicket,'stages'=>[]];if($eventDecisionId!=='')$lifecycleGroups[$executionId]['decisionId']=$eventDecisionId;if($eventTicket>0)$lifecycleGroups[$executionId]['positionTicket']=$eventTicket;$lifecycleGroups[$executionId]['stages'][]=$entry;};
$stageSql="SELECT strategy_key,execution_id,decision_id,position_ticket,stage,occurred_at AS event_time,result,retcode,filling_mode,reference_price,actual_price,latency_ms,reason FROM strategy_execution_stages WHERE strategy_key IN ($placeholders) ORDER BY occurred_at,id";
$stageStmt=$db->prepare($stageSql);$stageStmt->execute($accountKeys);foreach($stageStmt->fetchAll() as $row)$appendLifecycle($row);
// Historical records created before v51 remain available from the diagnostic stream.
$eventSql="SELECT e.strategy_key,e.event_time,e.result,e.details FROM strategy_events e WHERE e.strategy_key IN ($placeholders) AND e.name='EXECUTION_STAGE' AND NOT EXISTS(SELECT 1 FROM strategy_execution_stages s WHERE s.strategy_key=e.strategy_key AND s.stage_record_id=e.event_hash) ORDER BY e.event_time,e.id";
$eventStmt=$db->prepare($eventSql);$eventStmt->execute($accountKeys);foreach($eventStmt->fetchAll() as $row){$details=[];try{$details=json_decode((string)$row['details'],true,512,JSON_THROW_ON_ERROR);}catch(Throwable){}if(!is_array($details))continue;$appendLifecycle(['strategy_key'=>$row['strategy_key'],'execution_id'=>$details['execution_id']??'','decision_id'=>$details['decision_id']??'','position_ticket'=>$details['position_ticket']??0,'stage'=>$details['stage']??'','event_time'=>$details['event_at']??$row['event_time'],'result'=>$row['result'],'retcode'=>$details['retcode']??null,'filling_mode'=>$details['filling_mode']??'','reference_price'=>$details['reference_price']??0,'actual_price'=>$details['actual_price']??0,'latency_ms'=>$details['latency_ms']??null,'reason'=>$details['reason']??'']);}
$lifecycles=[];$decisionLatencies=[];$decisionLatencyKeys=[];$ackLatencies=[];$ackLatencyKeys=[];$fillLatencies=[];$fillLatencyKeys=[];$protectionLatencies=[];$protectionLatencyKeys=[];$publicationLatencies=[];$publicationLatencyKeys=[];$mobileLatencies=[];$mobileLatencyKeys=[];$rejections=0;$attemptCount=0;$sentCount=0;$missed=0;$retcodes=[];$filling=[];$executionTradeKeys=[];$rejectionTradeKeys=[];$sentTradeKeys=[];$missedTradeKeys=[];$retcodeTradeKeys=[];$fillingTradeKeys=[];
foreach($lifecycleGroups as $lifecycle){
    $stageMap=[];foreach($lifecycle['stages'] as $stage){$stageName=$stage['stage'];if(!isset($stageMap[$stageName])){$stageMap[$stageName]=$stage;continue;}if($stageName==='MODIFIED'||($stageMap[$stageName]['result']===false&&$stage['result']!==false))$stageMap[$stageName]=$stage;}
    $compoundDecision=$lifecycle['strategyKey'].'|'.$lifecycle['decisionId'];$compoundTicket=$lifecycle['strategyKey'].'|'.$lifecycle['positionTicket'];$lifecycleTradeKey=$tradeKeyByDecision[$compoundDecision]??$tradeKeyByTicket[$compoundTicket]??'';if($lifecycleTradeKey!=='')$executionTradeKeys[]=$lifecycleTradeKey;
    foreach($lifecycle['stages'] as $stage){$stageName=$stage['stage'];if($stage['retcode']!==null&&in_array($stageName,['CHECKED','ACCEPTED','EXIT_CHECKED','EXIT_ACCEPTED'],true)){$retcode=(string)$stage['retcode'];$retcodes[$retcode]=($retcodes[$retcode]??0)+1;if($lifecycleTradeKey!=='')$retcodeTradeKeys[$retcode][]=$lifecycleTradeKey;}if(in_array($stageName,['CHECKED','EXIT_CHECKED'],true))$attemptCount++;if(in_array($stageName,['SENT','EXIT_SENT'],true)){$sentCount++;if($lifecycleTradeKey!=='')$sentTradeKeys[]=$lifecycleTradeKey;if($stage['fillingMode']!==''){$mode=$stage['fillingMode'];$filling[$mode]=($filling[$mode]??0)+1;if($lifecycleTradeKey!=='')$fillingTradeKeys[$mode][]=$lifecycleTradeKey;}}if($stageName==='MISSED_WINDOW'){$missed++;if($lifecycleTradeKey!=='')$missedTradeKeys[]=$lifecycleTradeKey;}if($stage['result']===false&&in_array($stageName,['CHECKED','ACCEPTED','EXIT_CHECKED','EXIT_ACCEPTED'],true)){$rejections++;if($lifecycleTradeKey!=='')$rejectionTradeKeys[]=$lifecycleTradeKey;}}
    $diff=function(string $a,string $b)use($stageMap):?float{$first=isset($stageMap[$a])?stage_millis($stageMap[$a]['eventAt']):null;$second=isset($stageMap[$b])?stage_millis($stageMap[$b]['eventAt']):null;return $first!==null&&$second!==null?max(0.0,$second-$first):null;};
    $reportedLatency=function(string $stage)use($stageMap):?float{if(!isset($stageMap[$stage]))return null;$value=$stageMap[$stage]['latencyMs'];return $value!==null&&is_finite((float)$value)&&((float)$value)>=0.0?(float)$value:null;};
    $decisionToSend=$diff('DECISION','SENT');$ack=$reportedLatency('ACCEPTED')??$diff('SENT','ACCEPTED');$fill=$reportedLatency('FILLED')??$diff('SENT','FILLED');$protection=$diff('FILLED','PROTECTED');$publication=$diff(isset($stageMap['CLOSED'])?'CLOSED':'FILLED','PUBLISHED');$mobile=$reportedLatency('MOBILE_RECEIPT')??$diff('PUBLISHED','MOBILE_RECEIPT');
    if($decisionToSend!==null){$decisionLatencies[]=$decisionToSend;if($lifecycleTradeKey!=='')$decisionLatencyKeys[]=$lifecycleTradeKey;}
    if($ack!==null){$ackLatencies[]=$ack;if($lifecycleTradeKey!=='')$ackLatencyKeys[]=$lifecycleTradeKey;}
    if($fill!==null){$fillLatencies[]=$fill;if($lifecycleTradeKey!=='')$fillLatencyKeys[]=$lifecycleTradeKey;}
    if($protection!==null){$protectionLatencies[]=$protection;if($lifecycleTradeKey!=='')$protectionLatencyKeys[]=$lifecycleTradeKey;}
    if($publication!==null){$publicationLatencies[]=$publication;if($lifecycleTradeKey!=='')$publicationLatencyKeys[]=$lifecycleTradeKey;}
    if($mobile!==null){$mobileLatencies[]=$mobile;if($lifecycleTradeKey!=='')$mobileLatencyKeys[]=$lifecycleTradeKey;}
    $entrySlippage=isset($stageMap['FILLED'])?$stageMap['FILLED']['actualPrice']-$stageMap['FILLED']['referencePrice']:null;$exitSlippage=isset($stageMap['EXIT_ACCEPTED'])?$stageMap['EXIT_ACCEPTED']['referencePrice']-$stageMap['EXIT_ACCEPTED']['actualPrice']:null;
    $lifecycle['decisionToSendMs']=$decisionToSend;$lifecycle['brokerAcknowledgementMs']=$ack;$lifecycle['fillMs']=$fill;$lifecycle['protectionAttachmentMs']=$protection;$lifecycle['backendPublicationMs']=$publication;$lifecycle['executorToMobileMs']=$mobile;$lifecycle['entrySlippagePoints']=$entrySlippage;$lifecycle['exitSlippagePoints']=$exitSlippage;$lifecycles[]=$lifecycle;
}
$uniqueKeys=fn(array $keys):array=>array_values(array_unique(array_filter($keys,fn($value)=>$value!=='')));
foreach($retcodeTradeKeys as $key=>$keys)$retcodeTradeKeys[$key]=$uniqueKeys($keys);foreach($fillingTradeKeys as $key=>$keys)$fillingTradeKeys[$key]=$uniqueKeys($keys);
$latencySummary=function(array $values,array $keys)use($uniqueKeys):array{return ['sampleCount'=>count($values),'medianMs'=>percentile_values($values,50),'p95Ms'=>percentile_values($values,95),'tradeKeys'=>$uniqueKeys($keys)];};
$executionQuality=['lifecycles'=>array_reverse(array_slice($lifecycles,-100)),'decisionToSend'=>$latencySummary($decisionLatencies,$decisionLatencyKeys),'brokerAcknowledgement'=>$latencySummary($ackLatencies,$ackLatencyKeys),'fill'=>$latencySummary($fillLatencies,$fillLatencyKeys),'protectionAttachment'=>$latencySummary($protectionLatencies,$protectionLatencyKeys),'backendPublication'=>$latencySummary($publicationLatencies,$publicationLatencyKeys),'executorToMobile'=>$latencySummary($mobileLatencies,$mobileLatencyKeys),'rejectionRatePercent'=>$attemptCount>0?$rejections/$attemptCount*100:0,'rejections'=>$rejections,'orderAttempts'=>$attemptCount,'sentOrders'=>$sentCount,'missedExecutionWindows'=>$missed,'retcodes'=>$retcodes,'fillingModes'=>$filling,'tradeKeys'=>$uniqueKeys($executionTradeKeys),'rejectionTradeKeys'=>$uniqueKeys($rejectionTradeKeys),'sentTradeKeys'=>$uniqueKeys($sentTradeKeys),'missedWindowTradeKeys'=>$uniqueKeys($missedTradeKeys),'retcodeTradeKeys'=>$retcodeTradeKeys,'fillingModeTradeKeys'=>$fillingTradeKeys];

$cashSql="SELECT strategy_key,flow_type,amount,occurred_at FROM account_cash_flows WHERE strategy_key IN ($placeholders)";$cashParams=$accountKeys;if($windowStartUtc!==null&&$windowEndUtc!==null){$cashSql.=' AND occurred_at>=? AND occurred_at<?';$cashParams[]=mysql_datetime($windowStartUtc);$cashParams[]=mysql_datetime($windowEndUtc);}$cashSql.=' ORDER BY occurred_at,id';
$cashStmt=$db->prepare($cashSql);$cashStmt->execute($cashParams);$initialByAccount=[];$topUps=0.0;$withdrawals=0.0;$cashByDay=[];
foreach($cashStmt->fetchAll() as $row){$key=(string)$row['strategy_key'];$type=strtoupper((string)$row['flow_type']);$amount=n($row['amount']);$day=warsaw_day((string)$row['occurred_at']);if($type==='INITIAL'&&!isset($initialByAccount[$key])){$initialByAccount[$key]=abs($amount);continue;}if($type==='TOP_UP'){$value=abs($amount);$topUps+=$value;$cashByDay[$day]=($cashByDay[$day]??0.0)+$value;}elseif($type==='WITHDRAWAL'){$value=abs($amount);$withdrawals+=$value;$cashByDay[$day]=($cashByDay[$day]??0.0)-$value;}}
foreach($accountKeys as $key){if(isset($initialByAccount[$key]))continue;foreach($closed as $trade){if($trade['strategyKey']===$key&&$trade['balanceBefore']>0){$initialByAccount[$key]=$trade['balanceBefore'];break;}}}
$initial=array_sum($initialByAccount);$netContributions=$initial+$topUps-$withdrawals;
$equitySql="SELECT strategy_key,captured_minute,equity FROM strategy_equity_points WHERE strategy_key IN ($placeholders)";$equityParams=$accountKeys;if($windowStartUtc!==null&&$windowEndUtc!==null){$equitySql.=' AND captured_minute>=? AND captured_minute<?';$equityParams[]=mysql_datetime($windowStartUtc);$equityParams[]=mysql_datetime($windowEndUtc);}$equitySql.=' ORDER BY captured_minute';
$equityStmt=$db->prepare($equitySql);$equityStmt->execute($equityParams);$equityByDay=[];
foreach($equityStmt->fetchAll() as $row){$day=warsaw_day((string)$row['captured_minute']);try{$weekday=(int)(new DateTimeImmutable($day,new DateTimeZone('Europe/Warsaw')))->format('N');}catch(Throwable){$weekday=1;}if($weekday>5)continue;$equityByDay[$day][(string)$row['strategy_key']]=n($row['equity']);}
ksort($equityByDay);$lastEquity=[];$daily=[];foreach($equityByDay as $day=>$values){foreach($values as $key=>$value)$lastEquity[$key]=$value;if($lastEquity)$daily[]=['day'=>$day,'equity'=>array_sum($lastEquity)];}
$dailyReturns=[];$adjustedCurve=[];$adjustedIndex=1.0;for($index=0;$index<count($daily);$index++){if($index>0){$previous=(float)$daily[$index-1]['equity'];$flow=(float)($cashByDay[$daily[$index]['day']]??0.0);$return=$previous>0?(((float)$daily[$index]['equity']-$flow)/$previous-1.0):0.0;if(is_finite($return)){$dailyReturns[]=$return;$adjustedIndex*=max(0.0000001,1.0+$return);}}$adjustedCurve[]=$adjustedIndex;}
$dailyPeakIndex=0.0;$dailyMaxDrawdownPercent=0.0;$ulcerSquares=[];foreach($adjustedCurve as $value){$dailyPeakIndex=max($dailyPeakIndex,(float)$value);if($dailyPeakIndex>0){$dd=((float)$value/$dailyPeakIndex-1.0)*100.0;$dailyMaxDrawdownPercent=min($dailyMaxDrawdownPercent,$dd);$ulcerSquares[]=$dd*$dd;}}
$ulcerIndex=$ulcerSquares?sqrt(avg_values($ulcerSquares)):0.0;$peakEquity=null;$maxDrawdownCurrency=0.0;foreach($daily as $point){$value=(float)$point['equity'];if($peakEquity===null||$value>$peakEquity)$peakEquity=$value;if($peakEquity>0)$maxDrawdownCurrency=min($maxDrawdownCurrency,$value-$peakEquity);}
$annualizedReturnPercent=0.0;if(count($daily)>=2&&$adjustedIndex>0){$startDate=new DateTimeImmutable($daily[0]['day'],new DateTimeZone('Europe/Warsaw'));$endDate=new DateTimeImmutable($daily[count($daily)-1]['day'],new DateTimeZone('Europe/Warsaw'));$days=max(1,$endDate->diff($startDate)->days);$annualizedReturnPercent=(pow($adjustedIndex,365.25/$days)-1.0)*100.0;}
$calmarRatio=abs($dailyMaxDrawdownPercent)>1e-12?$annualizedReturnPercent/abs($dailyMaxDrawdownPercent):0.0;$positiveDaily=array_values(array_filter($dailyReturns,fn($value)=>$value>0));$negativeDaily=array_values(array_filter($dailyReturns,fn($value)=>$value<0));$omegaRatio=abs(array_sum($negativeDaily))>1e-15?array_sum($positiveDaily)/abs(array_sum($negativeDaily)):($positiveDaily?999.999:0.0);$var95=$dailyReturns?(percentile_values($dailyReturns,5)??0.0)*100.0:0.0;$tail=array_values(array_filter($dailyReturns,fn($value)=>$value<=($var95/100.0+1e-15)));$expectedShortfall95=$tail?avg_values($tail)*100.0:$var95;
$durations=array_map(fn($trade)=>(float)$trade['durationSeconds'],$closed);$mfe=array_map(fn($trade)=>(float)$trade['mfePoints'],$closed);$mae=array_map(fn($trade)=>(float)$trade['maePoints'],$closed);$entrySlip=array_map(fn($trade)=>(float)$trade['entrySlippagePoints'],$closed);$exitSlip=array_map(fn($trade)=>(float)$trade['exitSlippagePoints'],$closed);$positiveWeeks=count(array_filter($weekly,fn($week)=>(float)$week['profit']>0));$captureValues=[];foreach($closed as $trade){$maximum=(float)$trade['maxProfit'];if($maximum>1e-12)$captureValues[]=max(-1.0,min(1.0,(float)$trade['profit']/$maximum))*100.0;}$captureEfficiency=avg_values($captureValues);$timeInMarket=0.0;if($closed){try{$first=new DateTimeImmutable((string)$closed[0]['openedAt']);$last=new DateTimeImmutable((string)$closed[count($closed)-1]['closedAt']);$span=max(1,$last->getTimestamp()-$first->getTimestamp());$timeInMarket=min(100.0,array_sum($durations)/$span*100.0);}catch(Throwable){}}

$distribution=$closed;usort($distribution,fn($a,$b)=>$b['preleverageReturnPercent']<=>$a['preleverageReturnPercent']);$distributionPoints=[];foreach($distribution as $index=>$trade)$distributionPoints[]=['rank'=>$index+1,'ticket'=>$trade['ticket'],'strategyKey'=>$trade['strategyKey'],'returnPercent'=>$trade['preleverageReturnPercent'],'tradeClass'=>$trade['tradeClass'],'exitReason'=>$trade['exitReason'],'closedAt'=>$trade['closedAt'],'profit'=>$trade['profit']];
$recent=$trades;usort($recent,fn($a,$b)=>strcmp($b['closedAt']?:$b['openedAt'],$a['closedAt']?:$a['openedAt']));

$summary=[
    'totalTrades'=>count($trades),'closedTrades'=>count($closed),'openTrades'=>count($open),'wins'=>count($wins),'losses'=>count($losses),'winRate'=>count($closed)?count($wins)/count($closed)*100:0,
    'netProfit'=>array_sum($profits),'initialBalance'=>$initial,'topUps'=>$topUps,'withdrawals'=>$withdrawals,'netContributions'=>$netContributions,'capitalAdjustedReturnPercent'=>abs($netContributions)>1e-15?array_sum($profits)/$netContributions*100:0,
    'positiveWeeksPercent'=>$weekly?$positiveWeeks/count($weekly)*100:0,'averageWeeklyProfit'=>avg_values(array_column($weekly,'profit')),
    'averageWeeklyPreleverageReturnPercent'=>avg_values(array_column($weekly,'preleverageReturnPercent')),'averageWeeklyLeveragedReturnPercent'=>avg_values(array_column($weekly,'leveragedReturnPercent')),
    'totalSlippagePoints'=>array_sum($entrySlip)+array_sum($exitSlip),'grossProfit'=>$grossProfit,'grossLoss'=>$grossLoss,
    'profitFactor'=>$grossLossAbs>1e-15?$grossProfit/$grossLossAbs:($grossProfit>0?999.999:0.0),'expectancy'=>avg_values($profits),'medianProfit'=>percentile_values($profits,50)??0,
    'averageWin'=>avg_values(array_column($wins,'profit')),'averageLoss'=>avg_values(array_column($losses,'profit')),'payoffRatio'=>abs(avg_values(array_column($losses,'profit')))>0?avg_values(array_column($wins,'profit'))/abs(avg_values(array_column($losses,'profit'))):0,
    'averageWinPreleverageReturnPercent'=>avg_values(array_column($wins,'preleverageReturnPercent')),'averageWinLeveragedReturnPercent'=>avg_values(array_column($wins,'tradeReturn'))*100,
    'averageLossPreleverageReturnPercent'=>avg_values(array_column($losses,'preleverageReturnPercent')),'averageLossLeveragedReturnPercent'=>avg_values(array_column($losses,'tradeReturn'))*100,
    'averageDurationSeconds'=>avg_values($durations),'averageMfePoints'=>avg_values($mfe),'averageMaePoints'=>avg_values($mae),
    'averageEntrySlippagePoints'=>avg_values($entrySlip),'averageExitSlippagePoints'=>avg_values($exitSlip),
    'captureEfficiencyPercent'=>$captureEfficiency,'edgeRatio'=>abs(avg_values($mae))>0?avg_values($mfe)/abs(avg_values($mae)):0,
    'maxDrawdown'=>$maxDrawdownCurrency,'recoveryFactor'=>abs($maxDrawdownCurrency)>0?array_sum($profits)/abs($maxDrawdownCurrency):0,'consistencyScore'=>$weekly?$positiveWeeks/count($weekly)*100:0,'maxWinStreak'=>longest_streak($profits,true),'maxLossStreak'=>longest_streak($profits,false),'timeInMarketPercent'=>$timeInMarket,
    'bestTrade'=>$profits?max($profits):0,'worstTrade'=>$profits?min($profits):0,'sharpeRatio'=>$sharpe??0,'sortinoRatio'=>$sortino??0,'sharpeAvailable'=>$sharpe!==null,'sortinoAvailable'=>$sortino!==null||$sortinoInfinite,'sortinoInfinite'=>$sortinoInfinite,
    'ratiosAnnualized'=>true,'periodsPerYear'=>52,'ratioSampleTrades'=>count($closed),'calmarRatio'=>$calmarRatio,'omegaRatio'=>$omegaRatio,'ulcerIndexPercent'=>$ulcerIndex,'valueAtRisk95Percent'=>$var95,'expectedShortfall95Percent'=>$expectedShortfall95,'riskSampleDays'=>count($dailyReturns),
];

$filterOptions=['accounts'=>array_values(array_map(fn($row)=>['key'=>(string)$row['account_key'],'label'=>(string)$row['display_name'],'type'=>(string)$row['account_type']],$allowed)),'leverages'=>array_values(array_unique(array_filter(array_map(fn($row)=>n($row['entry_leverage']??0),$activeOptionRows),fn($value)=>$value>0))),'exitReasons'=>array_values(array_unique(array_filter(array_map(fn($row)=>(string)($row['exit_reason']??''),$activeOptionRows),fn($value)=>$value!==''))),'availableWeeks'=>$availableWeeks,'defaultRollingWeeks'=>min(4,$availableWeeks),'effectiveRollingWeeks'=>$effectiveRollingWeeks,'windowStart'=>$windowStartUtc?atom_datetime($windowStartUtc):'','windowEndExclusive'=>$windowEndUtc?atom_datetime($windowEndUtc):'','classes'=>['A','B','C','D']];
sort($filterOptions['leverages']);sort($filterOptions['exitReasons']);
json_response(['ok'=>true,'generatedAt'=>atom_datetime(new DateTimeImmutable('now',new DateTimeZone('UTC'))),'filters'=>['scope'=>$scope,'account'=>$requested,'leverage'=>$leverage,'exitReason'=>$exitReason,'rollingWeeks'=>(int)$requestedRollingWeeks,'tradeClass'=>$class],'filterOptions'=>$filterOptions,'summary'=>$summary,'exitReasons'=>$exitReasons,'weekly'=>$weekly,'recentTrades'=>$recent,'tradeClasses'=>$classGroups,'tradeDistribution'=>['sortOrder'=>'BEST_TO_WORST','meanReturnPercent'=>avg_values(array_column($closed,'preleverageReturnPercent')),'trades'=>$distributionPoints],'rolling20'=>$rolling,'confidenceIntervals'=>$confidence,'classProfitContribution'=>$classGroups,'classDistribution'=>$classDistribution,'drawdown'=>['maxDrawdownPercent'=>abs($closedTradeMaxDrawdownPercent),'averageMaePercent'=>avg_values(array_column($closed,'maePercent')),'series'=>$drawdownSeries,'tradeKeys'=>$allSample],'parameterComparison'=>$buildComparison,'benchmark'=>$benchmark,'executionQuality'=>$executionQuality,'metricSamples'=>$metricSamples]);
