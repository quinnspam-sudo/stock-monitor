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
**Do:** HIGH/MEDIUM → paste the ticker's committee payload into Claude Pro and get a verdict before any trade. LOW → treat as watch-only; momentum without factor support is the weakest signal. Never trade off the card alone.

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
**Means:** one of three mechanical exit rules fired against a *recorded verdict* (something you logged with `verdict.py add`, not the whole watchlist):
  - **STOP_LOSS** — down 7%+ from your recorded entry. CANSLIM's signature rule: cut every loss at -7% to -8%, no exceptions, no "it'll come back."
  - **TAKE_PROFIT** — up 20%+ from entry. CANSLIM's "sell into strength" rule for a normal (non-explosive) mover — a nudge to consider trimming, not a hard rule like the stop-loss.
  - **BOX_BREAKDOWN** — price broke below its trailing 20-day low on above-average volume. The sell-side mirror of the breakout buy signal (Darvas box theory).
  - **REBALANCE_DUE** — held 365+ days. Magic Formula's mechanical annual rotation, regardless of current conviction — this one fires on time elapsed, not price action.
**Do:** STOP_LOSS is the one rule in this whole system meant to be followed mechanically, not judged — that's the point of a stop-loss. The others are decision inputs, same as everything else here: read, don't auto-execute. Note this only covers positions you've recorded a verdict for; it has no visibility into anything you hold that was never logged.

━━━━━━━━━━━━━━━━━━
📝 **BUY-LOG CHANNEL** (#buy-log — message it directly, checked every 15 min)
**Means:** type `Bought $<amount> of <TICKER> at $<price>` (e.g. `Bought $20 of NVDA at $374`) and it's recorded the same as `verdict.py add` — automatically visible to sell-signal checks, the weekly review, and `verdict.py review`. Needs the actual ticker symbol, not a company name — a ✅ reply + reaction confirms exactly what was recorded; a ❌ means it didn't parse (format hint included) or the ticker didn't resolve.
**Do:** double-check the ✅ confirmation matches what you meant to log — this is the one input in the whole system that's you typing a trade in free text, so it's worth a glance before trusting it silently.

━━━━━━━━━━━━━━━━━━
**House rules:** the system *recommends only* — every trade goes through you. One alert = information; committee verdict = decision input; your judgment = final. Alerts are noise-gated: silence is normal and good."""

if __name__ == "__main__":
    send_message(GUIDE, kind="GUIDE", mention=False)
    print("Field guide posted to Discord (pin it in the channel).")
