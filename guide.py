"""Post the Discord field guide: every output type, what it means, what to do.

Run after changing any output format: ./venv/bin/python guide.py
Tip: pin the resulting messages in your Discord channel.
"""
from notify import send_message

GUIDE = """\
📖 **STOCK-MONITOR FIELD GUIDE** — every alert type, what it means, what to do
*(pin this message · reposted whenever outputs change)*

━━━━━━━━━━━━━━━━━━
🟢 **BUY ALERT** (green card with a ticker + score)
**Means:** a watchlist stock crossed the momentum threshold (75/100) — trend, volume, and relative strength are aligned. The card now includes a **Factor conviction** line (HIGH/MEDIUM/LOW) blending Magic Formula rank, Piotroski F-Score, quality gates, and momentum.
**Do:** execute the card's **Mechanical action** line — buy the fixed dollar amount (config `buy_amount_usd`), every alert, equal size, then log it in #buy-log. The Jan-Jul backtests showed the alpha lives in a few huge outliers (median alert ≈ 0): picking among alerts is how the edge dies. Committee judgment belongs upstream — deciding what's ON the watchlist — not vetoing individual alerts. If the total dollar flow is too high, lower `buy_amount_usd` or raise `alert_threshold`; don't skip alerts.

📋 **COMMITTEE PAYLOAD(S) READY**
**Means:** something *thesis-relevant* changed — score moved ≥8/110, timing ≥15, rating band crossed, Top-5 rank shifted, or a first evaluation. This is the system's core signal; it fires rarely by design.
**Do:** open the note in Obsidian → `Stock Monitor/Committee Payloads`, paste into your Claude Pro committee session, read the Template A verdict, then log it: `verdict.py add TICKER RATING`.

⏱️ **INTRADAY PULSE BREACH** (hourly window only)
**Means:** a holding moved ±3% or is trading ≥2x normal volume pace. This is a *smoke detector*, not a signal — most breaches are noise.
**Do:** scan headlines for the ticker. Only escalate (pull the payload, run the committee) if there's real news. Do not sell into an intraday move.

🔔 **CLOSING BELL SUMMARY** (13:35 PT daily)
**Means:** the day is archived — score gainers/losers, rating changes, market regime.
**Do:** low urgency. Review tonight or pre-market. Only names with **rating changes** deserve action; everything else is record-keeping.

📊 **WEEKLY REVIEW** (Friday close)
**Means:** verdict-journal scorecard — how past committee calls performed vs SPY.
**Do:** read for calibration. If buy-side verdicts consistently lag SPY, tighten the threshold or revisit the committee prompt — this is the system's feedback loop.

📉 **WEEKLY BACKTEST** (Saturday morning)
**Means:** checks the *local scoring engine's* calls (not committee verdicts — that's Weekly Review) against what each ticker actually did over the Mon-Fri just finished. Reports return/hit-rate/beat-SPY-rate by rating bucket, plus whether top-half-scored names actually outperformed bottom-half ones — the core "is the score itself meaningful" check.
**Do:** read for calibration on the scoring engine, not individual trades. If "signal failed" recurs for several weeks running, the momentum/factor weights need revisiting, not just that week's picks.

━━━━━━━━━━━━━━━━━━
🔴 **SELL SIGNAL** (posts to the separate #sell-alerts channel — hourly, market hours)
**Means:** one of three mechanical exit rules fired against a *real open position* (something you actually logged as bought via #buy-log and haven't fully sold yet — not the whole watchlist, and not a committee verdict either):
  - **STOP_LOSS** — down 15%+ from your average cost *while SPY is above its 50-day average*. The market is fine and your stock isn't — that's an idiosyncratic problem, cut it. When SPY is below its 50-day (market-wide drawdown), this stop and TRAIL_STOP are suspended: selling with the whole market tested as sell-low/rebuy-high churn.
  - **TRAIL_STOP** — closed 25%+ below its peak close since entry, in a healthy market. The winner has rolled over; take it. (These two replaced the old -7% stop / TAKE_PROFIT / BOX_BREAKDOWN rules, all of which tested worse than holding SPY — see the 2026-07-13 exit-rule backtest.)
  - **DISASTER_STOP** — down 30%+ from average cost, fires no matter what the market is doing. The unconditional floor under "hold through the drawdown." No thesis survives -30%.
  - **REBALANCE_DUE** — held 365+ days. Magic Formula's mechanical annual rotation, regardless of current conviction — this one fires on time elapsed, not price action.
**Do:** STOP_LOSS is the one rule in this whole system meant to be followed mechanically, not judged — that's the point of a stop-loss. The others are decision inputs, same as everything else here: read, don't auto-execute. Note this only covers real positions logged via #buy-log — it has no visibility into anything you hold that was never logged there, and it deliberately ignores committee verdicts/BUY alerts (those are recommendations, not confirmed positions).

━━━━━━━━━━━━━━━━━━
📝 **BUY-LOG CHANNEL** (#buy-log — message it directly, checked every 15 min)
**Means:** type `Bought $<amount> of <TICKER> at $<price>` or `Sold $<amount> of <TICKER> at $<price>` (e.g. `Bought $20 of NVDA at $374`) and it's recorded into the *actual trades* ledger — separate from anything the system recommends — automatically visible to sell-signal checks and `performance.py actual`. Needs the actual ticker symbol, not a company name — a ✅ reply + reaction confirms exactly what was recorded; a ❌ means it didn't parse (format hint included) or the ticker didn't resolve.
**Do:** double-check the ✅ confirmation matches what you meant to log — this is the one input in the whole system that's you typing a trade in free text, so it's worth a glance before trusting it silently. Use `performance.py recommendations` vs `performance.py actual` (or just ask Claude) to compare what the system suggested against what you actually did.

━━━━━━━━━━━━━━━━━━
**House rules:** the system *recommends only* — every trade goes through you. One alert = information; committee verdict = decision input; your judgment = final. Alerts are noise-gated: silence is normal and good."""

if __name__ == "__main__":
    send_message(GUIDE, kind="GUIDE", mention=False)
    print("Field guide posted to Discord (pin it in the channel).")
