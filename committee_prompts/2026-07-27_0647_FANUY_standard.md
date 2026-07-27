# COMMITTEE DATA PAYLOAD — FANUY (Standard)
Generated: 2026-07-27 06:47 local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: Industrials | Industry: Specialty Industrial Machinery
- Next earnings: in 4 day(s)

## Trigger(s) breached
- Earnings gate OPENED — earnings in 4 business day(s), positivity 71/100, beat streak 3/4 — buy decision is now actionable

## Prior ledger state
- Previous Overall Score: 61/110
- Previous Timing Score: 0/100
- Previous Confidence: 65%
- Previous evaluation date: 2026-07-24 12:46

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): 61/110 → local rating band: Watch
- Timing: 5/100
- Data-completeness confidence (proxy): 65%
- Category proxies (3/11 are ESTIMATES from missing data — weigh accordingly):
  - Valuation: 6/10
  - Cash Generation: 6/10
  - Growth: 6/10
  - Revenue Visibility: 5/10  [ESTIMATE — source data missing, do not trust]
  - Margin Quality: 8/10
  - Balance Sheet: 5/10  [ESTIMATE — source data missing, do not trust]
  - Capital Allocation: 4/10
  - Macro Exposure: 10/10
  - Competitive Moat: 5/10
  - Analyst Sentiment: 5/10  [ESTIMATE — source data missing, do not trust]
  - Technical Position: 1/10

## Earnings gate (actionable-BUY policy: earnings within 10 business days AND
## strict positivity pass — score >=70, >=3 signals, beat streak >=3/4. A Buy
## rating without this gate is thesis-only, NOT actionable; committee should
## confirm or veto the positivity call using transcript/guidance judgment)
  - Earnings in business days: 4 (buy window: ≤10)
  - Earnings Positivity Score: 71/100 (strict pass bar 70, beat streak 3/4 last quarters)
    - Analyst EPS revision momentum: 81
    - Earnings surprise history: 72
    - Pre-earnings relative strength vs SPY: 49
    - Recommendation upgrades vs downgrades (90d): GAPPED
    - Short interest level & trend: GAPPED
  - GATE VERDICT: ACTIONABLE BUY WINDOW

## Supermajority consensus vote (last gate before a BUY alert)
  - Verdict: FAIL — 2/9 systems bullish (supermajority 65%, min 6 computable)
    - momentum_timing: ✘
    - factor_tier_high: ✘
    - piotroski: ✔
    - canslim: ✘
    - estimate_revisions: ✔
    - insider_signal: GAPPED
    - momentum_6m: ✘
    - breakout_52wk: ✘
    - positivity_margin: ✘
    - quality_gates: ✘
  - HARD VETO: hostile market regime: SPY>!50d/200d, VIX 17.8 (max 28.0), term 0.868
  - Market regime: SPY>!50d/200d, VIX 17.8 (max 28.0), term 0.868 — HOSTILE

## Call-option candidate (independent options engine; committee should judge premium vs expected move, not just direction)
  - Judge confluence: 0/1 judges bullish (need >=100% of >=3) — vol_mispricing GAPPED, trend ✘, catalyst GAPPED, flow_proxy GAPPED
  - HARD VETO: 6-mo momentum -3% < 0% (falling knife)
  - HARD VETO: hostile market regime: SPY>!50d/200d, VIX 17.8 (max 28.0), term 0.868
  - No contract proposed: against: trend; 6-mo momentum -3% < 0% (falling knife); hostile market regime: SPY>!50d/200d, VIX 17.8 (max 28.0), term 0.868

## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
  - Magic Formula rank: #93 of 104 in universe (earnings yield -26.3%, return on capital 11.1%)
  - Piotroski F-Score: 7/9 (1 tests gapped) (8-9 strong, 0-2 weak)
  - PEG (GARP): 3.25
  - Momentum: 6-mo -2.9%, 12-mo +35.6%
  - Quality gates (Buffett-style): ROE >= 15%: FAIL; Debt/Equity < 0.5: GAPPED; Gross margin > 40%: FAIL; CFO > Net Income: PASS
  - Graham/Buffett intrinsic value: Graham Number $8.69, margin of safety -130.5%
  - CANSLIM (O'Neil): 1/7 criteria met — C: N; A: N; N: N; S: Y; L: N; I: N; M: N
  - Dividend growth quality (if applicable): yield 518.6%, payout 19471%, quality score 35/100
  - Fama-French 5-factor tilts: Size: Large, Value tilt: Growth (descriptive only, not scored — see interpretation guide), Profitability: +38.3%, Asset growth: +7.9%
  - Quality Minus Junk (AQR-style): 76/100
  - Insider transactions (90d, cluster-buy check): 0 buy txns / 0 sell txns, 0 distinct buyers
  - Analyst estimate revision momentum: +4.1% (current vs 90 days ago)
  - 52-week high breakout (O'Neil/Darvas): -27.3% from 52-wk high
  - Interpretation guide: Magic Formula = Greenblatt cheapness+quality rank within
    the monitored universe; F-Score 8-9 strong / 0-2 weak (Piotroski); PEG <= 1
    attractive per Lynch GARP (ignore for cyclicals); 6-12 mo momentum is the
    Carhart UMD factor; quality gates are Buffett-style quantitative tells.
    Graham Number/margin of safety is asset-and-earnings based (1934-era value
    investing) — expect it to look deeply "overvalued" for asset-light,
    high-multiple growth/tech names; that's the methodology working as
    designed, not a flaw, and should be weighted down for this watchlist's
    growth names accordingly. CANSLIM (O'Neil) is a 7-criterion growth+
    breakout+market-regime checklist, not a continuous score — read the
    per-criterion breakdown, not just the count. Dividend quality only
    applies to actual payers (GAPPED for non-payers, not penalized). Fama-
    French Size/Value tilts are descriptive only and deliberately excluded
    from the conviction blend (a small-cap/cheap-book-to-market tilt would
    bias against this watchlist's mega-cap growth names) — Profitability/
    Investment legs are folded into Quality Minus Junk (AQR-style) instead.
    Insider signal only means something as a cluster (3+ distinct buyers,
    zero sales in 90 days per Lakonishok & Lee) — a single insider trade is
    noise. Analyst revision momentum compares current-quarter/next-year EPS
    estimates to 90 days ago; the 52-week breakout check is O'Neil/Darvas-
    style and distinct from the 3-month-high check in the momentum score above.

## Raw data fields (yfinance)
  - forwardPE: 29.880596
  - trailingPE: 36.4
  - enterpriseToEbitda: -3.016
  - enterpriseToRevenue: -0.814
  - pegRatio: 3.2516
  - freeCashflow: 159451873280
  - operatingCashflow: 250896007168
  - totalRevenue: 857830981632
  - revenueGrowth: 0.106
  - earningsGrowth: 0.11
  - grossMargins: 0.3829
  - operatingMargins: 0.23903999
  - profitMargins: 0.19414
  - ebitdaMargins: 0.26992
  - currentRatio: 6.893
  - totalCash: 753871028224
  - totalDebt: 0
  - returnOnEquity: 0.09352
  - returnOnAssets: 0.05703
  - beta: 0.945
  - targetMeanPrice: 23.33
  - currentPrice: 20.02
  - heldPercentInstitutions: 0.0023999999
  - numberOfAnalystOpinions: 2

## Recent news headlines
  - Jensen Huang Signed Toyota, Fanuc, Kioxia, and 5 Other Japanese Industrial Giants Into Nvidia's Physical AI Coalition This Week. Nvidia Has $1 Trillion in Confirmed Demand Through 2027. (2026-07-25)
  - Sony, Mitsubishi Join Forces to Capture Japan's Physical AI Opportunity (2026-07-22)
  - Nvidia (NVDA) Deepens Japan AI Push With Factory Deal And Robotics Tie Ups (2026-07-17)
  - Nvidia Expands AI Push in Japan (2026-07-16)
  - Nvidia expands AI and robotics collaboration with leading Japanese manufacturers (NVDA) (2026-07-16)

## Recent insider transactions
  - none available (treat as GAPPED)

## Depth enrichment (short interest, 13F flow, filings, options skew)
  - Institutional flow (13F deltas):
    - Top holders: 4 adding / 2 trimming this quarter
    - Aristotle Capital Management, LLC: 0.19% held, -2.2% q/q
    - Sterling Capital Management, LLC: 0.00% held, -26.7% q/q
    - Hantz Financial Services, Inc.                          : 0.00% held, +100.5% q/q
    - Kelleher Financial Advisors: 0.00% held, +2.6% q/q
    - PNC Financial Services Group, Inc.: 0.00% held, +7.4% q/q
    - L & S Advisors Inc: 0.00% held, +100.0% q/q

## Gapped data sources (penalize Confidence Score accordingly)
  - Congressional trades: Data Status: GAPPED
  - Earnings call transcripts: Data Status: GAPPED
  - Credit ratings: Data Status: GAPPED
  - Short interest trend: Data Status: GAPPED
  - SEC filing stream: Data Status: GAPPED
  - Options skew / flow: Data Status: GAPPED
  - debtToEquity: Data Status: GAPPED
  - recommendationMean: Data Status: GAPPED
