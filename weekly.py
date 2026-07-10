"""Weekly performance review payload — Friday post-close.

Assembles the week's verdict performance (vs SPY), current ledger scoreboard, and
sector concentration into a review payload for the committee's Portfolio Manager
and Risk Manager to critique. This is the PDF's "weekly performance review
comparing recommendations against actual outcomes."

Run: ./venv/bin/python weekly.py [--quiet-discord]
"""
import json
import sys
from collections import Counter
from datetime import datetime

import yfinance as yf

import alert_stats
from notify import send_message, load_config
from committee import PROMPTS_DIR, load_ledger, market_open_today, thematic_concentration
from verdict import load as load_verdicts


def main():
    now = datetime.now()
    if "--force" not in sys.argv and now.weekday() != 4:
        print("Not Friday — skipping weekly review. Use --force to override.")
        return
    if "--force" not in sys.argv and not market_open_today():
        print("Market closed today — skipping weekly review. Use --force to override.")
        return
    ledger = load_ledger()
    # recommendations.json now also holds buy_alert/sell_signal entries
    # (see performance.py) — this review is specifically about committee
    # verdict accuracy, so filter to that kind only.
    verdicts = [r for r in load_verdicts() if r.get("kind", "committee_verdict") == "committee_verdict"]

    # 5y, not 1y: a verdict recorded >1y ago would otherwise get silently
    # mismatched against a truncated SPY window (no error, just wrong alpha).
    spy = yf.Ticker("SPY").history(period="5y")["Close"]

    def spy_return(since):
        w = spy[spy.index.strftime("%Y-%m-%d") >= since]
        return float(w.iloc[-1] / w.iloc[0] - 1) if len(w) > 1 else 0.0

    perf_lines = []
    for v in verdicts:
        try:
            px = float(yf.Ticker(v["ticker"]).history(period="1d")["Close"].iloc[-1])
            ret = px / v["price_at_verdict"] - 1
            alpha = ret - spy_return(v["date"])
            perf_lines.append(f"{v['ticker']} ({v['rating']}, {v['date']}): "
                              f"{ret:+.1%} | alpha vs SPY {alpha:+.1%}")
        except Exception:
            perf_lines.append(f"{v['ticker']} ({v['rating']}, {v['date']}): pricing error")

    board = [f"{t}: {e['overall']}/110 ({e.get('rating', '?')}) | timing {e['timing']}/100"
             for t, e in sorted(ledger.items(), key=lambda kv: -kv[1]["overall"])]
    sectors = Counter(e.get("sector", "Unknown") for e in ledger.values())
    total = sum(sectors.values()) or 1
    sector_lines = [f"{s}: {n} ({n / total:.0%})" for s, n in sectors.most_common()]
    theme_lines = thematic_concentration(load_config())

    def block(items, empty):
        return "\n".join(f"  - {i}" for i in items) if items else f"  - {empty}"

    # Options engine: this week's conviction calls from the append ledger
    # (evaluated in the signal-tracker section below; listed here so the
    # committee sees the contracts themselves).
    try:
        ideas = json.loads((PROMPTS_DIR.parent / "options_ideas.json").read_text())
    except Exception:
        ideas = []
    week_ideas = [r for r in ideas
                  if (now - datetime.fromisoformat(r["ts"])).days <= 7]
    idea_lines = [f"{r['ticker']}{' [ETF]' if r.get('asset_class') == 'etf' else ''} "
                  f"({r.get('lead')}-led, score {r.get('score')}/100): "
                  f"{(r.get('contract') or {}).get('expiry')} ${(r.get('contract') or {}).get('strike')}C "
                  f"@ ${(r.get('contract') or {}).get('mid')}"
                  for r in week_ideas]

    # Machine-vs-committee: does the paste time earn alpha? (signal_tracker)
    try:
        import signal_tracker
        tracker_block = "\n".join(f"  {l}" for l in signal_tracker.report_lines(max_days=90))
    except Exception as e:
        tracker_block = f"  - tracker unavailable this run: {e}"

    PROMPTS_DIR.mkdir(exist_ok=True)
    path = PROMPTS_DIR / f"{now:%Y-%m-%d}_WEEKLY_review.md"
    path.write_text(f"""# COMMITTEE DATA PAYLOAD — WEEKLY PERFORMANCE REVIEW
Generated: {now:%Y-%m-%d %H:%M} local | Source: stock-monitor weekly daemon
Instructions: Paste into the Investment Committee session. Have the Portfolio
Manager and Risk Manager lead a review: were past verdicts right, what should be
re-rated, and is sector concentration acceptable? Free-form output (no template).

## Alert-rate health (measurement only — thresholds are fixed, not adaptive)
  - {alert_stats.summary()}

## Verdict performance to date (return since verdict | alpha vs SPY)
{block(perf_lines, 'No verdicts recorded yet — record them with verdict.py add')}

## Current scoreboard (local proxy, ranked)
{block(board, 'Ledger empty — run monitor.py')}

## Sector concentration
{block(sector_lines, 'unavailable')}

## Thematic concentration (user-defined groupings)
{block(theme_lines, 'unavailable')}

## Options engine — conviction calls this week
{block(idea_lines, 'None this week — silence is the bar working')}

## Machine book vs committee book (signal_tracker, last 90d)
{tracker_block}
""")
    import obsidian
    obsidian.mirror_payload(path)
    print(f"Weekly review payload: {path.name}")
    if "--quiet-discord" not in sys.argv:
        try:
            send_message(f"📊 **Weekly review payload ready** — `{path.name}` "
                         f"({len(verdicts)} verdict(s) evaluated)")
        except Exception as e:
            print(f"Discord notice failed: {e}")


if __name__ == "__main__":
    main()
    import notify
    if notify.had_failures():
        print(f"{len(notify.FAILURES)} Discord post(s) failed this run — failing job so CI surfaces it.")
        sys.exit(1)
