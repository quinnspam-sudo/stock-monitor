"""Machine-vs-committee comparison tracker.

Answers one question with data instead of opinion: DOES THE CLAUDE PRO
COMMITTEE EARN ITS PASTE TIME? (Quinn, 2026-07-09 — precursor to deciding
whether to automate the committee away.)

Two books accumulate in parallel:
  MACHINE BOOK  — signals.json (this module's ledger). Every signal the
    pipeline emits, recorded AT EMISSION with the price at that moment,
    before any human sees it: buy_alert (monitor.py), call_idea (monitor.py,
    dual-conviction), call_conviction (options_engine.py daily scan).
  COMMITTEE BOOK — recommendations.json kind="committee_verdict", recorded
    by verdict.py when Quinn logs what the committee said.

`report` joins them: a machine signal is APPROVED if a committee verdict for
the same ticker lands within JOIN_WINDOW_D days and its rating contains
"buy"; REJECTED if a verdict lands but isn't buy-rated; UNREVIEWED if no
verdict was ever logged (payload never pasted). Then it computes, for every
signal, the underlying's return since emission and its alpha vs SPY over the
same window, and aggregates per group. The committee adds value iff the
APPROVED group's average alpha beats the ALL-MACHINE average by more than
noise — the report prints exactly that comparison.

Option signals also get a delta-approximation of the CONTRACT's return
(underlying move x delta x spot / premium, capped at -100%) — crude (ignores
gamma/theta/vega) but directionally honest for "did the leverage pay?".

Usage:
    ./venv/bin/python signal_tracker.py report            # the comparison
    ./venv/bin/python signal_tracker.py report --days 90  # only recent signals

Recording is wired into monitor.py / options_engine.py (never raises there —
tracking must not break alerting). Verdicts keep flowing through verdict.py
unchanged. Give it 2-3 months of accumulation before trusting the split.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).parent
SIGNALS_PATH = DIR / "signals.json"
RECOMMENDATIONS_PATH = DIR / "recommendations.json"

JOIN_WINDOW_D = 5   # verdict within this many days of the signal = same decision


def record(kind, ticker, price, detail="", contract=None):
    """Append one machine signal. Never raises — callers are alert paths."""
    try:
        sigs = json.loads(SIGNALS_PATH.read_text()) if SIGNALS_PATH.exists() else []
        sigs.append({"date": datetime.now().strftime("%Y-%m-%d"),
                     "ts": datetime.now().isoformat(timespec="seconds"),
                     "kind": kind, "ticker": ticker,
                     "price": round(float(price), 2) if price else None,
                     "detail": detail,
                     "contract": contract})   # expiry/strike/mid/delta for options
        SIGNALS_PATH.write_text(json.dumps(sigs, indent=1))
    except Exception as e:
        print(f"signal_tracker.record({ticker}): {e} (continuing)")


def _spy_return(spy, since):
    w = spy[spy.index.strftime("%Y-%m-%d") >= since]
    return float(w.iloc[-1] / w.iloc[0] - 1) if len(w) > 1 else 0.0


def _verdict_for(sig, verdicts):
    """Nearest committee verdict for the same ticker within the join window."""
    d0 = datetime.strptime(sig["date"], "%Y-%m-%d")
    best = None
    for v in verdicts:
        if v["ticker"] != sig["ticker"]:
            continue
        gap = abs((datetime.strptime(v["date"], "%Y-%m-%d") - d0).days)
        if gap <= JOIN_WINDOW_D and (best is None or gap < best[0]):
            best = (gap, v)
    return best[1] if best else None


def _agg(rows):
    rets = [r["alpha"] for r in rows if r.get("alpha") is not None]
    if not rets:
        return "n/a (no priced signals)"
    wins = sum(1 for a in rets if a > 0)
    return (f"n={len(rets)}  avg alpha {sum(rets)/len(rets):+.1%}  "
            f"win-rate vs SPY {wins}/{len(rets)} ({wins/len(rets):.0%})")


def cmd_report(args):
    import yfinance as yf
    max_days = int(args[args.index("--days") + 1]) if "--days" in args else None

    sigs = json.loads(SIGNALS_PATH.read_text()) if SIGNALS_PATH.exists() else []
    recs = json.loads(RECOMMENDATIONS_PATH.read_text()) if RECOMMENDATIONS_PATH.exists() else []
    verdicts = [r for r in recs if r.get("kind", "committee_verdict") == "committee_verdict"]
    if max_days:
        cutoff = datetime.now().timestamp() - max_days * 86400
        sigs = [s for s in sigs if datetime.strptime(s["date"], "%Y-%m-%d").timestamp() >= cutoff]
    if not sigs:
        print("No machine signals recorded yet — the ledger starts accumulating "
              "from the first alert after this tracker was deployed (2026-07-09).")
        return

    spy = yf.Ticker("SPY").history(period="5y")["Close"]
    rows = []
    for s in sigs:
        row = dict(s)
        v = _verdict_for(s, verdicts)
        row["group"] = ("APPROVED" if v and "buy" in v["rating"].lower()
                        else "REJECTED" if v else "UNREVIEWED")
        row["verdict"] = v["rating"] if v else None
        try:
            now = float(yf.Ticker(s["ticker"]).history(period="5d")["Close"].iloc[-1])
            if s.get("price"):
                row["ret"] = now / s["price"] - 1
                row["alpha"] = row["ret"] - _spy_return(spy, s["date"])
            c = s.get("contract")
            if c and c.get("mid") and c.get("delta") and s.get("price"):
                approx = (now - s["price"]) * c["delta"] * 100 / (c["mid"] * 100)
                row["opt_ret"] = max(-1.0, approx)
        except Exception as e:
            row["error"] = str(e)
        rows.append(row)

    print(f"{'DATE':<12}{'KIND':<17}{'TICKER':<8}{'GROUP':<12}{'RETURN':>8}{'vs SPY':>9}{'~OPT':>8}")
    for r in rows:
        print(f"{r['date']:<12}{r['kind']:<17}{r['ticker']:<8}{r['group']:<12}"
              + (f"{r['ret']:>8.1%}" if r.get("ret") is not None else f"{'n/a':>8}")
              + (f"{r['alpha']:>+9.1%}" if r.get("alpha") is not None else f"{'n/a':>9}")
              + (f"{r['opt_ret']:>8.0%}" if r.get("opt_ret") is not None else f"{'':>8}"))

    approved = [r for r in rows if r["group"] == "APPROVED"]
    rejected = [r for r in rows if r["group"] == "REJECTED"]
    unreviewed = [r for r in rows if r["group"] == "UNREVIEWED"]
    print(f"\nMACHINE BOOK (all signals, no filter): {_agg(rows)}")
    print(f"COMMITTEE-APPROVED:                    {_agg(approved)}")
    print(f"COMMITTEE-REJECTED (filter's saves):   {_agg(rejected)}")
    print(f"UNREVIEWED (never pasted):             {_agg(unreviewed)}")

    a = [r["alpha"] for r in approved if r.get("alpha") is not None]
    m = [r["alpha"] for r in rows if r.get("alpha") is not None]
    if a and m and len(m) > len(a):
        edge = sum(a) / len(a) - sum(m) / len(m)
        print(f"\nCommittee filter edge vs raw machine book: {edge:+.1%} avg alpha. "
              + ("Positive = the paste time is earning alpha."
                 if edge > 0 else
                 "Negative/zero = the mechanical gates alone are doing the work."))
    print("\nNote: REJECTED alpha is what the committee KEPT YOU OUT OF — for the "
          "filter to be valuable, rejected signals should underperform approved ones. "
          "Wait for ~2-3 months / 15+ joined signals before acting on this.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "report":
        print(__doc__)
        sys.exit(1)
    cmd_report(sys.argv[2:])
