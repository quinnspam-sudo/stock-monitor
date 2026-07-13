"""Watchlist health check — finds names that can never alert.

Two silent failure modes discovered 2026-07-13 in CI logs (BESIY, DSCSY
returning fundamentals 404s):
  1. No price history on yfinance → score_ticker returns None → the ticker
     is scanned every run and silently skipped forever.
  2. Price OK but no fundamentals → factors.compute fails → conviction is
     UNRATED → BUY alerts require HIGH/MEDIUM tier, so the ticker can pass
     every price gate and still never alert. Dead weight that LOOKS covered.

Neither shows up anywhere unless someone greps CI logs. This makes it a
report: run light (price check, fast, batch) by default; --deep also probes
fundamentals for every ticker (~1 call each, slow — weekly is fine).
Posts a summary to the updates channel with --discord when problems exist.

Run: ./venv/bin/python watchlist_health.py [--deep] [--discord]
"""
import json
import sys
from pathlib import Path

import yfinance as yf

from notify import load_config, send_message

REPORT_PATH = Path(__file__).parent / "watchlist_health.json"


def main():
    cfg = load_config()
    wl = cfg["watchlist"]
    print(f"Checking {len(wl)} tickers…")

    px = yf.download(wl, period="1mo", auto_adjust=True, progress=False,
                     group_by="column")["Close"]
    no_price = sorted(t for t in wl
                      if t not in px.columns or px[t].dropna().empty)
    stale = sorted(t for t in wl if t in px.columns and not px[t].dropna().empty
                   and px[t].dropna().index[-1] < px.dropna(how="all").index[-5])

    no_fundamentals = []
    if "--deep" in sys.argv:
        import factors
        for t in wl:
            if t in no_price:
                continue
            try:
                f = factors.compute(t)
                conv, tier = factors.conviction(f) if f else (None, "UNRATED")
                if tier == "UNRATED":
                    no_fundamentals.append(t)
            except Exception:
                no_fundamentals.append(t)
        no_fundamentals.sort()

    report = {"checked": len(wl), "no_price": no_price, "stale_price": stale,
              "unrated_no_fundamentals": no_fundamentals if "--deep" in sys.argv else None}
    REPORT_PATH.write_text(json.dumps(report, indent=1))

    lines = [f"Checked {len(wl)} tickers."]
    if no_price:
        lines.append(f"NO PRICE DATA (never scoreable): {', '.join(no_price)}")
    if stale:
        lines.append(f"STALE PRICE (no close in 5 sessions): {', '.join(stale)}")
    if "--deep" in sys.argv:
        if no_fundamentals:
            lines.append(f"UNRATED — no fundamentals, can never reach HIGH/MEDIUM "
                         f"conviction so can NEVER alert: {', '.join(no_fundamentals)}")
        else:
            lines.append("All price-covered tickers have rateable fundamentals.")
    if not no_price and not stale and not no_fundamentals:
        lines.append("Watchlist fully healthy.")
    out = "\n".join(lines)
    print(out)

    problems = bool(no_price or stale or no_fundamentals)
    if "--discord" in sys.argv and problems:
        send_message("🩺 **WATCHLIST HEALTH** — names that can never alert "
                     "(fix the symbol, swap to the primary listing, or drop them):\n"
                     + out, kind="WATCHLIST_HEALTH")
        print("Posted to Discord.")


if __name__ == "__main__":
    main()
    import notify
    if notify.had_failures():
        sys.exit(1)
