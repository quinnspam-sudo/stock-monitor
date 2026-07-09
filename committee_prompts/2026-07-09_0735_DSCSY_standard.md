# COMMITTEE DATA PAYLOAD — DSCSY (Standard)
Generated: 2026-07-09 07:35 local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: Technology | Industry: Semiconductor Equipment & Materials
- Next earnings: Data Status: GAPPED

## Trigger(s) breached
- Timing score Δ +15 (threshold ±15)

## Prior ledger state
- Previous Overall Score: 69/110
- Previous Timing Score: 20/100
- Previous Confidence: 57%
- Previous evaluation date: 2026-07-09 06:42

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): 71/110 → local rating band: Watch
- Timing: 35/100
- Data-completeness confidence (proxy): 57%
- Category proxies (4/11 are ESTIMATES from missing data — weigh accordingly):
  - Valuation: 5/10  [ESTIMATE — source data missing, do not trust]
  - Cash Generation: 6/10
  - Growth: 6/10
  - Revenue Visibility: 5/10  [ESTIMATE — source data missing, do not trust]
  - Margin Quality: 10/10
  - Balance Sheet: 5/10  [ESTIMATE — source data missing, do not trust]
  - Capital Allocation: 7/10
  - Macro Exposure: 10/10
  - Competitive Moat: 8/10
  - Analyst Sentiment: 5/10  [ESTIMATE — source data missing, do not trust]
  - Technical Position: 4/10

## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
  - Magic Formula rank: #77 of 90 in universe (earnings yield -77.8%, return on capital 32.8%)
  - Piotroski F-Score: 3/9 (1 tests gapped) (8-9 strong, 0-2 weak)
  - PEG (GARP): 2.19
  - Momentum: 6-mo +30.6%, 12-mo +59.1%
  - Quality gates (Buffett-style): ROE >= 15%: PASS; Debt/Equity < 0.5: GAPPED; Gross margin > 40%: PASS; CFO > Net Income: FAIL
  - Graham/Buffett intrinsic value: Graham Number $7.63, margin of safety -499.9%
  - CANSLIM (O'Neil): 3/7 criteria met — C: N; A: N; N: N; S: Y; L: Y; I: N; M: Y
  - Dividend growth quality (if applicable): yield 1180.7%, payout 65584%, quality score 35/100
  - Fama-French 5-factor tilts: Size: Large, Value tilt: Growth (descriptive only, not scored — see interpretation guide), Profitability: +70.1%, Asset growth: +13.7%
  - Quality Minus Junk (AQR-style): 93/100
  - Insider transactions (90d, cluster-buy check): 0 buy txns / 0 sell txns, 0 distinct buyers
  - Analyst estimate revision momentum: GAPPED
  - 52-week high breakout (O'Neil/Darvas): -21.1% from 52-wk high
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
  - trailingPE: 59.4026
  - enterpriseToEbitda: -1.196
  - enterpriseToRevenue: -0.545
  - pegRatio: 2.1915
  - freeCashflow: 74007371776
  - operatingCashflow: 133543002112
  - totalRevenue: 436888993792
  - revenueGrowth: 0.102
  - earningsGrowth: 0.111
  - grossMargins: 0.7015
  - operatingMargins: 0.4399
  - profitMargins: 0.3102
  - ebitdaMargins: 0.45512
  - currentRatio: 3.202
  - totalCash: 284575006720
  - totalDebt: 0
  - returnOnEquity: 0.25092
  - returnOnAssets: 0.16459
  - beta: 1.049
  - currentPrice: 45.74
  - heldPercentInstitutions: 0.00025

## Recent news headlines
  - A Look At Disco (TSE:6146) Valuation After Strong Recent Share Price Momentum (2026-06-09)
  - Is DISCO CORP (DSCSY) Stock Outpacing Its Industrial Products Peers This Year? (2026-05-08)
  - CS Disco, Inc. Q1 2026 Earnings Call Summary (2026-05-06)
  - DISCO CORP (DSCSY) Upgraded to Strong Buy: Here's Why (2026-04-23)
  - Are Industrial Products Stocks Lagging  Astec Industries (ASTE) This Year? (2026-04-22)

## Recent insider transactions
  - none available (treat as GAPPED)

## Gapped data sources (penalize Confidence Score accordingly)
  - Congressional trades: Data Status: GAPPED
  - Options skew / flow: Data Status: GAPPED
  - Institutional flow (13F deltas): Data Status: GAPPED
  - SEC filing stream: Data Status: GAPPED
  - Earnings call transcripts: Data Status: GAPPED
  - Credit ratings: Data Status: GAPPED
  - forwardPE: Data Status: GAPPED
  - debtToEquity: Data Status: GAPPED
  - recommendationMean: Data Status: GAPPED
  - targetMeanPrice: Data Status: GAPPED
  - numberOfAnalystOpinions: Data Status: GAPPED
