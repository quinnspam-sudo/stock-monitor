"""Performance query tool — compares "what the committee recommended" against
"what you actually did," using average-cost-basis accounting for real trades.

This tool covers two of the system's three ledgers:
  - recommendations.json — the committee book: committee_verdict entries only
    (verdict.py). Created on the first recorded verdict, so may not exist yet.
    What the COMMITTEE SAID.
  - actual_trades.json   — the execution ledger: real (paper) buys/sells,
    auto-written by execute.py. What you ACTUALLY DID.
The third ledger, signals.json (the machine book: buy_alert / conviction-call
signals), is scored separately by signal_tracker.py, not here.

Run:
    ./venv/bin/python performance.py actual
    ./venv/bin/python performance.py recommendations [--kind committee_verdict]
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yfinance as yf

RECOMMENDATIONS_PATH = Path(__file__).parent / "recommendations.json"
ACTUAL_TRADES_PATH = Path(__file__).parent / "actual_trades.json"


def load_recommendations(kind=None):
    recs = json.loads(RECOMMENDATIONS_PATH.read_text()) if RECOMMENDATIONS_PATH.exists() else []
    return [r for r in recs if kind is None or r.get("kind") == kind]


def load_actual_trades():
    return json.loads(ACTUAL_TRADES_PATH.read_text()) if ACTUAL_TRADES_PATH.exists() else []


def compute_open_positions(trades=None):
    """Average-cost-basis accounting over actual_trades.json, processed in
    date order. Returns {ticker: {"shares": float, "avg_cost": float,
    "held_since": "YYYY-MM-DD"}} for every ticker with shares > 0 remaining.

    Also used by sell_check.py — a stop-loss/take-profit/rebalance check
    only makes sense against a REAL open position with a real entry price,
    not a recommendation (this was the original design's conflation: it
    used to check recorded verdicts as if they were positions)."""
    trades = trades if trades is not None else load_actual_trades()
    trades = sorted(trades, key=lambda t: t["date"])
    positions = {}
    for t in trades:
        ticker = t["ticker"]
        pos = positions.setdefault(ticker, {"shares": 0.0, "cost": 0.0, "held_since": None})
        if t["action"] == "BUY":
            if pos["shares"] <= 0:
                pos["held_since"] = t["date"]
            pos["shares"] += t["shares"]
            pos["cost"] += t["amount"]
        elif t["action"] == "SELL":
            if pos["shares"] > 0:
                frac = min(1.0, t["shares"] / pos["shares"])
                pos["cost"] *= (1 - frac)
                pos["shares"] -= t["shares"]
            if pos["shares"] <= 1e-9:
                pos["shares"] = 0.0
                pos["cost"] = 0.0
                pos["held_since"] = None
    return {t: {"shares": p["shares"], "avg_cost": p["cost"] / p["shares"] if p["shares"] > 0 else None,
                "held_since": p["held_since"]}
            for t, p in positions.items() if p["shares"] > 1e-9}


def compute_closed_lots(trades=None):
    """Realized % change on shares that have actually been sold — walks the
    same average-cost accounting but records a closed lot each time a SELL
    reduces a position, using the avg cost basis AT THE TIME of that sale."""
    trades = trades if trades is not None else load_actual_trades()
    trades = sorted(trades, key=lambda t: t["date"])
    positions = {}
    closed = []
    for t in trades:
        ticker = t["ticker"]
        pos = positions.setdefault(ticker, {"shares": 0.0, "cost": 0.0})
        if t["action"] == "BUY":
            pos["shares"] += t["shares"]
            pos["cost"] += t["amount"]
        elif t["action"] == "SELL" and pos["shares"] > 0:
            avg_cost = pos["cost"] / pos["shares"]
            shares_closed = min(t["shares"], pos["shares"])  # clamp: can't close more than is held
            frac = shares_closed / pos["shares"]
            closed.append({
                "ticker": ticker, "date_closed": t["date"], "shares": shares_closed,
                "avg_cost": avg_cost, "exit_price": t["price"],
                "pct_change": t["price"] / avg_cost - 1 if avg_cost else None,
            })
            pos["cost"] *= (1 - frac)
            pos["shares"] -= shares_closed
    return closed


def compute_actual_performance():
    """Unrealized % change on every open position + realized % change on
    every closed lot. Returns (open_rows, closed_rows)."""
    open_positions = compute_open_positions()
    open_rows = []
    for ticker, pos in open_positions.items():
        try:
            price = float(yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1])
            pct = price / pos["avg_cost"] - 1
            open_rows.append({"ticker": ticker, "avg_cost": pos["avg_cost"], "price_now": price,
                              "pct_change": pct, "shares": pos["shares"], "held_since": pos["held_since"]})
        except Exception as e:
            open_rows.append({"ticker": ticker, "error": str(e)})
    closed_rows = compute_closed_lots()
    return open_rows, closed_rows


def compute_recommendation_performance(kind=None):
    recs = load_recommendations(kind)
    rows = []
    for r in recs:
        entry_price = r.get("price_at_verdict") or r.get("price")
        if not entry_price:
            continue
        try:
            price_now = float(yf.Ticker(r["ticker"]).history(period="1d")["Close"].iloc[-1])
            pct = price_now / entry_price - 1
            rows.append({"ticker": r["ticker"], "date": r["date"], "kind": r.get("kind", "committee_verdict"),
                        "entry_price": entry_price, "price_now": price_now, "pct_change": pct})
        except Exception as e:
            rows.append({"ticker": r["ticker"], "date": r["date"], "error": str(e)})
    return rows


def _summarize(rows, label):
    valid = [r for r in rows if "pct_change" in r and r["pct_change"] is not None]
    if not valid:
        print(f"No {label} with a computable % change.")
        return
    avg = sum(r["pct_change"] for r in valid) / len(valid)
    print(f"\n{len(valid)} {label} — average % change: {avg:+.1%}")


def cmd_actual(_args):
    open_rows, closed_rows = compute_actual_performance()
    print("=== OPEN POSITIONS (unrealized) ===")
    print(f"{'TICKER':<8}{'AVG COST':>10}{'PRICE NOW':>11}{'% CHANGE':>10}{'SHARES':>10}  HELD SINCE")
    for r in open_rows:
        if "error" in r:
            print(f"{r['ticker']:<8}  error: {r['error']}")
            continue
        print(f"{r['ticker']:<8}{r['avg_cost']:>10,.2f}{r['price_now']:>11,.2f}"
              f"{r['pct_change']:>+10.1%}{r['shares']:>10.4f}  {r['held_since']}")
    _summarize(open_rows, "open position(s)")

    print("\n=== CLOSED LOTS (realized) ===")
    print(f"{'TICKER':<8}{'AVG COST':>10}{'EXIT':>10}{'% CHANGE':>10}  DATE CLOSED")
    for r in closed_rows:
        print(f"{r['ticker']:<8}{r['avg_cost']:>10,.2f}{r['exit_price']:>10,.2f}"
              f"{r['pct_change']:>+10.1%}  {r['date_closed']}")
    _summarize(closed_rows, "closed lot(s)")


def cmd_recommendations(args):
    kind = None
    if "--kind" in args:
        kind = args[args.index("--kind") + 1]
    rows = compute_recommendation_performance(kind)
    label = f"recommendations ({kind})" if kind else "all recommendations"
    print(f"=== {label.upper()} ===")
    print(f"{'DATE':<12}{'TICKER':<8}{'KIND':<16}{'ENTRY':>10}{'NOW':>10}{'% CHANGE':>10}")
    for r in rows:
        if "error" in r:
            print(f"{r['date']:<12}{r['ticker']:<8}  error: {r['error']}")
            continue
        print(f"{r['date']:<12}{r['ticker']:<8}{r['kind']:<16}"
              f"{r['entry_price']:>10,.2f}{r['price_now']:>10,.2f}{r['pct_change']:>+10.1%}")
    _summarize(rows, label)


if __name__ == "__main__":
    cmds = {"actual": cmd_actual, "recommendations": cmd_recommendations}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[sys.argv[1]](sys.argv[2:])
