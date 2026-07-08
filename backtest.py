"""Weekly accuracy backtest — Saturday morning.

Looks at every rating the monitor issued during the week just finished
(Monday-Friday, pulled from history.json's daily snapshots) and checks it
against what the stock actually did over that same week. This is the
"did the local scoring engine's calls actually work" check — separate from
weekly.py, which reviews the *committee's* human-in-the-loop verdicts.

Run: ./venv/bin/python backtest.py [--force] [--quiet-discord]
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

from notify import send_message
from committee import PROMPTS_DIR, HISTORY_PATH, rating_for

ROOT = Path(__file__).parent
BACKTEST_LOG = ROOT / "backtest_log.json"

BUY_RATINGS = {"Strong Buy", "Buy"}
BEARISH_RATINGS = {"Reduce", "Sell"}


def last_full_week(today):
    """Return (monday, friday) dates for the Mon-Fri that just ended."""
    # If run on Saturday, yesterday (Friday) is the end of the week just finished.
    friday = today - timedelta(days=(today.weekday() - 4) % 7 or 7)
    monday = friday - timedelta(days=4)
    return monday, friday


def week_snapshots(hist, monday, friday):
    """ticker -> first snapshot of the week (rating call made early in the week)."""
    days = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
    calls = {}
    for day in days:
        for ticker, entries in hist.get(day, {}).items():
            if ticker not in calls and entries:
                calls[ticker] = {"date": day, **entries[0]}
    return calls


def week_return(ticker, monday, friday):
    h = yf.Ticker(ticker).history(start=monday.strftime("%Y-%m-%d"),
                                   end=(friday + timedelta(days=1)).strftime("%Y-%m-%d"))
    if len(h) < 2:
        return None
    return float(h["Close"].iloc[-1] / h["Close"].iloc[0] - 1)


def main():
    now = datetime.now()
    if now.weekday() != 5 and "--force" not in sys.argv:
        print("Not Saturday — skipping backtest. Use --force to override.")
        return

    monday, friday = last_full_week(now.date())
    hist = json.loads(HISTORY_PATH.read_text()) if HISTORY_PATH.exists() else {}
    calls = week_snapshots(hist, monday, friday)

    if not calls:
        print(f"No history for week of {monday:%Y-%m-%d}–{friday:%Y-%m-%d} — skipping.")
        return

    spy_ret = week_return("SPY", monday, friday) or 0.0

    rows = []
    for ticker, call in calls.items():
        try:
            ret = week_return(ticker, monday, friday)
        except Exception:
            ret = None
        if ret is None:
            continue
        rows.append({
            "ticker": ticker, "rating": call["rating"], "overall": call["overall"],
            "return": ret, "alpha": ret - spy_ret,
        })

    if not rows:
        print("No priceable tickers for backtest week — skipping.")
        return

    def bucket_stats(bucket_rows):
        if not bucket_rows:
            return None
        n = len(bucket_rows)
        avg_ret = sum(r["return"] for r in bucket_rows) / n
        hit_rate = sum(1 for r in bucket_rows if r["return"] > 0) / n
        beat_spy = sum(1 for r in bucket_rows if r["alpha"] > 0) / n
        return {"n": n, "avg_return": avg_ret, "hit_rate": hit_rate, "beat_spy_rate": beat_spy}

    buy_rows = [r for r in rows if r["rating"] in BUY_RATINGS]
    bear_rows = [r for r in rows if r["rating"] in BEARISH_RATINGS]
    other_rows = [r for r in rows if r not in buy_rows and r not in bear_rows]

    sorted_rows = sorted(rows, key=lambda r: -r["overall"])
    half = max(1, len(sorted_rows) // 2)
    top_half, bottom_half = sorted_rows[:half], sorted_rows[half:]

    buy_stats = bucket_stats(buy_rows)
    bear_stats = bucket_stats(bear_rows)
    other_stats = bucket_stats(other_rows)
    top_stats = bucket_stats(top_half)
    bottom_stats = bucket_stats(bottom_half)

    def fmt(stats, label):
        if not stats:
            return f"  - {label}: no calls this week"
        return (f"  - {label} (n={stats['n']}): avg return {stats['avg_return']:+.1%}, "
                f"hit rate {stats['hit_rate']:.0%}, beat SPY {stats['beat_spy_rate']:.0%}")

    row_lines = "\n".join(
        f"  - {r['ticker']}: {r['rating']} (score {r['overall']}/110) → "
        f"{r['return']:+.1%} (alpha {r['alpha']:+.1%})"
        for r in sorted(rows, key=lambda r: -r["return"])
    )

    signal_works = (top_stats and bottom_stats
                    and top_stats["avg_return"] > bottom_stats["avg_return"])

    verdict_line = ("Top-half scores outperformed bottom-half — scoring signal held up this week."
                    if signal_works else
                    "Top-half scores did NOT outperform bottom-half — scoring signal was noise or inverted this week.")

    PROMPTS_DIR.mkdir(exist_ok=True)
    path = PROMPTS_DIR / f"{now:%Y-%m-%d}_WEEKLY_BACKTEST.md"
    path.write_text(f"""# COMMITTEE DATA PAYLOAD — WEEKLY SCORING BACKTEST
Generated: {now:%Y-%m-%d %H:%M} local | Week tested: {monday:%Y-%m-%d} – {friday:%Y-%m-%d}
Instructions: This checks the LOCAL SCORING ENGINE's calls (not committee verdicts —
see WEEKLY_review for that) against what each ticker actually did over the same week.
SPY return this week: {spy_ret:+.1%}

## By rating bucket
{fmt(buy_stats, "Buy / Strong Buy")}
{fmt(other_stats, "Watch / Hold")}
{fmt(bear_stats, "Reduce / Sell")}

## Score-return relationship (top-half vs bottom-half score, by ticker count)
{fmt(top_stats, "Top-half score")}
{fmt(bottom_stats, "Bottom-half score")}

**{verdict_line}**

## Per-ticker detail (ranked by realized return)
{row_lines}
""")
    import obsidian
    obsidian.mirror_payload(path)

    log = json.loads(BACKTEST_LOG.read_text()) if BACKTEST_LOG.exists() else []
    log.append({
        "week": f"{monday:%Y-%m-%d}_{friday:%Y-%m-%d}", "spy_return": spy_ret,
        "buy_stats": buy_stats, "bear_stats": bear_stats,
        "top_half_stats": top_stats, "bottom_half_stats": bottom_stats,
        "signal_held": signal_works,
    })
    BACKTEST_LOG.write_text(json.dumps(log, indent=2))

    print(f"Backtest payload: {path.name}")
    if "--quiet-discord" not in sys.argv:
        try:
            send_message(f"\U0001f4c9 **Weekly backtest ready** — `{path.name}` "
                         f"({len(rows)} calls tested, {'signal held' if signal_works else 'signal failed'})")
        except Exception as e:
            print(f"Discord notice failed: {e}")


if __name__ == "__main__":
    main()
