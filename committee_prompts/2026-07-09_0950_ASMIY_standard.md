# COMMITTEE DATA PAYLOAD — ASMIY (Standard)
Generated: 2026-07-09 09:50 local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: Technology | Industry: Semiconductor Equipment & Materials
- Next earnings: in -79 day(s)

## Trigger(s) breached
- Timing score Δ -22 (threshold ±15)

## Prior ledger state
- Previous Overall Score: 70/110
- Previous Timing Score: 63/100
- Previous Confidence: 67%
- Previous evaluation date: 2026-07-09 08:50

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): 68/110 → local rating band: Watch
- Timing: 41/100
- Data-completeness confidence (proxy): 67%
- Category proxies (1/11 are ESTIMATES from missing data — weigh accordingly):
  - Valuation: 6/10
  - Cash Generation: 1/10
  - Growth: 4/10
  - Revenue Visibility: 5/10  [ESTIMATE — source data missing, do not trust]
  - Margin Quality: 10/10
  - Balance Sheet: 10/10
  - Capital Allocation: 7/10
  - Macro Exposure: 7/10
  - Competitive Moat: 6/10
  - Analyst Sentiment: 8/10
  - Technical Position: 4/10

## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
  - Magic Formula rank: #52 of 93 in universe (earnings yield 1.9%, return on capital 45.9%)
  - Piotroski F-Score: 8/9 (8-9 strong, 0-2 weak)
  - PEG (GARP): 1.99
  - Momentum: 6-mo +43.5%, 12-mo +75.0%
  - Quality gates (Buffett-style): ROE >= 15%: PASS; Debt/Equity < 0.5: PASS; Gross margin > 40%: PASS; CFO > Net Income: PASS
  - Graham/Buffett intrinsic value: Graham Number $227.80, margin of safety -361.4%
  - CANSLIM (O'Neil): 3/7 criteria met (2 gapped) — C: ?; A: ?; N: N; S: Y; L: Y; I: N; M: Y
  - Dividend growth quality (if applicable): yield 0.3%, payout 14%, quality score 80/100
  - Fama-French 5-factor tilts: Size: Large, Value tilt: Growth (descriptive only, not scored — see interpretation guide), Profitability: +51.8%, Asset growth: +3.4%
  - Quality Minus Junk (AQR-style): 59/100
  - Insider transactions (90d, cluster-buy check): 0 buy txns / 0 sell txns, 0 distinct buyers
  - Analyst estimate revision momentum: +16.4% (current vs 90 days ago)
  - 52-week high breakout (O'Neil/Darvas): -15.8% from 52-wk high
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
  - forwardPE: 30.60036
  - trailingPE: 45.71553
  - enterpriseToEbitda: 44.961
  - enterpriseToRevenue: 15.341
  - pegRatio: 1.9852
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
  - recommendationMean: 2.0
  - targetMeanPrice: 1420.0
  - currentPrice: 1051.0
  - heldPercentInstitutions: 0.0053899996
  - numberOfAnalystOpinions: 1

## Recent news headlines
  - 📉Global AI Stocks Tumble (2026-07-07)
  - ASM International (ENXTAM:ASM) Names CFO Pick On A Valuation Story Near Fair Value (2026-07-07)
  - European Indexes Edge Higher at Open (2026-07-06)
  - ASM International names KPN's Chris Figee as new CFO (2026-07-06)
  - ASM International (ASMIY) Upgraded to Buy: What Does It Mean for the Stock? (2026-07-01)

## Recent insider transactions
  - none available (treat as GAPPED)

## Gapped data sources (penalize Confidence Score accordingly)
  - Congressional trades: Data Status: GAPPED
  - Options skew / flow: Data Status: GAPPED
  - Institutional flow (13F deltas): Data Status: GAPPED
  - SEC filing stream: Data Status: GAPPED
  - Earnings call transcripts: Data Status: GAPPED
  - Credit ratings: Data Status: GAPPED
  - earningsGrowth: Data Status: GAPPED
