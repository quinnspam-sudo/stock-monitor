# COMMITTEE DATA PAYLOAD — TOELY (Standard)
Generated: 2026-07-23 07:46 local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: Technology | Industry: Semiconductor Equipment & Materials
- Next earnings: in 7 day(s)

## Trigger(s) breached
- Timing score Δ +20 (threshold ±15)

## Prior ledger state
- Previous Overall Score: 62/110
- Previous Timing Score: 35/100
- Previous Confidence: 57%
- Previous evaluation date: 2026-07-23 06:46

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): 64/110 → local rating band: Watch
- Timing: 55/100
- Data-completeness confidence (proxy): 57%
- Category proxies (4/11 are ESTIMATES from missing data — weigh accordingly):
  - Valuation: 5/10  [ESTIMATE — source data missing, do not trust]
  - Cash Generation: 3/10
  - Growth: 5/10
  - Revenue Visibility: 5/10  [ESTIMATE — source data missing, do not trust]
  - Margin Quality: 9/10
  - Balance Sheet: 5/10  [ESTIMATE — source data missing, do not trust]
  - Capital Allocation: 8/10
  - Macro Exposure: 8/10
  - Competitive Moat: 5/10
  - Analyst Sentiment: 5/10  [ESTIMATE — source data missing, do not trust]
  - Technical Position: 6/10

## Earnings gate (actionable-BUY policy: earnings within 10 business days AND
## strict positivity pass — score >=70, >=3 signals, beat streak >=3/4. A Buy
## rating without this gate is thesis-only, NOT actionable; committee should
## confirm or veto the positivity call using transcript/guidance judgment)
  - Earnings in business days: 5 (buy window: ≤10)
  - Earnings Positivity Score: 100/100 (strict pass bar 70, beat streak None/0 last quarters)
    - Analyst EPS revision momentum: GAPPED
    - Earnings surprise history: GAPPED
    - Pre-earnings relative strength vs SPY: 100
    - Recommendation upgrades vs downgrades (90d): GAPPED
    - Short interest level & trend: GAPPED
  - GATE VERDICT: NOT ACTIONABLE — only 1/5 positivity signals available (need ≥3); no reported-quarter history to verify beat streak

## Supermajority consensus vote (last gate before a BUY alert)
  - Verdict: FAIL — 3/8 systems bullish (supermajority 65%, min 6 computable)
    - momentum_timing: ✘
    - factor_tier_high: ✘
    - piotroski: ✘
    - canslim: ✘
    - estimate_revisions: GAPPED
    - insider_signal: GAPPED
    - momentum_6m: ✔
    - breakout_52wk: ✘
    - positivity_margin: ✔
    - quality_gates: ✔
  - HARD VETO: hostile market regime: SPY>!50d/200d, VIX 19.0 (max 28.0), term 0.911
  - Market regime: SPY>!50d/200d, VIX 19.0 (max 28.0), term 0.911 — HOSTILE

## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
  - Magic Formula rank: #84 of 103 in universe (earnings yield -195.2%, return on capital 35.8%)
  - Piotroski F-Score: 4/9 (1 tests gapped) (8-9 strong, 0-2 weak)
  - PEG (GARP): 2.22
  - Momentum: 6-mo +47.9%, 12-mo +107.4%
  - Quality gates (Buffett-style): ROE >= 15%: PASS; Debt/Equity < 0.5: GAPPED; Gross margin > 40%: PASS; CFO > Net Income: FAIL
  - Graham/Buffett intrinsic value: Graham Number $34.94, margin of safety -472.9%
  - CANSLIM (O'Neil): 3/7 criteria met — C: Y; A: Y; N: N; S: N; L: Y; I: N; M: N
  - Dividend growth quality (if applicable): yield 311.7%, payout 16312%, quality score 35/100
  - Fama-French 5-factor tilts: Size: Large, Value tilt: Growth (descriptive only, not scored — see interpretation guide), Profitability: +45.3%, Asset growth: +8.9%
  - Quality Minus Junk (AQR-style): 85/100
  - Insider transactions (90d, cluster-buy check): 0 buy txns / 0 sell txns, 0 distinct buyers
  - Analyst estimate revision momentum: GAPPED
  - 52-week high breakout (O'Neil/Darvas): -19.7% from 52-wk high
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
  - trailingPE: 51.994804
  - enterpriseToEbitda: -0.453
  - enterpriseToRevenue: -0.131
  - pegRatio: 2.2191
  - freeCashflow: 229108629504
  - operatingCashflow: 539731984384
  - totalRevenue: 2443533090816
  - revenueGrowth: 0.086
  - earningsGrowth: 0.505
  - grossMargins: 0.45339
  - operatingMargins: 0.2889
  - profitMargins: 0.23509
  - ebitdaMargins: 0.28904
  - currentRatio: 2.702
  - totalCash: 506250002432
  - totalDebt: 0
  - returnOnEquity: 0.2927
  - returnOnAssets: 0.14237
  - beta: 1.371
  - currentPrice: 200.18
  - heldPercentInstitutions: 0.00027000002

## Recent news headlines
  - European Indexes Fall as Tech Rally Falters (2026-07-22)
  - Tokyo Electron (TSE:8035) Could Be 10% Undervalued On Its AI Chip Demand Story (2026-07-18)
  - Nvidia and AMD Hit by AI Selloff (2026-07-17)
  - Nvidia, AMD, Mircon, TSMC Shares Sink as China Unveils Powerful New AI Model (2026-07-17)
  - Nvidia’s Huang Courts Japanese Suppliers With Kanda Pork Skewers (2026-07-16)

## Recent insider transactions
  - none available (treat as GAPPED)

## Depth enrichment (short interest, 13F flow, filings, options skew)
  - Institutional flow (13F deltas):
    - Top holders: 5 adding / 1 trimming this quarter
    - Hantz Financial Services, Inc.                          : 0.00% held, -97.9% q/q
    - Madison Asset Management, LLC: 0.00% held, +9.2% q/q
    - L & S Advisors Inc: 0.00% held, +100.0% q/q
    - Salomon & Ludwin, LLC: 0.00% held, +4.6% q/q
    - Rhumbline Advisers: 0.00% held, +6.2% q/q
    - Gamma Investing LLC: 0.00% held, +11.1% q/q
  - SEC filing stream:
    - 2026-07-07 F-6EF — Offering Registrations
    - 2023-04-05 F-6 POS — Offering Registrations
    - 2023-04-04 F-6 POS — Offering Registrations
    - 2023-03-31 F-6 POS — Offering Registrations
    - 2023-03-21 F-6 POS — Offering Registrations

## Gapped data sources (penalize Confidence Score accordingly)
  - Congressional trades: Data Status: GAPPED
  - Earnings call transcripts: Data Status: GAPPED
  - Credit ratings: Data Status: GAPPED
  - Short interest trend: Data Status: GAPPED
  - Options skew / flow: Data Status: GAPPED
  - forwardPE: Data Status: GAPPED
  - debtToEquity: Data Status: GAPPED
  - recommendationMean: Data Status: GAPPED
  - targetMeanPrice: Data Status: GAPPED
  - numberOfAnalystOpinions: Data Status: GAPPED
