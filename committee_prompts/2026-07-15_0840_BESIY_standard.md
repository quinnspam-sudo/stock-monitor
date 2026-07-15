# COMMITTEE DATA PAYLOAD — BESIY (Standard)
Generated: 2026-07-15 08:40 local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: Technology | Industry: Semiconductor Equipment & Materials
- Next earnings: Data Status: GAPPED

## Trigger(s) breached
- Rating change: Buy → Watch

## Prior ledger state
- Previous Overall Score: 75/110
- Previous Timing Score: 23/100
- Previous Confidence: 59%
- Previous evaluation date: 2026-07-15 07:42

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): 74/110 → local rating band: Watch
- Timing: 9/100
- Data-completeness confidence (proxy): 59%
- Category proxies (3/11 are ESTIMATES from missing data — weigh accordingly):
  - Valuation: 5/10  [ESTIMATE — source data missing, do not trust]
  - Cash Generation: 8/10
  - Growth: 10/10
  - Revenue Visibility: 5/10  [ESTIMATE — source data missing, do not trust]
  - Margin Quality: 10/10
  - Balance Sheet: 6/10
  - Capital Allocation: 8/10
  - Macro Exposure: 8/10
  - Competitive Moat: 8/10
  - Analyst Sentiment: 5/10  [ESTIMATE — source data missing, do not trust]
  - Technical Position: 1/10

## Earnings gate (actionable-BUY policy: earnings within 10 business days AND
## strict positivity pass — score >=70, >=3 signals, beat streak >=3/4. A Buy
## rating without this gate is thesis-only, NOT actionable; committee should
## confirm or veto the positivity call using transcript/guidance judgment)
  - Earnings in business days: GAPPED (buy window: ≤10)
  - Earnings Positivity Score: 34/100 (strict pass bar 70, beat streak 1/4 last quarters)
    - Analyst EPS revision momentum: GAPPED
    - Earnings surprise history: 2
    - Pre-earnings relative strength vs SPY: 97
    - Recommendation upgrades vs downgrades (90d): GAPPED
    - Short interest level & trend: GAPPED
  - GATE VERDICT: NOT ACTIONABLE — no confirmed upcoming earnings date; only 2/5 positivity signals available (need ≥3); positivity 34/100 below strict bar 70; beat streak 1/4 quarters (strict bar: ≥3/4)

## Supermajority consensus vote (last gate before a BUY alert)
  - Verdict: FAIL — 2/8 systems bullish (supermajority 65%, min 6 computable)
    - momentum_timing: ✘
    - factor_tier_high: ✘
    - piotroski: ✘
    - canslim: ✘
    - estimate_revisions: GAPPED
    - insider_signal: GAPPED
    - momentum_6m: ✔
    - breakout_52wk: ✘
    - positivity_margin: ✘
    - quality_gates: ✔
  - Market regime: SPY>50d/200d, VIX 16.3 (max 28.0), term 0.846 — OK

## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
  - Magic Formula rank: #91 of 118 in universe (earnings yield 0.8%, return on capital 23.2%)
  - Piotroski F-Score: 5/9 (8-9 strong, 0-2 weak)
  - PEG (GARP): 1.45
  - Momentum: 6-mo +45.8%, 12-mo +89.6%
  - Quality gates (Buffett-style): ROE >= 15%: PASS; Debt/Equity < 0.5: FAIL; Gross margin > 40%: PASS; CFO > Net Income: PASS
  - Graham/Buffett intrinsic value: Graham Number $17.92, margin of safety -1452.8%
  - CANSLIM (O'Neil): 4/7 criteria met — C: Y; A: Y; N: N; S: N; L: Y; I: N; M: Y
  - Dividend growth quality (if applicable): yield 0.6%, payout 73%, quality score 50/100
  - Fama-French 5-factor tilts: Size: Large, Value tilt: Growth (descriptive only, not scored — see interpretation guide), Profitability: +63.3%, Asset growth: -9.8%
  - Quality Minus Junk (AQR-style): 48/100
  - Insider transactions (90d, cluster-buy check): 0 buy txns / 0 sell txns, 0 distinct buyers
  - Analyst estimate revision momentum: GAPPED
  - 52-week high breakout (O'Neil/Darvas): -25.7% from 52-wk high
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
  - trailingPE: 128.21198
  - enterpriseToEbitda: 107.914
  - enterpriseToRevenue: 35.647
  - pegRatio: 1.451
  - freeCashflow: 151480624
  - operatingCashflow: 226720992
  - totalRevenue: 632065024
  - revenueGrowth: 0.283
  - earningsGrowth: 0.635
  - grossMargins: 0.63273
  - operatingMargins: 0.34577
  - profitMargins: 0.24002
  - ebitdaMargins: 0.33033
  - debtToEquity: 113.605
  - currentRatio: 4.735
  - totalCash: 611438016
  - totalDebt: 519112992
  - returnOnEquity: 0.3127
  - returnOnAssets: 0.10138
  - beta: 1.375
  - currentPrice: 278.22
  - heldPercentInstitutions: 3.0000001e-05

## Recent news headlines
  - How BE Semiconductor Industries (BESIY) Is Turning Hybrid Bonding Demand Into a Bigger AI Packaging Growth Target (2026-06-23)
  - BESI raises long-term revenue, margin targets as demand increases (2026-06-18)
  - BE Semiconductor Raises Long-Term Revenue, Profitability Targets on AI Boost (2026-06-18)
  - Ultra Clean (UCTT) Surges 6.5%: Is This an Indication of Further Gains? (2026-06-03)
  - European Stocks Tracking Lower in Friday Trading; Lack of US-China Trade Deal Hits Tech Shares (2026-05-15)

## Recent insider transactions
  - none available (treat as GAPPED)

## Depth enrichment (short interest, 13F flow, filings, options skew)
  - Short interest trend:
    - Shares short 320,002 vs 319,138 prior month (+0.3% — flat)
  - Institutional flow (13F deltas):
    - Top holders: 3 adding / 0 trimming this quarter
    - Salomon & Ludwin, LLC: 0.00% held, +204.3% q/q
    - Rhumbline Advisers: 0.00% held, +28.5% q/q
    - Gamma Investing LLC: 0.00% held, +763.6% q/q

## Gapped data sources (penalize Confidence Score accordingly)
  - Congressional trades: Data Status: GAPPED
  - Earnings call transcripts: Data Status: GAPPED
  - Credit ratings: Data Status: GAPPED
  - SEC filing stream: Data Status: GAPPED
  - Options skew / flow: Data Status: GAPPED
  - forwardPE: Data Status: GAPPED
  - recommendationMean: Data Status: GAPPED
  - targetMeanPrice: Data Status: GAPPED
  - numberOfAnalystOpinions: Data Status: GAPPED
