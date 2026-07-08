"""Static dashboard generator — writes dashboard.html from the ledger + history.

Called automatically at the end of every monitor.py run; open the file in any
browser (it self-refreshes every 5 minutes):
    open ~/Claude/stock-monitor/dashboard.html
"""
import json
from datetime import datetime
from pathlib import Path

from committee import load_ledger, HISTORY_PATH

DASH_PATH = Path(__file__).parent / "dashboard.html"

BAND_COLORS = {"Strong Buy": "#1e8e3e", "Buy": "#34a853", "Watch": "#f9ab00",
               "Hold": "#9aa0a6", "Reduce": "#e8710a", "Sell": "#d93025"}


def day_delta(ticker):
    """Today's first-run vs latest overall score delta, if history exists."""
    if not HISTORY_PATH.exists():
        return None
    hist = json.loads(HISTORY_PATH.read_text())
    runs = hist.get(datetime.now().strftime("%Y-%m-%d"), {}).get(ticker, [])
    return runs[-1]["overall"] - runs[0]["overall"] if len(runs) > 1 else 0


def render():
    ledger = load_ledger()
    rows = []
    ranked = sorted(ledger.items(), key=lambda kv: -kv[1].get("overall", 0))
    for i, (t, e) in enumerate(ranked, 1):
        rating = e.get("rating", "?")
        color = BAND_COLORS.get(rating, "#9aa0a6")
        d = day_delta(t)
        delta = f"{d:+d}" if d else "—"
        dte = e.get("days_to_earnings")
        earnings = f"{dte}d" if isinstance(dte, int) and dte >= 0 else "—"
        rows.append(
            f"<tr><td>{i}</td><td><b>{t}</b></td>"
            f"<td>{e.get('overall', '?')}/110</td>"
            f"<td><span style='background:{color};color:#fff;padding:2px 8px;"
            f"border-radius:10px;font-size:12px'>{rating}</span></td>"
            f"<td>{e.get('timing', '?')}/100</td><td>{delta}</td>"
            f"<td>{earnings}</td><td>{e.get('sector', '?')}</td>"
            f"<td>{e.get('confidence', '?')}%</td></tr>")

    DASH_PATH.write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="300"><title>Stock Monitor</title>
<style>
body{{font-family:-apple-system,Helvetica,sans-serif;background:#0d1117;color:#e6edf3;margin:40px}}
h1{{font-size:20px}} .sub{{color:#8b949e;font-size:13px;margin-bottom:20px}}
table{{border-collapse:collapse;width:100%;max-width:900px}}
th,td{{text-align:left;padding:9px 14px;border-bottom:1px solid #21262d;font-size:14px}}
th{{color:#8b949e;font-weight:600;font-size:12px;text-transform:uppercase}}
tr:hover{{background:#161b22}}
</style></head><body>
<h1>📈 Stock Monitor — Committee Scoreboard</h1>
<div class="sub">Updated {datetime.now():%Y-%m-%d %H:%M} · local proxy scores (noise gate,
not committee verdicts) · auto-refreshes every 5 min · recommends only, never trades</div>
<table><tr><th>#</th><th>Ticker</th><th>Score</th><th>Rating</th><th>Timing</th>
<th>Δ today</th><th>Earnings</th><th>Sector</th><th>Conf.</th></tr>
{''.join(rows)}
</table></body></html>""")
    return DASH_PATH


if __name__ == "__main__":
    print(f"Dashboard written: {render()}")
