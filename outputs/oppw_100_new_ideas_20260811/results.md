# OPPW: 100 new causal entry-skip ideas

Generated 2026-08-11 from `backtest/quotes.pkl` using the current `oppw24.py` baseline from 2018-04-13 through the last completed trade.

Each idea is a standalone causal entry gate. When its signal is true at the weekly cash open, that week's baseline entry is replaced by a 0% return. Signals use only prior completed sessions and the current premarket. Results use fixed 11.3x leverage and no tax or deposits.

Previously explored last-N loss gates, plain opening-gap gates, simple momentum/MA/RSI/ATR gates, Tuesday re-entry, and long-market-break rules were deliberately excluded.

## Baseline

- Completed weekly trades: 432
- Weekly geometric return: 2.408353%
- Weekly-close maximum drawdown: -96.6264%
- Worst rolling 52 observed weeks: -69.6325%

## Ranked results

|Rank|ID|Idea|Skips|Skipped L/W|Weekly geo|Delta|Max DD|DD improvement|Worst 52|Worst-52 improvement|Post-2021 geo|2022-2025 geo|
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|1|50|Premarket closes near its low|36|20/16|2.911976%|+0.503623 pp|-86.7755%|+9.8509 pp|-34.6978%|+34.9347 pp|2.595004%|2.905922%|
|2|55|Premarket low early and close near high|91|43/48|2.852529%|+0.444176 pp|-96.5002%|+0.1262 pp|-76.8902%|-7.2577 pp|3.302379%|4.259604%|
|3|73|Positive return autocorrelation after decline|12|6/6|2.792771%|+0.384418 pp|-92.7876%|+3.8388 pp|-36.2447%|+33.3878 pp|2.707859%|3.079802%|
|4|61|Strong negative 20-session return skew|33|15/18|2.707616%|+0.299263 pp|-96.6264%|+0.0000 pp|-76.6612%|-7.0287 pp|3.024282%|3.739903%|
|5|51|Premarket closes near its high|56|26/30|2.604704%|+0.196351 pp|-96.5002%|+0.1262 pp|-68.4969%|+1.1356 pp|2.979247%|3.724825%|
|6|41|Efficient premarket decline|31|15/16|2.585619%|+0.177266 pp|-92.0505%|+4.5759 pp|-42.0450%|+27.5876 pp|2.567035%|3.188472%|
|7|14|Two consecutive lower-wick rejections|40|13/27|2.572433%|+0.164080 pp|-86.7755%|+9.8509 pp|-43.4455%|+26.1870 pp|1.471588%|2.079959%|
|8|7|Inside session after wide session|17|11/6|2.568205%|+0.159852 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.730776%|3.635379%|
|9|95|Volatility contraction followed by wide choppy premarket|2|1/1|2.542892%|+0.134539 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.646130%|3.215521%|
|10|87|Negative skew plus downward statistical jump|3|2/1|2.522066%|+0.113713 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.568139%|3.191650%|
|11|89|Negative autocorrelation plus upper-wick rejection|1|1/0|2.509357%|+0.101004 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.549330%|3.215521%|
|12|18|Three-session narrowing ending bullish|60|29/31|2.505164%|+0.096811 pp|-92.7413%|+3.8851 pp|-30.7899%|+38.8426 pp|2.346374%|2.842813%|
|13|39|Late rejection at least 1% below session high|8|5/3|2.481032%|+0.072679 pp|-93.2234%|+3.4030 pp|-51.6325%|+18.0000 pp|2.268104%|2.983940%|
|14|44|Premarket V-recovery from low|68|27/41|2.476571%|+0.068218 pp|-96.8714%|-0.2450 pp|-73.3695%|-3.7370 pp|3.291571%|4.294894%|
|15|54|Premarket high early and close near low|53|26/27|2.463864%|+0.055511 pp|-88.9264%|+7.7000 pp|-40.2238%|+29.4087 pp|2.506197%|2.798993%|
|16|69|Five-session volatility expansion after advance|9|5/4|2.463606%|+0.055253 pp|-96.4667%|+0.1597 pp|-75.3222%|-5.6897 pp|2.679416%|3.523538%|
|17|96|Inside session followed by opening discontinuity|1|1/0|2.462207%|+0.053854 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.399876%|3.215521%|
|18|24|Previous last-hour surge|15|5/10|2.453206%|+0.044853 pp|-93.2234%|+3.4030 pp|-77.6743%|-8.0418 pp|2.352149%|3.327397%|
|19|52|Overnight rise contradicted by premarket decline|1|1/0|2.446873%|+0.038520 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.456864%|3.215521%|
|20|82|Bullish marubozu plus premarket inverted-V|4|2/2|2.434644%|+0.026291 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.438771%|3.291053%|
|21|91|Previous last-hour and current premarket selloffs|2|2/0|2.430061%|+0.021708 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.415227%|3.237140%|
|22|21|Early rally followed by late selloff|7|4/3|2.416602%|+0.008249 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.413880%|3.352872%|
|23|37|Low-reversal directional down session|1|1/0|2.415975%|+0.007622 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.411151%|3.231400%|
|24|47|Premarket final-hour surge|4|1/3|2.415387%|+0.007034 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.531157%|3.516671%|
|25|76|Two-period mean-reversion variance ratio after decline|30|13/17|2.414490%|+0.006137 pp|-93.2234%|+3.4030 pp|-67.7452%|+1.8873 pp|2.602556%|3.321200%|
|26|68|Five-session volatility expansion after decline|7|4/3|2.407097%|-0.001256 pp|-96.6264%|+0.0000 pp|-61.4687%|+8.1638 pp|2.343689%|3.136404%|
|27|71|High range-volatility with low previous close|12|6/6|2.404575%|-0.003778 pp|-96.9659%|-0.3395 pp|-81.7350%|-12.1025 pp|2.657122%|3.230964%|
|28|8|Two consecutive inside sessions|2|1/1|2.403889%|-0.004464 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.416056%|3.238307%|
|29|94|Downward jump followed by premarket V-recovery|5|2/3|2.390502%|-0.017851 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.373470%|2.968949%|
|30|22|Early selloff followed by late rebound|11|3/8|2.389163%|-0.019190 pp|-96.4667%|+0.1597 pp|-70.3632%|-0.7307 pp|2.413663%|3.274097%|
|31|38|Low-reversal directional up session|3|1/2|2.388471%|-0.019882 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.370464%|3.174104%|
|32|11|Wide doji|2|1/1|2.374832%|-0.033521 pp|-96.4667%|+0.1597 pp|-68.1949%|+1.4376 pp|2.334079%|3.122874%|
|33|90|Efficient 20-session decline plus weak premarket close|2|1/1|2.365684%|-0.042669 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.336760%|3.126648%|
|34|84|Wide doji plus directional premarket|1|0/1|2.363871%|-0.044482 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.334079%|3.122874%|
|35|100|Bullish rejection plus upward opening discontinuity|2|0/2|2.359711%|-0.048642 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.356585%|3.154561%|
|36|35|Up session with last-hour range concentration|42|19/23|2.351650%|-0.056703 pp|-96.4667%|+0.1597 pp|-75.5569%|-5.9244 pp|2.629430%|3.719699%|
|37|42|Efficient premarket advance|39|16/23|2.340922%|-0.067431 pp|-96.8714%|-0.2450 pp|-71.8383%|-2.2058 pp|2.669834%|3.345932%|
|38|65|Upward statistical jump|6|2/4|2.338093%|-0.070260 pp|-96.6264%|+0.0000 pp|-73.0474%|-3.4149 pp|2.354228%|3.128533%|
|39|93|Late downside range concentration plus premarket selloff|2|1/1|2.330775%|-0.077578 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.285133%|3.053970%|
|40|23|Previous last-hour selloff|17|9/8|2.328753%|-0.079600 pp|-96.6264%|+0.0000 pp|-73.0834%|-3.4509 pp|2.328492%|3.183382%|
|41|81|Bearish marubozu plus efficient premarket decline|4|2/2|2.319069%|-0.089284 pp|-96.6264%|+0.0000 pp|-71.7772%|-2.1447 pp|2.267823%|3.295506%|
|42|49|Cash open drops below final premarket print|6|2/4|2.317261%|-0.091092 pp|-96.6264%|+0.0000 pp|-70.8088%|-1.1763 pp|2.265150%|3.275061%|
|43|12|Compressed doji|21|11/10|2.315248%|-0.093105 pp|-96.9842%|-0.3578 pp|-81.9810%|-12.3485 pp|2.511341%|3.096526%|
|44|59|Very efficient premarket decline|8|2/6|2.308788%|-0.099565 pp|-96.6264%|+0.0000 pp|-72.5323%|-2.8998 pp|2.338102%|3.128538%|
|45|40|Late recovery at least 1% above session low|17|6/11|2.304065%|-0.104288 pp|-91.6742%|+4.9522 pp|-77.3089%|-7.6764 pp|2.184361%|3.068998%|
|46|3|Upper-wick rejection on above-median range|17|7/10|2.301894%|-0.106459 pp|-96.8247%|-0.1983 pp|-71.9319%|-2.2994 pp|2.253263%|2.880470%|
|47|20|Previous gap-down fully recovered|20|7/13|2.287947%|-0.120406 pp|-96.6264%|+0.0000 pp|-74.4849%|-4.8524 pp|2.474247%|3.543803%|
|48|34|Down session with last-hour range concentration|40|20/20|2.273757%|-0.134596 pp|-96.6264%|+0.0000 pp|-63.9204%|+5.7121 pp|1.935763%|2.794061%|
|49|57|Compressed premarket followed by opening discontinuity|11|4/7|2.270540%|-0.137813 pp|-96.6264%|+0.0000 pp|-61.4687%|+8.1638 pp|2.212122%|2.951211%|
|50|48|Cash open jumps above final premarket print|40|16/24|2.268998%|-0.139355 pp|-96.6264%|+0.0000 pp|-79.7057%|-10.0732 pp|2.535895%|2.728380%|
|51|62|Strong positive 20-session return skew|16|5/11|2.268094%|-0.140259 pp|-96.6264%|+0.0000 pp|-75.7864%|-6.1539 pp|2.271740%|3.035118%|
|52|60|Very efficient premarket advance|12|4/8|2.259581%|-0.148772 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.368225%|2.932076%|
|53|63|High 20-session kurtosis with latest decline|19|8/11|2.258617%|-0.149736 pp|-96.6264%|+0.0000 pp|-67.5331%|+2.0994 pp|2.530827%|3.139207%|
|54|97|Repeated low closes plus weak premarket close|6|2/4|2.253732%|-0.154621 pp|-96.6264%|+0.0000 pp|-74.4169%|-4.7844 pp|2.256304%|3.013391%|
|55|4|Lower-wick rejection on above-median range|24|8/16|2.248727%|-0.159626 pp|-96.4667%|+0.1597 pp|-74.1549%|-4.5224 pp|2.101185%|2.971770%|
|56|26|Morning selloff and midday rebound|12|3/9|2.242024%|-0.166329 pp|-96.6264%|+0.0000 pp|-69.2073%|+0.4252 pp|2.331233%|3.341899%|
|57|53|Overnight decline contradicted by premarket rise|8|2/6|2.237397%|-0.170956 pp|-96.6264%|+0.0000 pp|-69.6325%|+0.0000 pp|2.328433%|3.114925%|
|58|64|Downward statistical jump|10|4/6|2.206013%|-0.202340 pp|-96.6264%|+0.0000 pp|-67.9369%|+1.6956 pp|2.081693%|2.559160%|
|59|25|Morning rally and midday fade|14|7/7|2.203615%|-0.204738 pp|-96.5002%|+0.1262 pp|-72.3878%|-2.7553 pp|2.218087%|2.959605%|
|60|13|Two consecutive upper-wick rejections|18|8/10|2.196981%|-0.211372 pp|-96.9842%|-0.3578 pp|-74.1199%|-4.4874 pp|2.154537%|2.957798%|
|61|70|Volatility contraction with low previous close|15|5/10|2.182409%|-0.225944 pp|-96.6264%|+0.0000 pp|-82.3412%|-12.7087 pp|2.485121%|2.997840%|
|62|46|Premarket final-hour selloff|9|3/6|2.177299%|-0.231054 pp|-96.7789%|-0.1525 pp|-73.5819%|-3.9494 pp|2.178931%|2.904506%|
|63|86|Down-volatility expansion or premarket selloff|16|7/9|2.176046%|-0.232307 pp|-96.7789%|-0.1525 pp|-66.4798%|+3.1527 pp|2.122865%|2.825628%|
|64|74|Low sign entropy with negative majority|4|0/4|2.168279%|-0.240074 pp|-96.9842%|-0.3578 pp|-80.7358%|-11.1033 pp|2.220553%|2.963075%|
|65|28|Early low and top-quartile close|139|57/82|2.155600%|-0.252753 pp|-93.6427%|+2.9837 pp|-90.5088%|-20.8763 pp|2.312626%|3.545729%|
|66|10|Upside range expansion|21|5/16|2.133952%|-0.274401 pp|-96.4667%|+0.1597 pp|-75.4054%|-5.7729 pp|2.217755%|3.411702%|
|67|2|Previous bullish marubozu|57|24/33|2.125406%|-0.282947 pp|-96.6264%|+0.0000 pp|-83.9067%|-14.2742 pp|2.430420%|3.865324%|
|68|16|Two of three closes in top quartile|128|57/71|2.067960%|-0.340393 pp|-93.3670%|+3.2594 pp|-74.7755%|-5.1430 pp|2.171594%|3.233611%|
|69|77|Two-period trending variance ratio after decline|15|5/10|2.061642%|-0.346711 pp|-96.9842%|-0.3578 pp|-72.8534%|-3.2209 pp|1.874900%|2.599586%|
|70|36|High intraday 30-minute reversal count|114|47/67|2.054627%|-0.353726 pp|-94.0368%|+2.5896 pp|-64.3297%|+5.3028 pp|1.486894%|2.098657%|
|71|88|Downside-tail cluster plus downside range expansion|6|0/6|2.017682%|-0.390671 pp|-97.4614%|-0.8350 pp|-84.7178%|-15.0853 pp|2.080872%|2.766559%|
|72|85|Choppy wide cash session plus opening discontinuity|15|3/12|1.984738%|-0.423615 pp|-96.6264%|+0.0000 pp|-67.9369%|+1.6956 pp|1.758585%|2.496466%|
|73|45|Premarket inverted-V rejection|54|23/31|1.983852%|-0.424501 pp|-90.4404%|+6.1860 pp|-44.8032%|+24.8293 pp|1.757287%|2.171205%|
|74|17|Three-session narrowing ending bearish|24|9/15|1.966813%|-0.441540 pp|-96.6264%|+0.0000 pp|-72.5572%|-2.9247 pp|2.184297%|3.005835%|
|75|19|Previous gap-up fully faded|19|7/12|1.957473%|-0.450880 pp|-96.6264%|+0.0000 pp|-69.0306%|+0.6019 pp|1.672113%|2.353210%|
|76|67|Upside semivariance dominates|68|35/33|1.941045%|-0.467308 pp|-96.6264%|+0.0000 pp|-76.4897%|-6.8572 pp|1.787940%|2.322705%|
|77|78|Efficient 20-session declining path|21|6/15|1.928360%|-0.479993 pp|-93.2234%|+3.4030 pp|-55.2716%|+14.3609 pp|1.603020%|2.278605%|
|78|80|Cluster of upside-tail sessions|89|43/46|1.895079%|-0.513274 pp|-96.6264%|+0.0000 pp|-73.7406%|-4.1081 pp|1.610596%|2.394689%|
|79|6|Bullish outside session|14|2/12|1.885352%|-0.523001 pp|-96.6264%|+0.0000 pp|-72.5323%|-2.8998 pp|1.707632%|2.553515%|
|80|72|Negative return autocorrelation after decline|40|17/23|1.876218%|-0.532135 pp|-93.8542%|+2.7722 pp|-78.0863%|-8.4538 pp|2.141303%|2.903576%|
|81|98|High reversal counts in cash and premarket|66|25/41|1.873951%|-0.534402 pp|-96.9671%|-0.3407 pp|-88.6009%|-18.9684 pp|2.050323%|2.666713%|
|82|30|Directional up session from early low to late high|115|46/69|1.852646%|-0.555707 pp|-93.3670%|+3.2594 pp|-80.8426%|-11.2101 pp|1.653522%|2.232336%|
|83|32|High-efficiency up cash session|52|22/30|1.843269%|-0.565084 pp|-96.6264%|+0.0000 pp|-82.4956%|-12.8631 pp|1.898521%|2.924872%|
|84|31|High-efficiency down cash session|29|9/20|1.814793%|-0.593560 pp|-97.6977%|-1.0713 pp|-88.2243%|-18.5918 pp|1.957759%|2.508220%|
|85|5|Bearish outside session|29|9/20|1.762923%|-0.645430 pp|-97.2504%|-0.6240 pp|-79.9415%|-10.3090 pp|1.854036%|2.547078%|
|86|83|Prior gap-up fade or premarket final-hour selloff|28|10/18|1.727436%|-0.680917 pp|-96.7789%|-0.1525 pp|-73.0582%|-3.4257 pp|1.452738%|2.044794%|
|87|43|Wide choppy premarket|92|32/60|1.723866%|-0.684487 pp|-92.7364%|+3.8900 pp|-57.6923%|+11.9402 pp|1.893974%|2.286151%|
|88|66|Downside semivariance dominates|65|23/42|1.708570%|-0.699783 pp|-96.7918%|-0.1654 pp|-83.7150%|-14.0825 pp|2.054665%|2.802203%|
|89|79|Cluster of downside-tail sessions|45|13/32|1.693339%|-0.715014 pp|-93.7348%|+2.8916 pp|-69.0906%|+0.5419 pp|1.502746%|2.516603%|
|90|99|Bearish rejection or downward opening discontinuity|50|18/32|1.662170%|-0.746183 pp|-97.4586%|-0.8322 pp|-81.4603%|-11.8277 pp|1.715658%|2.471944%|
|91|9|Downside range expansion|31|10/21|1.646221%|-0.762132 pp|-97.4614%|-0.8350 pp|-86.7779%|-17.1454 pp|1.747936%|2.169061%|
|92|56|Premarket range exceeds previous cash range|112|48/64|1.639890%|-0.768463 pp|-96.9842%|-0.3578 pp|-83.9657%|-14.3332 pp|2.075594%|2.398693%|
|93|92|Directional down session or overnight-up contradiction|72|29/43|1.548854%|-0.859499 pp|-97.4605%|-0.8341 pp|-85.4738%|-15.8413 pp|1.611271%|2.175270%|
|94|29|Directional down session from early high to late low|71|28/43|1.510672%|-0.897681 pp|-97.4605%|-0.8341 pp|-85.4738%|-15.8413 pp|1.554752%|2.175270%|
|95|1|Previous bearish marubozu|40|13/27|1.503944%|-0.904409 pp|-97.5887%|-0.9623 pp|-85.2489%|-15.6164 pp|1.414099%|1.984547%|
|96|27|Early high and bottom-quartile close|79|31/48|1.503806%|-0.904547 pp|-97.7638%|-1.1374 pp|-87.8190%|-18.1865 pp|1.790579%|2.241723%|
|97|75|High sign entropy after wide session|92|31/61|1.433986%|-0.974367 pp|-92.8612%|+3.7652 pp|-88.7125%|-19.0800 pp|1.460073%|2.715733%|
|98|58|High premarket hourly reversal count|227|94/133|1.258109%|-1.150244 pp|-81.4078%|+15.2186 pp|-74.7373%|-5.1048 pp|1.568500%|2.182310%|
|99|15|Two of three closes in bottom quartile|54|14/40|1.164569%|-1.243784 pp|-97.6232%|-0.9968 pp|-87.7557%|-18.1232 pp|1.264235%|1.467397%|
|100|33|Wide but inefficient cash session|110|32/78|0.664790%|-1.743563 pp|-97.4460%|-0.8196 pp|-90.5298%|-20.8973 pp|0.485442%|1.652940%|

## Interpretation limits

These are exploratory in-sample screens over 100 hypotheses. Ranking does not constitute untouched out-of-sample confirmation. Thresholds must be frozen before walk-forward or live shadow evaluation.

The accompanying `test_100_new_ideas.py` contains every exact causal formula and threshold used for this report.
