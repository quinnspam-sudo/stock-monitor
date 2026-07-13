# EVALUATION PROTOCOL — rules freeze & out-of-sample test

**Status: RULES FROZEN as of 2026-07-13.** No parameter, threshold, or rule
changes until the review date below, except to fix outright bugs (a rule not
doing what its code comment says) — never to improve backtested performance.

## Why this exists

Every rule in the current system was chosen or retuned on 2026-07-13 using
historical data through that same date (see committee_prompts/
2026-07-13_EXIT_RULES_BACKTEST.md). That makes ALL current performance
numbers in-sample. Re-tuning again on the same data can only increase
overfit. The only way to learn whether the system actually works is to run
it unchanged and compare live results to what the backtest predicts.

Mitigating evidence already in hand (why the frozen rules are a reasonable
bet, not why they're proven):
- Parameter sensitivity: the -15% stop / 25% trail sits on a smooth plateau
  (every neighbor in a stop {10,12.5,15,20} x trail {20,25,30} grid was
  +7..+16pts vs SPY over 1y) — the choice is not a lone lucky spike.
- The ACTUAL live formula (score>=76 + consensus + regime), replayed on
  prices, tested stronger than the proxy used for rule selection: +15.2pts
  vs SPY over 1y and +10.3pts over 6m with the frozen exits.

## Pre-registered predictions (written BEFORE the data)

Over the evaluation window, with the mechanical policy followed ($10 per
alert, every alert, sells per sell_check.py):

1. The machine book (signals.json, all buy_alerts) beats SPY-on-same-dates
   on average alpha.
2. Positions exited by market-conditioned stops underperform, from their
   exit date, the positions that were held (i.e. the stops cut the right
   names).
3. The committee's approve/reject split (signal_tracker report) shows
   APPROVED alpha <= ALL-MACHINE alpha + noise (i.e. per-alert human
   filtering does NOT add value; if this is wrong, re-empower the committee
   per-alert).
4. Earnings-gate-open alerts do NOT meaningfully outperform gate-closed
   alerts (if wrong, re-promote the gate to suppressor).

## Review: 2026-10-13 (3 months) — grade each prediction

- Data: `./venv/bin/python signal_tracker.py report --days 92`
  plus the weekly adherence sections (execution % matters: below ~80%
  adherence the test is void — it measured the operator, not the system).
- If 1 holds: keep running, extend freeze 3 more months for a bigger n.
- If 1 fails: the honest conclusions are (a) the edge was in-sample fiction,
  or (b) regime changed. Either way the answer is NOT re-tuning exits on the
  same window — it is deciding whether to keep the strategy at all.
- 2/3/4 adjust their specific rule only, with the change and its rationale
  appended here.

## Amendment log

- 2026-07-13: protocol created; rules frozen (entry: score>=76 + consensus +
  regime, cooldown 24h; exits: -15% stop & 25% trail while SPY>50d SMA, -30%
  unconditional floor, 365d rebalance; sizing: buy_amount_usd equal-weight).
