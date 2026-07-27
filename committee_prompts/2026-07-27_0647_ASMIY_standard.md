# COMMITTEE DATA PAYLOAD — ASMIY (Standard)
Generated: 2026-07-27 06:47 local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: Technology | Industry: Semiconductor Equipment & Materials
- Next earnings: in 1 day(s)

## Trigger(s) breached
- Earnings imminent: 1 day(s) out — pre-earnings committee review

## Prior ledger state
- Previous Overall Score: 62/110
- Previous Timing Score: 0/100
- Previous Confidence: 65%
- Previous evaluation date: 2026-07-24 12:46

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): 62/110 → local rating band: Watch
- Timing: 0/100
- Data-completeness confidence (proxy): 65%
- Category proxies (2/11 are ESTIMATES from missing data — weigh accordingly):
  - Valuation: 6/10
  - Cash Generation: 1/10
  - Growth: 4/10
  - Revenue Visibility: 5/10  [ESTIMATE — source data missing, do not trust]
  - Margin Quality: 10/10
  - Balance Sheet: 10/10
  - Capital Allocation: 7/10
  - Macro Exposure: 7/10
  - Competitive Moat: 6/10
  - Analyst Sentiment: 5/10  [ESTIMATE — source data missing, do not trust]
  - Technical Position: 1/10

## Earnings gate (actionable-BUY policy: earnings within 10 business days AND
## strict positivity pass — score >=70, >=3 signals, beat streak >=3/4. A Buy
## rating without this gate is thesis-only, NOT actionable; committee should
## confirm or veto the positivity call using transcript/guidance judgment)
  - Earnings in business days: 1 (buy window: ≤10)
  - Earnings Positivity Score: 40/100 (strict pass bar 70, beat streak 2/4 last quarters)
    - Analyst EPS revision momentum: GAPPED
    - Earnings surprise history: 20
    - Pre-earnings relative strength vs SPY: 80
    - Recommendation upgrades vs downgrades (90d): GAPPED
    - Short interest level & trend: GAPPED
  - GATE VERDICT: NOT ACTIONABLE — only 2/5 positivity signals available (need ≥3); positivity 40/100 below strict bar 70; beat streak 2/4 quarters (strict bar: ≥3/4)

## Supermajority consensus vote (last gate before a BUY alert)
  - Verdict: FAIL — 4/9 systems bullish (supermajority 65%, min 6 computable)
    - momentum_timing: ✘
    - factor_tier_high: ✘
    - piotroski: ✔
    - canslim: ✘
    - estimate_revisions: ✔
    - insider_signal: GAPPED
    - momentum_6m: ✔
    - breakout_52wk: ✘
    - positivity_margin: ✘
    - quality_gates: ✔
  - HARD VETO: hostile market regime: SPY>!50d/200d, VIX 17.8 (max 28.0), term 0.868
  - Market regime: SPY>!50d/200d, VIX 17.8 (max 28.0), term 0.868 — HOSTILE

## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
  - Magic Formula rank: #56 of 104 in universe (earnings yield 2.0%, return on capital 45.9%)
  - Piotroski F-Score: 8/9 (8-9 strong, 0-2 weak)
  - PEG (GARP): 1.88
  - Momentum: 6-mo +14.1%, 12-mo +85.7%
  - Quality gates (Buffett-style): ROE >= 15%: PASS; Debt/Equity < 0.5: PASS; Gross margin > 40%: PASS; CFO > Net Income: PASS
  - Graham/Buffett intrinsic value: Graham Number $227.17, margin of safety -323.1%
  - CANSLIM (O'Neil): 1/7 criteria met (2 gapped) — C: ?; A: ?; N: N; S: N; L: Y; I: N; M: N
  - Dividend growth quality (if applicable): yield 0.3%, payout 14%, quality score 80/100
  - Fama-French 5-factor tilts: Size: Large, Value tilt: Growth (descriptive only, not scored — see interpretation guide), Profitability: +51.8%, Asset growth: +3.4%
  - Quality Minus Junk (AQR-style): 59/100
  - Insider transactions (90d, cluster-buy check): 0 buy txns / 0 sell txns, 0 distinct buyers
  - Analyst estimate revision momentum: +16.4% (current vs 90 days ago)
  - 52-week high breakout (O'Neil/Darvas): -23.0% from 52-wk high
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
  - forwardPE: 27.982006
  - trailingPE: 41.82202
  - enterpriseToEbitda: 42.621
  - enterpriseToRevenue: 14.543
  - pegRatio: 1.88
  - freeCashflow: 59450000
  - operatingCashflow: 758200000
  - totalRevenue: 3196499968
  - revenueGrowth: 0.028
  - grossMargins: 0.51794
  - operatingMargins: 0.32243
  - profitMargins: 0.31006
  - ebitdaMargins: 0.34122002
  - debtToEquity: 1.679
  - currentRatio: 2.245
  - totalCash: 981600000
  - totalDebt: 72000000
  - returnOnEquity: 0.24936001
  - returnOnAssets: 0.10936
  - beta: 1.555
  - targetMeanPrice: 1420.0
  - currentPrice: 961.07
  - heldPercentInstitutions: 0.0053100004
  - numberOfAnalystOpinions: 1

## Recent news headlines
  - Chip Stocks Rise After Pause in Middle East Fighting (2026-07-27)
  - European Chip Stocks Rise After Pause in Mideast Fighting (2026-07-27)
  - ASML Posts Blockbuster Q2 Numbers and Raises Guidance. ASML Stock Still Has Room to Run. (2026-07-17)
  - European chip stocks fall after sharp U.S. peers’ selloff (2026-07-17)
  - European Chip Stocks Skid After SK Hynix Nasdaq Debut (2026-07-13)

## Recent insider transactions
  - none available (treat as GAPPED)

## Depth enrichment (short interest, 13F flow, filings, options skew)
  - Institutional flow (13F deltas):
    - Top holders: 4 adding / 2 trimming this quarter
    - Firsthand Capital Management, Inc.: 0.01% held, +100.0% q/q
    - Boston Common Asset Management, LLC: 0.01% held, -24.3% q/q
    - Hantz Financial Services, Inc.                          : 0.00% held, -97.0% q/q
    - PNC Financial Services Group, Inc.: 0.00% held, +166.0% q/q
    - Salomon & Ludwin, LLC: 0.00% held, +133.3% q/q
    - Rhumbline Advisers: 0.00% held, +5.5% q/q

## Gapped data sources (penalize Confidence Score accordingly)
  - Congressional trades: Data Status: GAPPED
  - Earnings call transcripts: Data Status: GAPPED
  - Credit ratings: Data Status: GAPPED
  - Short interest trend: Data Status: GAPPED
  - SEC filing stream: Data Status: GAPPED
  - Options skew / flow: Data Status: GAPPED
  - earningsGrowth: Data Status: GAPPED
  - recommendationMean: Data Status: GAPPED
