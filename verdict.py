"""Verdict journal — closes the loop with the Claude Pro committee.

Writes into recommendations.json (kind="committee_verdict") — the "what did
the system/committee say to do" ledger, distinct from actual_trades.json
("what did I actually buy/sell"). See performance.py to compare the two.

After you paste a payload into Claude Pro and get a Template A verdict, record it:
    ./venv/bin/python verdict.py add TICKER RATING [--entry 148.50] [--note "thesis..."]
    e.g. ./venv/bin/python verdict.py add AAPL "Buy" --entry 308 --note "Margin expansion thesis"

Review performance of all recorded verdicts vs price since:
    ./venv/bin/python verdict.py review
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yfinance as yf

RECOMMENDATIONS_PATH = Path(__file__).parent / "recommendations.json"


def load():
    return json.loads(RECOMMENDATIONS_PATH.read_text()) if RECOMMENDATIONS_PATH.exists() else []


def save(v):
    RECOMMENDATIONS_PATH.write_text(json.dumps(v, indent=2))


def cmd_add(args):
    ticker, rating = args[0].upper(), args[1]
    entry = note = None
    if "--entry" in args:
        entry = float(args[args.index("--entry") + 1])
    if "--note" in args:
        note = args[args.index("--note") + 1]
    price = float(yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1])
    recs = load()
    date = datetime.now().strftime("%Y-%m-%d")
    recs.append({
        "date": date, "ticker": ticker, "kind": "committee_verdict", "rating": rating,
        "price_at_verdict": round(price, 2),
        "suggested_entry": entry, "note": note,
    })
    save(recs)
    print(f"Recorded: {ticker} {rating} @ ${price:,.2f} on {date}")
    import obsidian
    obsidian.record_verdict(ticker, rating, price, entry, note, date)
    import git_sync
    git_sync.commit_and_push(["recommendations.json"], f"verdict: {ticker} {rating} @ {price:,.2f}")


def cmd_review(_args):
    recs = [r for r in load() if r.get("kind", "committee_verdict") == "committee_verdict"]
    if not recs:
        print("No committee verdicts recorded yet. Use: verdict.py add TICKER RATING")
        return
    # 5y, not 1y: a verdict recorded >1y ago would otherwise get silently
    # mismatched against a truncated SPY window (no error, just wrong alpha).
    spy = yf.Ticker("SPY").history(period="5y")["Close"]

    def spy_return(since):
        window = spy[spy.index.strftime("%Y-%m-%d") >= since]
        return float(window.iloc[-1] / window.iloc[0] - 1) if len(window) > 1 else 0.0

    print(f"{'DATE':<12}{'TICKER':<8}{'RATING':<12}{'AT VERDICT':>11}{'NOW':>10}{'RETURN':>9}{'vs SPY':>9}")
    for v in recs:
        try:
            now_price = float(yf.Ticker(v["ticker"]).history(period="1d")["Close"].iloc[-1])
            ret = now_price / v["price_at_verdict"] - 1
            alpha = ret - spy_return(v["date"])
            print(f"{v['date']:<12}{v['ticker']:<8}{v['rating']:<12}"
                  f"{v['price_at_verdict']:>11,.2f}{now_price:>10,.2f}{ret:>9.1%}{alpha:>+9.1%}")
        except Exception as e:
            print(f"{v['date']:<12}{v['ticker']:<8}{v['rating']:<12}  error: {e}")
    buys = [v for v in recs if "buy" in v["rating"].lower()]
    print(f"\n{len(recs)} verdicts recorded ({len(buys)} buy-side). "
          "'vs SPY' is excess return over SPY from the verdict date.")


if __name__ == "__main__":
    cmds = {"add": cmd_add, "review": cmd_review}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[sys.argv[1]](sys.argv[2:])
