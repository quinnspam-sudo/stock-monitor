# COMMITTEE DATA PAYLOAD — OMRNY (Standard)
Generated: 2026-07-09 13:03 local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: Technology | Industry: Electronic Components
- Next earnings: Data Status: GAPPED

## Trigger(s) breached
- Timing score Δ +26 (threshold ±15)
- Rating change: Hold → Watch

## Prior ledger state
- Previous Overall Score: 57/110
- Previous Timing Score: 30/100
- Previous Confidence: 62%
- Previous evaluation date: 2026-07-08 17:08

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): 60/110 → local rating band: Watch
- Timing: 56/100
- Data-completeness confidence (proxy): 62%
- Category proxies (3/11 are ESTIMATES from missing data — weigh accordingly):
  - Valuation: 8/10
  - Cash Generation: 1/10
  - Growth: 5/10  [ESTIMATE — source data missing, do not trust]
  - Revenue Visibility: 5/10  [ESTIMATE — source data missing, do not trust]
  - Margin Quality: 4/10
  - Balance Sheet: 9/10
  - Capital Allocation: 3/10
  - Macro Exposure: 9/10
  - Competitive Moat: 5/10
  - Analyst Sentiment: 5/10  [ESTIMATE — source data missing, do not trust]
  - Technical Position: 6/10

## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
  - Magic Formula rank: #33 of 90 in universe (earnings yield 22.4%, return on capital 12.2%)
  - Piotroski F-Score: 6/9 (8-9 strong, 0-2 weak)
  - PEG (GARP): 1.58
  - Momentum: 6-mo +42.4%, 12-mo +38.1%
  - Quality gates (Buffett-style): ROE >= 15%: FAIL; Debt/Equity < 0.5: PASS; Gross margin > 40%: PASS; CFO > Net Income: PASS
  - Graham/Buffett intrinsic value: Graham Number $25.27, margin of safety -44.2%
  - CANSLIM (O'Neil): 2/7 criteria met (2 gapped) — C: ?; A: ?; N: N; S: N; L: Y; I: N; M: Y
  - Dividend growth quality (if applicable): yield 296.4%, payout 9630%, quality score 35/100
  - Fama-French 5-factor tilts: Size: Mid, Value tilt: Value (descriptive only, not scored — see interpretation guide), Profitability: +45.7%, Asset growth: +11.3%
  - Quality Minus Junk (AQR-style): 81/100
  - Insider transactions (90d, cluster-buy check): 0 buy txns / 0 sell txns, 0 distinct buyers
  - Analyst estimate revision momentum: -2.7% (current vs 90 days ago)
  - 52-week high breakout (O'Neil/Darvas): -10.6% from 52-wk high
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
  - forwardPE: 20.466293
  - trailingPE: 33.73148
  - enterpriseToEbitda: 2.628
  - enterpriseToRevenue: 0.321
  - pegRatio: 1.5813
  - freeCashflow: -65165623296
  - operatingCashflow: 60919001088
  - totalRevenue: 767350996992
  - grossMargins: 0.45742
  - operatingMargins: 0.07811
  - profitMargins: 0.03712
  - ebitdaMargins: 0.12213001
  - debtToEquity: 24.107
  - currentRatio: 1.826
  - totalCash: 166541000704
  - totalDebt: 241208999936
  - returnOnEquity: 0.03822
  - returnOnAssets: 0.026029998
  - beta: 1.139
  - targetMeanPrice: 45.110035
  - currentPrice: 36.43
  - heldPercentInstitutions: 4.0000003e-05
  - numberOfAnalystOpinions: 1

## Recent news headlines
  - Omron Robotics and Italy's Comau partner to expand industrial automation (2026-05-11)
  - OMRNY vs. VPG: Which Stock Is the Better Value Option? (2026-04-10)
  - Carlyle (CG) Stock Is Up, What You Need To Know (2026-03-30)
  - OMRNY or VPG: Which Is the Better Value Stock Right Now? (2026-03-25)
  - Omron (OMRNY) May Find a Bottom Soon, Here's Why You Should Buy the Stock Now (2026-03-10)

## Recent insider transactions
  - none available (treat as GAPPED)

## Gapped data sources (penalize Confidence Score accordingly)
  - Congressional trades: Data Status: GAPPED
  - Options skew / flow: Data Status: GAPPED
  - Institutional flow (13F deltas): Data Status: GAPPED
  - SEC filing stream: Data Status: GAPPED
  - Earnings call transcripts: Data Status: GAPPED
  - Credit ratings: Data Status: GAPPED
  - revenueGrowth: Data Status: GAPPED
  - earningsGrowth: Data Status: GAPPED
  - recommendationMean: Data Status: GAPPED
