"""Static dashboard generator — writes dashboard.html from the ledger + history.

Called automatically at the end of every monitor.py run; open the file in any
browser (it self-refreshes every 5 minutes):
    open ~/Claude/stock-monitor/dashboard.html
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from committee import load_ledger, HISTORY_PATH

PACIFIC = ZoneInfo("America/Los_Angeles")
TIER_COLORS = {"HIGH": "#1e8e3e", "MEDIUM": "#f9ab00", "LOW": "#e8710a"}

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
        blend = e.get("blend")
        tier = e.get("tier")
        tier_html = (f"<span style='color:{TIER_COLORS.get(tier, '#9aa0a6')};font-weight:600'>{tier}</span>"
                     + (f" {e['conviction']}" if e.get("conviction") is not None else "")
                     if tier else "—")
        rows.append(
            f"<tr><td>{i}</td><td><b>{t}</b></td>"
            f"<td>{e.get('overall', '?')}/110</td>"
            f"<td><b>{blend if blend is not None else '—'}</b></td>"
            f"<td>{tier_html}</td>"
            f"<td><span style='background:{color};color:#fff;padding:2px 8px;"
            f"border-radius:10px;font-size:12px'>{rating}</span></td>"
            f"<td>{e.get('timing', '?')}/100</td><td>{delta}</td>"
            f"<td>{earnings}</td><td>{e.get('sector', '?')}</td>"
            f"<td>{e.get('confidence', '?')}%</td></tr>")

    # Staleness banner: newest ledger write >2h old during market hours means
    # the pipeline has stopped feeding the dashboard — say so in red instead of
    # silently showing yesterday's numbers.
    stale_html = ""
    dates = [e.get("date") for e in ledger.values() if e.get("date")]
    if dates:
        try:
            newest = max(datetime.strptime(d, "%Y-%m-%d %H:%M") for d in dates)
            now_pt = datetime.now(PACIFIC)
            age_h = (now_pt.replace(tzinfo=None) - newest).total_seconds() / 3600
            in_session = now_pt.weekday() < 5 and (6, 30) <= (now_pt.hour, now_pt.minute) <= (13, 0)
            if in_session and age_h > 2:
                stale_html = (f"<div style='background:#d93025;color:#fff;padding:10px 14px;"
                              f"border-radius:6px;margin-bottom:16px;font-size:14px'>⚠️ Data is "
                              f"{age_h:.1f}h old during market hours — the monitor pipeline may be "
                              f"down. Check GitHub Actions / cron-job.org.</div>")
        except ValueError:
            pass

    # Options engine panel: conviction calls from the append ledger (30d).
    # Empty is the normal state — the engine is designed to be silent.
    opt_rows = []
    try:
        ideas = json.loads((Path(__file__).parent / "options_ideas.json").read_text())
        for r in ideas:
            if (datetime.now() - datetime.fromisoformat(r["ts"])).days > 30:
                continue
            c = r.get("contract") or {}
            etf = " <span style='color:#8b949e;font-size:11px'>[ETF]</span>" \
                if r.get("asset_class") == "etf" else ""
            opt_rows.append(
                f"<tr><td>{r['ts'][:10]}</td><td><b>{r['ticker']}</b>{etf}</td>"
                f"<td>{r.get('lead', '?')}-led</td><td>{r.get('score', '?')}/100</td>"
                f"<td>{c.get('expiry', '?')} ${c.get('strike', '?')}C @ ${c.get('mid', '?')}"
                f" (Δ{c.get('delta', '?')})</td></tr>")
    except Exception:
        pass
    options_html = ("<h1 style='margin-top:36px'>🎯 Options Engine — conviction calls (30d)</h1>"
                    + ("<table><tr><th>Date</th><th>Ticker</th><th>Lead</th><th>Score</th>"
                       "<th>Contract</th></tr>" + "".join(opt_rows) + "</table>"
                       if opt_rows else
                       "<div class='sub'>None in the last 30 days — silence is the bar working.</div>"))

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
not committee verdicts) · Blend = 55% momentum + 45% factor conviction, the score that
actually gates BUY alerts · auto-refreshes every 5 min · recommends only, never trades</div>
{stale_html}<table><tr><th>#</th><th>Ticker</th><th>Score</th><th>Blend</th><th>Conviction</th>
<th>Rating</th><th>Timing</th><th>Δ today</th><th>Earnings</th><th>Sector</th><th>Conf.</th></tr>
{''.join(rows)}
</table>
{options_html}
</body></html>""")
    return DASH_PATH


if __name__ == "__main__":
    print(f"Dashboard written: {render()}")
