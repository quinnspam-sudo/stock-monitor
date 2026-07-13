# EXIT-RULE BACKTEST — 2026-01-02 → 2026-07-13

Question: if every price-reconstructable BUY fire since Jan 2 was bought with
$10 (re-entering when the signal re-fired after an exit), which sell rule
leaves the most money vs putting the same $10s into SPY on the same dates?

| Exit rule | Buys | Sells | Return | SPY same windows | Edge |
|---|---|---|---|---|---|
| Never sell (buy & hold) | 317 | 0 | +20.4% | +9.3% | **+11.1pts** |
| -15% stop only | 370 | 132 | +15.1% | +9.0% | **+6.1pts** |
| 25% trailing stop only | 382 | 189 | +13.8% | +9.1% | +4.7pts |
| -15% stop + 25% trail (ADOPTED) | 407 | 234 | +12.4% | +9.0% | +3.5pts |
| 50-day-low breakdown | 434 | 289 | +10.6% | +9.0% | +1.6pts |
| 20% trailing stop | 446 | 306 | +9.8% | +9.0% | +0.8pts |
| -10% stop + 20% trail | 494 | 368 | +8.9% | +8.9% | +0.0pts |
| OLD RULES: -7% stop + Darvas 20d | 565 | 475 | +8.1% | +8.8% | -0.7pts |
| 3% below 50d SMA | 592 | 528 | +6.6% | +8.9% | -2.3pts |
| OLD RULES incl. +20% take-profit | 998 | 965 | +4.1% | +7.9% | -3.8pts |

Findings:
- ALL of the buy signal's alpha came from a few huge trends (ICHR +250%,
  UCTT +227%, STX/MU/WDC ~+190%). Any exit that reacts to a normal pullback
  (Darvas 20-day low, tight -7% stop, 50d SMA) sells those winners during
  shakeouts and re-buys higher on the next fire — erasing the edge entirely.
- The +20% take-profit was the single most destructive rule: caps every
  winner while the stop takes full losses. Both take-profit variants were
  the worst tested.
- Adopted: -15% stop + 25% trailing stop off the peak close since entry.
  Not the max-edge choice on this sample (-15% stop alone was), but the
  trailing stop is kept as disaster protection so a big winner can't round-
  trip to a loss — this window (mostly rising market) never tested that
  failure mode, and "no exit for winners" is the kind of rule that looks
  optimal right up until it isn't.

## Round 2 — multi-window + market-conditioned stops (same day, later session)

Re-ran over 5y / 1y / 6m windows, then tested conditioning the stops on
market health (SPY vs its own 50d SMA). Edge vs SPY-on-same-buy-dates:

| Sells fire…                       | 5y       | 1y       | 6m      |
|---|---|---|---|
| Always (stop15 + trail25)         | -37.5pts | +6.1pts  | +3.5pts |
| Only when SPY < 50d SMA           | -36.6pts | +6.1pts  | +2.3pts |
| **Only when SPY > 50d SMA (ADOPTED)** | **-25.0pts** | **+13.6pts** | **+9.9pts** |
| Never sell                        | +100.4pts* | +25.7pts | +11.1pts |
| Old rules (-7% + Darvas 20d)      | -49.7pts | -2.7pts  | -0.7pts |

*5y never-sell is survivorship-inflated (today's watchlist replayed over 5
years) — compare exit rows to each other, not to it.

Findings:
- Market-conditioned stops (fire only in a HEALTHY market) beat every other
  exit in every window. Mechanism: a stock down -15% while SPY is fine is an
  idiosyncratic problem — cut it; a stock down with the whole market usually
  recovers with it, and selling then is the sell-low/rebuy-high churn that
  made the 5y unconditioned number so bad (1,956 buys / 1,765 sells).
- The intuitive opposite ("sell only when the market is down") tested ≈ no
  better than unconditioned: it converts the stop into "sell near the
  bottom, after the damage."
- ADOPTED (sell_check.py): -15% stop and 25% trail active only while SPY >
  50d SMA; plus an UNconditional -30% disaster floor (costs ~nothing in
  sample, bounds the untested deep-bear scenario where "hold because
  everything is falling" keeps falling — the sample has 2022 but no 2008).

Caveats: price-only reconstruction of the buy logic (fundamental votes /
earnings gate not replayable), current-watchlist survivorship bias (severe
at 5y), and even conditioned exits lagged never-sell in-sample — the exits
buy drawdown protection, not extra return. Re-run after the next correction.
Sweep scripts preserved in research/ (sim_exits.py, sim_windows.py,
sim_regime_exits.py).


## Round 3 — robustness & live-formula validation (same day)

1. PARAMETER SENSITIVITY (is -15%/25% overfit?): grid stop {10,12.5,15,20}%
   x trail {20,25,30}%, market-conditioned, re-entry. 1y edges +7.2..+16.5pts,
   6m +8.0..+10.5pts — a smooth plateau, monotonically improving as rules
   loosen. The adopted point is mid-plateau, not a lucky spike. (Gradient
   direction consistent with never-sell being the in-sample ceiling.)
2. ACTUAL LIVE FORMULA replayed (monitor.py score_ticker >= 76 + consensus
   price votes + regime; RSI band, SMA20/50, 3-mo-high, volume ratio —
   everything but factor-conviction tiers, which need historical
   fundamentals): 1y +27.7pts never-sell / +15.2pts with frozen exits;
   6m +11.2 / +10.3. The live formula is MORE selective and tested STRONGER
   than the 6-vote proxy used to pick the exit rules.
3. Rules frozen; out-of-sample predictions pre-registered in
   EVALUATION_PROTOCOL.md, review 2026-10-13. Scripts: research/
   sim_sensitivity.py, research/sim_live_score.py.
