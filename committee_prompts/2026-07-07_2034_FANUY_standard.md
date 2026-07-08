# COMMITTEE DATA PAYLOAD — FANUY (Standard)
Generated: 2026-07-07 20:34 local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: Industrials | Industry: Specialty Industrial Machinery
- Next earnings: in 24 day(s)

## Trigger(s) breached
- Timing score Δ -30 (threshold ±15)

## Prior ledger state
- Previous Overall Score: 64/110
- Previous Timing Score: 50/100
- Previous Confidence: 67%
- Previous evaluation date: 2026-07-06 14:58

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): 62/110 → local rating band: Watch
- Timing: 20/100
- Data-completeness confidence (proxy): 67%
- Category proxies (2/11 are ESTIMATES from missing data — weigh accordingly):
  - Valuation: 6/10
  - Cash Generation: 6/10
  - Growth: 6/10
  - Revenue Visibility: 5/10  [ESTIMATE — source data missing, do not trust]
  - Margin Quality: 8/10
  - Balance Sheet: 5/10  [ESTIMATE — source data missing, do not trust]
  - Capital Allocation: 4/10
  - Macro Exposure: 10/10
  - Competitive Moat: 5/10
  - Analyst Sentiment: 5/10
  - Technical Position: 2/10

## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
  - Magic Formula rank: #31 of 37 in universe (earnings yield -26.4%, return on capital 11.1%)
  - Piotroski F-Score: 7/9 (1 tests gapped) (8-9 strong, 0-2 weak)
  - PEG (GARP): 3.58
  - Momentum: 6-mo +5.2%, 12-mo +66.4%
  - Quality gates (Buffett-style): ROE >= 15%: FAIL; Debt/Equity < 0.5: GAPPED; Gross margin > 40%: FAIL; CFO > Net Income: PASS
  - Interpretation guide: Magic Formula = Greenblatt cheapness+quality rank within
    the monitored universe; F-Score 8-9 strong / 0-2 weak (Piotroski); PEG <= 1
    attractive per Lynch GARP (ignore for cyclicals); 6-12 mo momentum is the
    Carhart UMD factor; quality gates are Buffett-style quantitative tells.

## Raw data fields (yfinance)
  - forwardPE: 31.940298
  - trailingPE: 38.90909
  - enterpriseToEbitda: -3.005
  - enterpriseToRevenue: -0.811
  - pegRatio: 3.5828
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
  - recommendationMean: 3.0
  - targetMeanPrice: 23.33
  - currentPrice: 21.4
  - heldPercentInstitutions: 0.00242
  - numberOfAnalystOpinions: 2

## Recent news headlines
  - AI’s Next Act Isn’t Chatbots. It’s Robots, and BOTZ Is the Bet (2026-07-06)
  - How Cognex Corporation’s (CGNX) Machine Vision Focus Keeps It Close to AI-Enabled Factory Automation (2026-07-06)
  - Why Robo Global Robotics & Automation ETF (ROBO) Is a Top ETF Buy for Robotics Investors (2026-06-24)
  - Japan's Nikkei Closes at Record High (2026-06-22)
  - Are Industrial Products Stocks Lagging  Fanuc (FANUY) This Year? (2026-06-09)

## Recent insider transactions
  - none available (treat as GAPPED)

## Gapped data sources (penalize Confidence Score accordingly)
  - Congressional trades: Data Status: GAPPED
  - Options skew / flow: Data Status: GAPPED
  - Institutional flow (13F deltas): Data Status: GAPPED
  - SEC filing stream: Data Status: GAPPED
  - Earnings call transcripts: Data Status: GAPPED
  - Credit ratings: Data Status: GAPPED
  - debtToEquity: Data Status: GAPPED
