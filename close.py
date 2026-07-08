"""Template D generator — Daily Closing Bell Summary payload.

Reads today's entries in history.json (written by monitor.py runs throughout the
day), computes first-vs-last score movement per ticker, rating-band crossings,
and a market regime wrap, then writes a Template D payload to committee_prompts/.

Run: ./venv/bin/python close.py [--quiet-discord]
"""
import json
import sys
from datetime import datetime

from notify import load_config, send_message
from collections import Counter

from committee import PROMPTS_DIR, HISTORY_PATH, market_open_today, load_ledger, thematic_concentration
from pulse import market_snapshot


def main():
    if "--force" not in sys.argv and not market_open_today():
        print("Market closed today — skipping close summary. Use --force to override.")
        return
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    hist = json.loads(HISTORY_PATH.read_text()) if HISTORY_PATH.exists() else {}
    today = hist.get(day, {})
    if not today:
        print(f"No monitor runs recorded today ({day}) — run monitor.py first.")
        return

    moves, rating_shifts, closing = [], [], []
    for ticker, runs in sorted(today.items()):
        first, last = runs[0], runs[-1]
        delta = last["overall"] - first["overall"]
        moves.append((ticker, delta, first, last))
        closing.append(f"{ticker}: {last['overall']}/110 ({last['rating']}) | timing {last['timing']}/100")
        if first["rating"] != last["rating"]:
            rating_shifts.append(f"{ticker}: {first['rating']} → {last['rating']}")

    moves.sort(key=lambda m: -m[1])
    gainers = [f"{t} | {l['overall']}/110 | Δ{d:+d} intraday" for t, d, f, l in moves if d > 0][:3]
    losers = [f"{t} | {l['overall']}/110 | Δ{d:+d} intraday" for t, d, f, l in reversed(moves) if d < 0][:3]

    ledger = load_ledger()
    sectors = Counter(v.get("sector", "Unknown") for v in ledger.values())
    total = sum(sectors.values()) or 1
    sector_lines = [f"{s}: {n} name(s) ({n / total:.0%} of watchlist)"
                    for s, n in sectors.most_common()]
    theme_lines = thematic_concentration(load_config())

    PROMPTS_DIR.mkdir(exist_ok=True)
    path = PROMPTS_DIR / f"{day}_CLOSE_templateD.md"

    def block(items, empty):
        return "\n".join(f"  - {i}" for i in items) if items else f"  - {empty}"

    path.write_text(f"""# COMMITTEE DATA PAYLOAD — DAILY CLOSING BELL (Template D)
Generated: {now:%Y-%m-%d %H:%M} local | Source: stock-monitor close daemon
Instructions: Paste into the Investment Committee session. Output Template D only.

## Market Close Date
{day}

## Score increases (local proxy, first vs last run today)
{block(gainers, 'No score increases today.')}

## Score decreases (local proxy, first vs last run today)
{block(losers, 'No score decreases today.')}

## Rating-band crossings today
{block(rating_shifts, 'No rating changes.')}

## Closing scoreboard
{block(closing, 'n/a')}

## Watchlist sector concentration (Risk Manager input)
{block(sector_lines, 'unavailable')}

## Watchlist thematic concentration (user-defined groupings, Risk Manager input)
{block(theme_lines, 'unavailable')}

## Market Regime Snapshot (raw)
{block(market_snapshot(), 'unavailable')}

## Gapped daily sources
  - ETF flow data: Data Status: GAPPED
  - Macro release calendar detail: Data Status: GAPPED
""")
    import obsidian
    obsidian.mirror_payload(path)
    print(f"Close payload: {path.name}")

    if "--quiet-discord" not in sys.argv:
        try:
            send_message(f"🔔 **Closing bell summary ready** — `{path.name}`\n"
                         + (f"Rating changes: {', '.join(rating_shifts)}" if rating_shifts
                            else "No rating changes today.")
                         + "\n**→ Do this:** end-of-day review, no urgency. Paste the payload into "
                         "Claude Pro tonight or tomorrow pre-market for the Template D wrap. "
                         "Act only on names with rating changes.", kind="CLOSE")
        except Exception as e:
            print(f"Discord notice failed: {e}")


if __name__ == "__main__":
    main()
    import notify
    if notify.had_failures():
        print(f"{len(notify.FAILURES)} Discord post(s) failed this run — failing job so CI surfaces it.")
        sys.exit(1)
