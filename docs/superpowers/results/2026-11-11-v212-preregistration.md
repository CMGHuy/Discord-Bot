# v212 pre-registration — Confluence limit entry partway to the support

**Spec:** `docs/superpowers/specs/2026-11-06-v212-confluence-limit-entry.md`, last changed in `d8d33c79`.
**Plan:** `docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_0-index.md`.
**Code:** `main` at `4497ddd8` (V212-1..V212-14 merged, CI green). No edit under `swingbot/` or `scripts/` until the last stage file is committed.
**Driver:** `scripts/backtest/measure_confluence_limit.py`; stage files under `docs/superpowers/results/v212/`.
**Committed before any compute.** `observed_n` is appended after the outcome-blind Stage −1 census, in its own commit, before Stage 0 (plan index § OPEN).

## The measurement (verbatim from the spec)

<!-- spec-quote-begin -->
### The rule (frozen here)

New knob: `CONFLUENCE_LIMIT_ENTRY_F` (float). The default 0 means off, and
today's behaviour stays byte-identical.

**Scope.** A confluence plan is in scope when all three hold:
- its `entry_type` today would be `market`;
- its `level` (the pre-clamp `scenario.stop_loss`: `supports[0]` for a
  long, `resistances[0]` for a short) lies more than 2% from the market
  price M;
- so today's stop was moved by the v115 clamp. That is read from
  `builders.clamped_distance` (`builders.py:588`), not `stop_moved_by`:
  only v191's ATR band sets `stop_moved_by`, so on the clamp path it is
  `None`.

The existing scenario gates (`MIN_STOP_DISTANCE_PCT` and the max-stop gate
in `levels.build_scenarios`) still run on the pre-clamp level before any
plan exists. They therefore bound each cell's D range. The results doc
prints the D range actually reached.

Breakout `stop_entry` plans and plans whose level is within 2% (their stop
already sits on structure) are untouched.

**For an in-scope long** (shorts mirrored), with S the level:

1. **Limit.** `L = M − f × (M − S)`, rounded to the tick toward M.
2. **Stop.** `S × (1 − 0.0025)`, 0.25% under the support, rounded to the
   tick away from L.
3. **Drop.** If `(L − stop) / L > 2%`, the plan is dropped. It is never
   clamped, so the stop always sits under structure. `MIN_STOP_DISTANCE_PCT`
   does not apply to these plans, because the stop is structural by
   construction. The count of fills with a stop under 1.75% is reported.
4. **Targets.** TP1 and TP2 keep today's prices. A plan whose TP1 fails
   `MIN_RISK_REWARD_RATIO` from L is dropped. That should not happen,
   because the entry only moves away from the target's opposite side. The
   drop count is reported.
5. **Expiry.** The limit is valid through the close of the 3rd full
   session after the alert session, frozen. In replay that is bars t+1 to
   t+3. The plan also cancels if TP1 trades before the fill.
6. **Fill: one rule that mirrors a broker's resting order,** shared by
   replay (`exit_sim_v2._limit_entry_v2`), live (`plan_manager` limit
   handling, v187 D3) and the measurement.
   - **Primary rule: trade-through.** The bar's low must trade at least one
     tick under L (`limit_strict_fill`). A bar that only touches L counts
     as a fill only in a disclosed sensitivity.
   - **Gap through L.** An open at or under L fills **at the open**.
   - **Gap through the stop.** An open at or under the stop fills **at the
     open**, and the stop sells at that same open. The realised result is
     about 0R less frictions, not a loss of more than 1R. The original
     wording said "more than 1R"; it was corrected 2026-11-06 because a
     resting limit fills at the open, not at L. A sensitivity scores these
     trades from L (pessimistic), disclosed and never gating. A gap through
     the stop is **never** silently cancelled, because a resting broker
     order would have filled; it carries `filled_stopped_gap`. Today's live
     `at_or_beyond_stop` cancel and fill-at-`trigger_price`
     (`plan_manager.py:1232-1249`) are changed **for this arm only**, so
     live, replay and the measurement agree. Out-of-scope plans keep
     today's live path.
   - **Price already at or under L when the alert is sent.** The order is
     marketable and fills at the quoted price. Replay starts at t+1 and
     cannot see this case, so live counts it and the shadow report
     discloses it.
   - **Frictions.** `swingbot/core/edge/frictions.py` applies, non-zero,
     to both arms on every trade.
7. **Sizing.** Fixed dollar risk on `|L − stop|`, with no change to the
   risk-per-trade setting. The notional caps
   `MAX_POSITION_SIZE_PCT` (`config.py:572`) and
   `MAX_POSITION_VALUE_ABSOLUTE` (`config.py:650`) **still bind** in replay,
   the measurement and live alike. A fill whose size a notional cap cut
   carries less than the fixed dollar risk, and its R is still scored on
   the plan's stop. The share of such fills is disclosed.
   - Every kept plan satisfies `|L − stop| / L ≤ 2%`, asserted in replay
     and live (`known-traps.md` § Stop floor and 2% cap).
   - The alert's suggested size equals the engine's size. An alert blocked
     by a heat, sector or cluster cap is still flagged with size 0, as
     today.
8. **Heat is re-checked at fill** *(author's call among the options the
   panel offered)*. Today's heat, sector, cluster and `MAX_OPEN_POSITIONS`
   checks (`scan_run.py:1210-1229`, `heat.py`) run at alert time against
   open trades only, so a pending limit reserves nothing. When a limit
   fills, the same checks run again against the then-open book, using the
   fill's actual risk.
   - If any cap would be breached, the fill is cancelled. The plan is then
     `cancelled_limit` with the reason `heat_at_fill`, and live posts a
     follow-up.
   - Replay applies the identical rule, so the scored portfolio is one that
     could exist. On a sell-off day this stops resting limits stacking risk
     past the caps.
   - Pending limits do not reserve heat, because that would block other
     alerts on orders that mostly never fill.
9. **Drops are logged** through the existing `plan rejected (` lines,
   with reasons `limit_scope`, `limit_stop_beyond_cap` and
   `limit_rr_fail`. A quiet day caused by this arm can then be diagnosed.

Grid (pre-registered, three cells): f ∈ {⅓, ½, ⅔}. **Looks: 3.** The
verdict unit is pooled over both directions. Per-direction results are
disclosed. A pass ships both directions or neither.

Each cell reaches its own slice of support distance: the drop rule admits
`D = (M − S)/M` up to about 1.75% / (1 − f). That is about 2.6% at ⅓, 3.5%
at ½ and 5.25% at ⅔. Each cell's reference arm is that cell's own in-scope
plans. The results doc prints each cell's D range and N.

### Pass rule

The partner's three clauses were set on 2026-11-06, as with v131. All are
point estimates, scored per cell. The comparison is **the arm's filled
trades** against **the reference arm's trades on the same in-scope
plans**: today's market entry and clamped stop.

1. **ExpR:** the arm's ExpR is greater than the reference's.
2. **Fills:** the arm's filled trades number at least 50% of the
   reference's trades, pooled over both directions.
3. **Win rate:** the arm's win rate is no more than 2 pp below the
   reference's.

How these sit inside the funnel (`backtest-methodology.md` § Acceptance
gate, § Funnel stages):

- **Gate family:** `validate_component.py --gate harvest`. Stage 2 uses
  `gate_expectancy_harvest` (`backtest_wf.py:278`). The win-rate gate
  family is not used, because ExpR is the objective.
- **Clause 2 replaces the funnel's volume clause** (`VOLUME_MAX_CUT_PCT`
  25%) for this pre-registration, as v131's own gate did. A limit that
  forgoes runners cannot meet a 25% cut by construction. Every other funnel
  clause applies unchanged.
- **Stage 0 MDE.** It uses the paired design over alert keys present in
  both arms (a filled arm trade and its reference trade). `observed_n` is
  the number of filled keys, stated in the pre-registration record. If
  Stage 0 is underpowered, the result is recorded as UNDERPOWERED, budget
  intact, as v191 was.
- **Stage 1 plateau.** The winner is the cell with the highest ExpR among
  those clearing all clauses. It must have each grid neighbour clear
  clauses 1–3 as well; ⅓ and ⅔ have one neighbour each. No plateau means
  no proceed.
- **Stage 3 thin seal.** Fewer than 30 filled trades per direction in the
  validation window is reported as THIN, never as a pass.
- **Multiple comparisons.** The 3 looks enter the ledger's
  `ledger_qvalues` BH family.

**Disclosures** (printed, never gating):

- the paired per-alert ΔR over every in-scope alert, with an unfilled
  limit scored 0R;
- dollar P&L per alert;
- each cell's D range;
- the effective stop distance from M on fills;
- fills stopped within 3 bars, and how often the expiry cap or the TP1
  cancel binds (v131's adverse-selection diagnostics);
- the scope and drop counts;
- the touch-fill sensitivity, scored with the same clauses;
- the count of gap-through-stop fills, and their mean R;
- the share of stops that were wick-throughs closing back above the stop
  (stop-run diagnostic; never grounds to widen the buffer);
- fills and ExpR by ATR14% bucket;
- fills and ExpR on SPY down days (close < prior close − 1%) against
  other days, and the number of distinct fill days;
- the share of fills with an earnings date inside the 3-bar window;
- dollar P&L at fixed risk per cell, on filled trades only;
- the share of fills whose size a notional cap cut;
- fills cancelled by `heat_at_fill`;
- risk and ruin (`edge/ruin.py`, `analytics/risk_metrics.py`), for the arm
  against the reference:
  - the worst single-day sum of R;
  - the maximum simultaneous open risk at one open;
  - the maximum drawdown;
  - the worst gap-through-stop R, and its per-day clustering.
<!-- spec-quote-end -->

## The mechanism as implemented

| Item | Value | Where |
|---|---|---|
| Knob | `CONFLUENCE_LIMIT_ENTRY_F`, default `"0"` (inert); the driver sets `f` per cell | `swingbot/config.py`, `ScanParams.confluence_limit_entry_f` |
| Scope | confluence plan, `entry_type` today `market` (not breakout), `builders.clamped_distance(M, level, is_bull) is not None` (level more than 2% from M); never `stop_moved_by` | `builders.apply_confluence_limit` |
| Limit | `L = M − f·(M − S)`, rounded to the tick toward M | `builders.confluence_limit_geometry` |
| Stop | `S·(1 − 0.0025)` long, `S·(1 + 0.0025)` short, rounded to the tick away from L | `builders.LIMIT_STOP_BUFFER = 0.0025` |
| Drops | `limit_stop_beyond_cap` when `(L − stop)/L > 2%`; `limit_rr_fail` when TP1 fails `MIN_RISK_REWARD_RATIO` from L; `limit_scope` when the rounded geometry is degenerate | `builders.LIMIT_DROP_REASONS` |
| Expiry | bars t+1..t+3 in replay | `builders.LIMIT_EXPIRY_BARS = 3` |
| Fill | trade-through (low ≤ L − tick) primary, touch as the disclosed sensitivity (`rows --touch`); open ≤ L fills at the open; a fill at or through the stop fills and stops at the open (`filled_stopped_gap`, outcome `loss`, about 0R less frictions); TP1 cancel inclusive; a bar reaching both L and TP1 cancels | `planning/limit_entry_rule.bar_outcome` |
| Frictions | `swingbot/core/edge/frictions.py`, both arms, every trade, at scoring | `confluence_limit_replay.net_r` |
| Portfolio pass | heat, sector, cluster, `MAX_OPEN_POSITIONS`, `MAX_POSITION_SIZE_PCT`, `MAX_POSITION_VALUE_ABSOLUTE`; arm signals dated at the fill date; both arms scored on the pass's kept trades | `backtest_wf.portfolio_replay`, `measure_confluence_limit.portfolio_pass` |
| Grid | `F_GRID = (1/3, 1/2, 2/3)`, cells `f0.333`, `f0.5`, `f0.667`; looks: 3 | `confluence_limit_replay.F_GRID` |
| Clauses | (1) arm ExpR > reference ExpR; (2) arm fills ≥ `FILLS_SHARE` = 0.5 × reference trades, pooled directions; (3) arm win rate ≥ reference − `WR_SLACK_PP` = 2.0 pp; point estimates | `measure_confluence_limit.clauses` |
| Gate family | harvest; Stage 2 `backtest_wf.gate_expectancy_harvest`; clause 2 replaces `VOLUME_MAX_CUT_PCT` | `measure_confluence_limit.py` |
| Stage chain | `REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}` | `measure_confluence_limit.REQUIRES` |
| Plateau | best cell clearing clauses 1–3 whose every grid neighbour clears them too (⅓ and ⅔ have one neighbour); tie rule as the `plateau()` docstring states: a tie keeps the smaller f: max keeps the first maximum in CELLS order | `measure_confluence_limit.plateau` |
| Thin seal | fewer than `THIN_PER_DIRECTION` = 30 filled trades per direction at Stage 3 is THIN, never a pass | `measure_confluence_limit.thin` |

## Decisions the spec left open (plan index § OPEN, author's calls)

- `limit_scope` is the drop for an in-scope plan whose rounded geometry is degenerate (L not strictly between the stop and M, or a non-finite level). Out-of-scope plans are untouched and never counted as drops.
- `filled_stopped_gap` is never a placeholder discard: the fill is persisted and closed by the stop, so the realised loss stays in the book.
- `observed_n` per cell is the number of in-scope TRAIN alerts whose arm limit filled (the paired keys of Stage 0), appended below after the census.
- Windows follow v139: TRAIN 2020-01-01..2023-12-31; folds 2021 / 2022 / 2023; VALIDATION 2024-01-01..2025-12-31.
- Ledger verdict mapping (the ledger enum has no UNDERPOWERED or THIN): refused at Stage −1 → `UNMEASURABLE`; UNDERPOWERED, no plateau or Stage 2 FAIL → `NO-LIFT` (v191 precedent); the selected cell's Stage 3 FAIL / THIN / PASS → `FAIL` / `INCONCLUSIVE` / `PASS`, the other two looks `NO-LIFT`.

## Populations

- Confluence plans only, both directions, pooled for the verdict; per-direction disclosed. Strategy-source and breakout plans are outside the population.
- Reference arm: today's market entry and clamped stop on each cell's own in-scope plans (`paired_alerts`, derived from one knob-0 replay, so both arms share the plan stream and the cooldown).
- Horizons and replay gates: the driver has no horizons flag and passes `LEGACY_HORIZONS` from `swingbot.core.market.strategy_types` (`measure_confluence_limit.py`), whose value is ('2w', '4w', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m'); replay gates are the driver defaults.

## Universe and data

- Universe `measure_arms.cached_universe()` with `MEASURE_ARMS_UNIVERSE=cache`: 649 tickers, latest bar 2026-09-28. The plan expected 60-80 tickers; that expectation is outdated since v162 (the cache universe is now every ticker the selected training data holds, here Alpaca). The partner decided on 2026-11-11 to freeze the full cache universe, N=649. For comparison, v131 used 74.
- Cache `data/backtest_cache_ext` (`BACKTEST_CACHE_DIR`); `data_source` alpaca (v162: named here before TRAIN is read). Survivorship bias favours longs; it applies to both arms alike.
- Tickers: A,AAL,AAP,AAPL,ABBV,ABNB,ABT,ACGL,ACN,ADBE,ADI,ADM,ADP,ADSK,ADT,AEE,AEP,AES,AFL,AIG,AIV,AIZ,AJG,AKAM,ALB,ALGN,ALK,ALL,ALLE,AMAT,AMCR,AMD,AME,AMG,AMGN,AMP,AMT,AMTM,AMZN,AN,ANET,ANF,AON,AOS,APA,APD,APH,APO,APP,APTV,ARE,ARES,ARM,ASML,ASTS,ATI,ATO,AVGO,AVY,AWK,AXON,AXP,AYI,AZO,BA,BAC,BALL,BAX,BBT,BBWI,BBY,BDX,BEAM,BEN,BF-B,BG,BHF,BIIB,BIO,BKNG,BKR,BLDR,BLK,BMY,BNY,BR,BRK-B,BRO,BSX,BWA,BX,BXP,C,CAG,CAH,CARR,CASY,CAT,CB,CBOE,CBRE,CCEP,CCI,CCL,CDNS,CDW,CE,CEG,CF,CFG,CHD,CHRW,CHTR,CI,CIEN,CINF,CL,CLF,CLX,CMCSA,CME,CMG,CMI,CMS,CNC,CNP,CNX,COF,COHR,COIN,COO,COP,COR,COST,COTY,CPAY,CPB,CPRI,CPRT,CPT,CPWR,CRH,CRL,CRM,CRWD,CRWV,CSCO,CSGP,CSX,CTAS,CTSH,CTVA,CVNA,CVS,CVX,CZR,D,DAL,DASH,DD,DDOG,DE,DECK,DELL,DG,DGX,DHI,DHR,DIS,DLR,DLTR,DOC,DOCU,DOG,DOV,DOW,DPZ,DRI,DTE,DUK,DVA,DVN,DXC,DXCM,EBAY,ECHO,ECL,ED,EFX,EG,EIX,EL,ELV,EMC,EME,EMN,EMR,ENPH,EOG,EP,EPAM,EQIX,EQT,ERIE,ES,ESS,ETN,ETR,ETSY,EVRG,EW,EXC,EXE,EXPD,EXPE,EXR,F,FANG,FAST,FB,FCPT,FCX,FDS,FDX,FE,FERG,FFIV,FHN,FICO,FIS,FISV,FITB,FIX,FLEX,FLR,FLS,FMC,FOSL,FOX,FOXA,FRT,FSLR,FTI,FTNT,FTV,GC_F,GD,GDDY,GE,GEHC,GEN,GENZ,GEV,GHC,GILD,GIS,GL,GLW,GM,GME,GNRC,GNW,GOOG,GOOGL,GPC,GPN,GR,GRMN,GS,GT,GWW,HAL,HAS,HBAN,HCA,HD,HIG,HII,HIMS,HLT,HOG,HON,HOOD,HP,HPE,HPQ,HRB,HRL,HSIC,HST,HSY,HUBB,HUM,HWM,IBKR,IBM,ICE,IDXX,IEX,IFF,ILMN,INCY,INFO,INTC,INTU,INVH,IP,IPGP,IQV,IR,IREN,IRM,ISRG,IT,ITT,ITW,IVZ,J,JAVA,JBHT,JBL,JCI,JEF,JKHY,JNJ,JPM,KDP,KEY,KEYS,KG,KHC,KIM,KKR,KLAC,KMB,KMI,KMX,KO,KR,KSS,KVUE,L,LB,LDOS,LEN,LH,LHX,LII,LIN,LITE,LKQ,LLY,LMT,LNC,LNT,LOW,LRCX,LULU,LUMN,LUV,LVS,LW,LYB,LYV,M,MA,MAA,MAC,MAR,MAS,MAT,MCD,MCHP,MCK,MCO,MDLZ,MDT,MET,META,MGM,MHK,MI,MKC,MKTX,MLM,MMI,MMM,MNST,MO,MOH,MOS,MPC,MPWR,MRK,MRNA,MRSH,MRVL,MS,MSCI,MSFT,MSI,MSTR,MTB,MTCH,MTD,MU,MUR,NAVI,NBIS,NBR,NCLH,NDAQ,NDSN,NE,NEE,NEM,NFLX,NI,NKE,NKTR,NOC,NOV,NOW,NRG,NSC,NTAP,NTRS,NUE,NVDA,NVR,NWL,NWS,NWSA,NXPI,NYT,O,ODFL,OGN,OI,OKE,OMC,ON,ORCL,ORLY,OTIS,OXY,PANW,PARA,PAYC,PAYX,PBI,PCAR,PCG,PCL,PEG,PENN,PEP,PFE,PFG,PG,PGR,PH,PHM,PKG,PLD,PLTR,PM,PNC,PNR,PNW,PODD,POOL,PPG,PPL,PRGO,PRU,PSA,PSKY,PSQ,PSX,PTC,PVH,PWR,PYPL,QBTS,QCOM,QRVO,R,RCL,RDDT,REG,REGN,RF,RHI,RIG,RJF,RKLB,RL,RMD,ROK,ROL,ROP,ROST,RRC,RSG,RTX,RVTY,RWM,S,SBAC,SBNY,SBUX,SCHW,SE,SEDG,SH,SHLD,SHOP,SHW,SIG,SII,SI_F,SJM,SLB,SLG,SLM,SMCI,SNA,SNDK,SNOW,SNPS,SO,SOFI,SOLV,SPG,SPGI,SPY,SRE,STE,STI,STLD,STT,STX,STZ,SUN,SW,SWK,SWKS,SYF,SYK,SYY,T,TAP,TDC,TDG,TDY,TE,TECH,TEL,TER,TFC,TFX,TGT,THC,TJX,TKO,TLT,TMO,TMUS,TPL,TPR,TRGP,TRIP,TRMB,TROW,TRV,TSCO,TSLA,TSN,TT,TTD,TTWO,TXN,TXT,TYL,UA,UAA,UAL,UBER,UDR,UHS,ULTA,UNH,UNM,UNP,UPS,URBN,URI,USB,UUP,V,VEEV,VFC,VIAV,VICI,VLO,VLTO,VMC,VMRK,VNO,VNT,VRSK,VRSN,VRT,VRTX,VST,VTR,VTRS,VZ,WAB,WAT,WBD,WDAY,WDC,WEC,WELL,WFC,WHR,WM,WMB,WMT,WRB,WSM,WST,WTW,WU,WY,WYNN,XEL,XOM,XRAY,XRX,XYL,XYZ,YUM,ZBH,ZBRA,ZION,ZTS

## Commands

`$P` = this file. Every command runs from `E:/Documents/Private/Projects/Discord-Bot` on `main`, with the environment `MEASURE_ARMS_UNIVERSE=cache BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`, written `<ENV>` below:

```bash
<ENV> python -u scripts/backtest/measure_confluence_limit.py census --window train --preregistration $P --checkpoint-dir logs/v212/ckpt-census-train --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage -1 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py rows --window train --preregistration $P --checkpoint-dir logs/v212/ckpt-rows-train --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py rows --window train --touch --preregistration $P --checkpoint-dir logs/v212/ckpt-rows-train-touch --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage 0 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage 1 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage 2 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py stage --stage 3 --preregistration $P --out docs/superpowers/results/v212
<ENV> python -u scripts/backtest/measure_confluence_limit.py ledger --preregistration $P --run-date <run date, UTC YYYY-MM-DD> --record <path of the stage-3 record>
```

`--run-date` and `--record` are required by the `ledger` CLI; V212-17 supplies them at run time (the run date and the Stage 3 record path), not chosen here.

Outputs: `docs/superpowers/results/v212/v212-census-train-rows.json`, `v212-rows-train-rows.json`, `v212-rows-train-touch-rows.json`, `stage-1.json`, `v212-stage0.json` .. `v212-stage3.json`. Stage 3 (which builds the VALIDATION rows for the selected cell) runs once, only after Stage 2 PASS.

## Multiple testing

Three looks (`f0.333`, `f0.5`, `f0.667`), pooled over both directions. They enter the ledger's `ledger_qvalues` BH family as three rows; the q-values are reported, never gating. The guards are the plateau rule, the three clauses, the Stage 2 folds and the one Stage 3 shot.

## Not re-run

v131 (Fibonacci Limit, strategy source), v139 arms S and D, v191 arms K and R and the v115 clamp are untouched: this moves the **entry** on clamped **confluence** plans, a mechanism no closed row covers (spec § Why). A fail closes this rule; another f, buffer, expiry or a limit at the support is not a new mechanism (spec § Anti-goals).

## observed_n (appended after the Stage −1 census, before Stage 0)

- `f0.333`: observed_n = 15180 filled keys of 38630 in-scope TRAIN alerts
- `f0.5`: observed_n = 20162 filled keys of 38630 in-scope TRAIN alerts
- `f0.667`: observed_n = 20939 filled keys of 38630 in-scope TRAIN alerts
