"""Ecosystem dashboard — one static page with every important metric.

Reads scores.json, history.json, config.json, alert_state.json,
recommendations.json, committee_prompts/ and monitor.log, and writes
ecosystem.html (self-contained, no network, self-refreshes every 5 min).

    ./venv/bin/python ecosystem.py && open ecosystem.html
"""
import html
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).parent
PACIFIC = ZoneInfo("America/Los_Angeles")
OUT = BASE / "ecosystem.html"

# validated reference palette (light / dark handled via CSS variables)
SERIES = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7"]
BAND_COLORS = {"Strong Buy": "#1e8e3e", "Buy": "#34a853", "Watch": "#f9ab00",
               "Hold": "#9aa0a6", "Reduce": "#e8710a", "Sell": "#d93025"}
TIER_COLORS = {"HIGH": "#1e8e3e", "MEDIUM": "#f9ab00", "LOW": "#e8710a"}


def load(name, default):
    p = BASE / name
    return json.loads(p.read_text()) if p.exists() else default


def esc(s):
    return html.escape(str(s))


def sparkline(vals, w=110, h=26, color="var(--series1)"):
    if len(vals) < 2:
        return "<span class='muted'>—</span>"
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(
        f"{2 + i * (w - 4) / (len(vals) - 1):.1f},{h - 3 - (v - lo) / rng * (h - 6):.1f}"
        for i, v in enumerate(vals))
    return (f"<svg width='{w}' height='{h}' aria-label='intraday trend'>"
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2' "
            f"stroke-linecap='round' stroke-linejoin='round'/></svg>")


def hbar(pct, color):
    return (f"<div class='bar-track'><div class='bar-fill' "
            f"style='width:{pct:.0f}%;background:{color}'></div></div>")


def line_chart(series, w=920, h=260):
    """series: list of (label, color, [(time, val), ...]) — shared y 0-110."""
    left, right, top, bot = 42, 12, 12, 26
    pw, ph = w - left - right, h - top - bot
    times = sorted({t for _, _, pts in series for t, _ in pts})
    if len(times) < 2:
        return "<p class='muted'>Not enough intraday runs yet today.</p>"
    tx = {t: left + i * pw / (len(times) - 1) for i, t in enumerate(times)}
    allv = [v for _, _, pts in series for _, v in pts]
    lo, hi = min(allv) - 2, max(allv) + 2
    rng = (hi - lo) or 1
    y = lambda v: top + ph - (v - lo) / rng * ph
    step = max(1, round(rng / 4))
    gv, gridvals = -(-int(lo) // step) * step, []
    while gv <= hi:
        gridvals.append(gv)
        gv += step
    grid = "".join(
        f"<line x1='{left}' x2='{w - right}' y1='{y(v):.0f}' y2='{y(v):.0f}' class='grid'/>"
        f"<text x='{left - 8}' y='{y(v) + 4:.0f}' class='tick' text-anchor='end'>{v}</text>"
        for v in gridvals)
    lines, labels = "", ""
    for label, color, pts in series:
        pl = " ".join(f"{tx[t]:.1f},{y(v):.1f}" for t, v in pts if t in tx)
        lines += (f"<polyline points='{pl}' fill='none' stroke='{color}' stroke-width='2' "
                  f"stroke-linejoin='round'/>")
        lt, lv = pts[-1]
        labels += (f"<text x='{tx[lt] + 5:.0f}' y='{y(lv) + 4:.0f}' class='dlabel' "
                   f"fill='{color}'>{esc(label)}</text>")
    n = max(1, len(times) // 6)
    ticks = "".join(
        f"<text x='{tx[t]:.0f}' y='{h - 6}' class='tick' text-anchor='middle'>{esc(t)}</text>"
        for t in times[::n])
    return (f"<svg viewBox='0 0 {w} {h}' style='width:100%;height:auto' role='img' "
            f"aria-label='Intraday overall scores'>{grid}{lines}{labels}{ticks}"
            f"<line x1='{left}' x2='{w - right}' y1='{top + ph}' y2='{top + ph}' class='axis'/></svg>")


def render():
    now = datetime.now(PACIFIC)
    today = now.strftime("%Y-%m-%d")
    scores = load("scores.json", {})
    history = load("history.json", {})
    config = load("config.json", {})
    alert_state = load("alert_state.json", {})
    recs = load("recommendations.json", [])
    hist_today = history.get(today, {})

    ranked = sorted(scores.items(), key=lambda kv: -kv[1].get("overall", 0))

    # ---- KPIs -------------------------------------------------------------
    watchlist = config.get("watchlist", [])
    overalls = [e.get("overall", 0) for _, e in ranked]
    avg_overall = sum(overalls) / len(overalls) if overalls else 0
    buys = [t for t, e in ranked if e.get("rating") in ("Buy", "Strong Buy")]
    threshold = config.get("alert_threshold", 76)
    above = [t for t, e in ranked if e.get("overall", 0) >= threshold]
    midnight = datetime(now.year, now.month, now.day, tzinfo=PACIFIC).timestamp()
    alerts_today = [t for t, ts in alert_state.items() if ts >= midnight]
    payloads = sorted(BASE.glob("committee_prompts/*.md"))
    payloads_today = [p for p in payloads if p.name.startswith(today)]
    earnings_soon = sorted(
        [(t, e["days_to_earnings"]) for t, e in ranked
         if isinstance(e.get("days_to_earnings"), int) and 0 <= e["days_to_earnings"] <= 7],
        key=lambda x: x[1])
    runs_today = max((len(v) for v in hist_today.values()), default=0)

    # Staleness from the newest score timestamp itself (naive PT strings),
    # not file mtime — mtime is just the last git pull on the Mac.
    scores_age_min = None
    dates = [e["date"] for _, e in ranked if e.get("date")]
    if dates:
        newest = datetime.strptime(max(dates), "%Y-%m-%d %H:%M").replace(tzinfo=PACIFIC)
        scores_age_min = (now - newest).total_seconds() / 60
    market_hours = now.weekday() < 5 and 6 <= now.hour < 14
    stale = market_hours and scores_age_min is not None and scores_age_min > 120

    def tile(label, value, sub=""):
        return (f"<div class='tile'><div class='tlabel'>{label}</div>"
                f"<div class='tvalue'>{value}</div>"
                f"<div class='tsub'>{sub}</div></div>")

    kpis = "".join([
        tile("Tracked tickers", len(watchlist), f"{len(ranked)} scored in ledger"),
        tile("Avg overall score", f"{avg_overall:.0f}<span class='denom'>/110</span>",
             f"top: {ranked[0][0]} {ranked[0][1]['overall']}" if ranked else ""),
        tile("Buy-rated", len(buys), ", ".join(buys[:6]) + ("…" if len(buys) > 6 else "")),
        tile("Above alert threshold", len(above), f"threshold {threshold}"),
        tile("Alerts fired today", len(alerts_today),
             ", ".join(sorted(alerts_today)[:5]) + ("…" if len(alerts_today) > 5 else "") or "none"),
        tile("Committee payloads today", len(payloads_today), f"{len(payloads)} all-time"),
        tile("Monitor runs today", runs_today, "15-min cadence in market hours"),
        tile("Verdicts logged", len(recs),
             "verdict.py add TICKER RATING" if not recs else "recommendations.json"),
    ])

    # ---- rating distribution ---------------------------------------------
    order = ["Strong Buy", "Buy", "Watch", "Hold", "Reduce", "Sell"]
    counts = {r: sum(1 for _, e in ranked if e.get("rating") == r) for r in order}
    total = len(ranked) or 1
    dist = "".join(
        f"<div class='dist-row'><span class='dist-name'><i class='dot' "
        f"style='background:{BAND_COLORS[r]}'></i>{r}</span>"
        f"{hbar(counts[r] / total * 100, BAND_COLORS[r])}"
        f"<span class='dist-n'>{counts[r]}</span></div>"
        for r in order if counts[r])

    # ---- sector averages ---------------------------------------------------
    sectors = {}
    for _, e in ranked:
        sectors.setdefault(e.get("sector", "Unknown"), []).append(e.get("overall", 0))
    sec_rows = sorted(((s, sum(v) / len(v), len(v)) for s, v in sectors.items()),
                      key=lambda x: -x[1])
    sec_html = "".join(
        f"<div class='dist-row'><span class='dist-name'>{esc(s)}</span>"
        f"{hbar(a / 110 * 100, 'var(--series1)')}"
        f"<span class='dist-n'>{a:.0f} <span class='muted'>({n})</span></span></div>"
        for s, a, n in sec_rows)

    # ---- intraday chart: top 5 by overall ---------------------------------
    chart_series = []
    for i, (t, _) in enumerate(ranked[:5]):
        runs = hist_today.get(t, [])
        if len(runs) >= 2:
            chart_series.append((t, SERIES[i], [(r["time"], r["overall"]) for r in runs]))
    chart = line_chart(chart_series) if chart_series else \
        "<p class='muted'>No intraday history for today yet.</p>"
    legend = "".join(
        f"<span class='leg'><i class='dot' style='background:{c}'></i>{esc(t)}</span>"
        for t, c, _ in chart_series)

    # ---- main table --------------------------------------------------------
    rows = ""
    for i, (t, e) in enumerate(ranked, 1):
        runs = hist_today.get(t, [])
        vals = [r["overall"] for r in runs]
        delta = vals[-1] - vals[0] if len(vals) > 1 else 0
        dcls = "up" if delta > 0 else "down" if delta < 0 else "muted"
        rating = e.get("rating", "?")
        dte = e.get("days_to_earnings")
        tier = e.get("tier")
        rows += (
            f"<tr><td class='muted'>{i}</td><td><b>{esc(t)}</b></td>"
            f"<td class='num'>{e.get('overall', '—')}</td>"
            f"<td class='num'>{e.get('timing', '—')}</td>"
            f"<td class='num'>{e.get('blend', '—')}</td>"
            f"<td class='num'>{e.get('conviction', '—')}</td>"
            f"<td><span class='pill' style='background:{BAND_COLORS.get(rating, '#9aa0a6')}'>"
            f"{esc(rating)}</span></td>"
            f"<td style='color:{TIER_COLORS.get(tier, 'inherit')};font-weight:600'>{esc(tier or '—')}</td>"
            f"<td class='num {dcls}'>{delta:+d}</td>"
            f"<td>{sparkline(vals)}</td>"
            f"<td class='num'>{dte if isinstance(dte, int) and dte >= 0 else '—'}</td>"
            f"<td class='num'>{e.get('confidence', '—')}%</td>"
            f"<td class='muted'>{esc(e.get('sector', '—'))}</td></tr>")

    # ---- earnings + payload queue + verdicts -------------------------------
    earn_html = "".join(
        f"<li><b>{esc(t)}</b> — {d} day{'s' if d != 1 else ''}</li>" for t, d in earnings_soon
    ) or "<li class='muted'>Nothing within 7 days.</li>"

    recent_payloads = "".join(
        f"<li><code>{esc(p.name)}</code></li>" for p in payloads[-8:][::-1]
    ) or "<li class='muted'>None generated yet.</li>"

    if recs:
        vrows = "".join(
            f"<li><b>{esc(r.get('ticker', '?'))}</b> {esc(r.get('rating', ''))} "
            f"<span class='muted'>@ {r.get('price_at_verdict', r.get('entry', '—'))} · "
            f"{esc(r.get('date', ''))}</span></li>"
            for r in recs[-10:][::-1])
    else:
        vrows = ("<li class='muted'>No committee verdicts recorded yet — after a Claude Pro "
                 "session, run <code>verdict.py add TICKER RATING</code> to start the "
                 "SPY-alpha loop.</li>")

    # ---- ops health ---------------------------------------------------------
    def freshness(name):
        p = BASE / name
        if not p.exists():
            return f"<li><code>{name}</code> <span class='down'>missing</span></li>"
        age = time.time() - p.stat().st_mtime
        txt = f"{age / 60:.0f} min ago" if age < 5400 else f"{age / 3600:.1f} h ago"
        return f"<li><code>{name}</code> <span class='muted'>updated {txt}</span></li>"

    ops = "".join(freshness(n) for n in
                  ("scores.json", "history.json", "alert_state.json"))
    try:
        import subprocess
        commit = subprocess.run(
            ["git", "log", "-1", "--format=%h · %s · %cr"],
            cwd=BASE, capture_output=True, text=True, timeout=5).stdout.strip()
        if commit:
            ops += f"<li>last commit <span class='muted'>{esc(commit)}</span></li>"
    except Exception:
        pass
    # monitor.log is gitignored and local-only — absent in CI runs, and its age
    # says nothing about the GH-Actions pipeline. Show the tail only if present.
    log_tail = ""
    logp = BASE / "monitor.log"
    if logp.exists():
        tail = logp.read_text().strip().splitlines()[-6:]
        log_tail = "".join(f"<div>{esc(l)}</div>" for l in tail)

    banner = (f"<div class='banner'>⚠ scores.json is {scores_age_min:.0f} min old during "
              f"market hours — the monitor pipeline may be stalled.</div>") if stale else ""

    page = f"""<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<meta http-equiv='refresh' content='300'>
<title>Stock Monitor Ecosystem</title>
<style>
:root{{--bg:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--series1:#2a78d6;
--up:#006300;--down:#d03b3b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0d0d0d;--surface:#1a1a19;--ink:#fff;
--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--border:rgba(255,255,255,.10);--series1:#3987e5;--up:#0ca30c;--down:#e66767}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 20px 60px}}
h1{{font-size:22px;margin:0}}h2{{font-size:15px;margin:0 0 12px;color:var(--ink2)}}
header{{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;
gap:8px;margin-bottom:18px}}
.stamp{{color:var(--muted);font-size:13px}}
.banner{{background:#d03b3b;color:#fff;padding:10px 14px;border-radius:8px;
margin-bottom:16px;font-weight:600}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
gap:12px;margin-bottom:22px}}
.tile,.card{{background:var(--surface);border:1px solid var(--border);
border-radius:10px;padding:14px 16px}}
.tlabel{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
.tvalue{{font-size:28px;font-weight:700;margin:2px 0}}
.denom{{font-size:15px;color:var(--muted);font-weight:400}}
.tsub{{font-size:12px;color:var(--ink2);min-height:16px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:22px}}
.grid3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
gap:14px;margin-bottom:22px}}
@media(max-width:800px){{.grid2{{grid-template-columns:1fr}}}}
.card{{margin-bottom:0}}
.dist-row{{display:grid;grid-template-columns:170px 1fr 52px;gap:10px;
align-items:center;margin:7px 0}}
.dist-name{{font-size:13px;display:flex;align-items:center;gap:7px}}
.dist-n{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
.bar-track{{background:var(--grid);border-radius:4px;height:12px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px;min-width:2px}}
.dot{{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}}
.leg{{margin-right:16px;font-size:13px;color:var(--ink2)}}
.leg .dot{{margin-right:5px}}
.grid{{stroke:var(--grid);stroke-width:1}}
.axis{{stroke:var(--axis);stroke-width:1}}
.tick{{fill:var(--muted);font-size:11px}}
.dlabel{{font-size:12px;font-weight:700}}
table{{width:100%;border-collapse:collapse;background:var(--surface);
border:1px solid var(--border);border-radius:10px;overflow:hidden;font-size:13px}}
.tblwrap{{overflow-x:auto;margin-bottom:22px;border-radius:10px}}
th{{text-align:left;padding:9px 10px;color:var(--muted);font-size:11px;
text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--grid);
position:sticky;top:0;background:var(--surface)}}
td{{padding:7px 10px;border-bottom:1px solid var(--grid)}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:color-mix(in srgb,var(--series1) 6%,transparent)}}
.num{{font-variant-numeric:tabular-nums;text-align:right}}
th.num{{text-align:right}}
.pill{{color:#fff;padding:2px 9px;border-radius:10px;font-size:11px;font-weight:600;
white-space:nowrap}}
.muted{{color:var(--muted)}}
.up{{color:var(--up);font-weight:600}}.down{{color:var(--down);font-weight:600}}
ul{{margin:0;padding-left:2px;list-style:none}}
li{{padding:4px 0;border-bottom:1px solid var(--grid)}}
li:last-child{{border:none}}
code{{font-size:12px;background:var(--grid);padding:1px 5px;border-radius:4px}}
.log{{font:11px/1.6 ui-monospace,monospace;color:var(--ink2);overflow-x:auto;
white-space:pre}}
</style></head><body><div class='wrap'>
<header><h1>📈 Stock Monitor Ecosystem</h1>
<span class='stamp'>Generated {now.strftime('%a %b %d, %Y · %I:%M %p PT')} · auto-refreshes every 5 min</span></header>
{banner}
<div class='tiles'>{kpis}</div>
<div class='card' style='margin-bottom:22px'>
<h2>Intraday overall score — top 5 ranked</h2>{legend and f"<div style='margin-bottom:8px'>{legend}</div>"}{chart}</div>
<div class='grid2'>
<div class='card'><h2>Rating distribution</h2>{dist}</div>
<div class='card'><h2>Average overall by sector</h2>{sec_html}</div>
</div>
<h2 style='margin-bottom:10px'>Full ledger — {len(ranked)} tickers, ranked by overall</h2>
<div class='tblwrap'><table><thead><tr>
<th>#</th><th>Ticker</th><th class='num'>Overall /110</th><th class='num'>Timing /100</th>
<th class='num'>Blend</th><th class='num'>Conviction</th><th>Rating</th><th>Tier</th>
<th class='num'>Δ today</th><th>Today</th><th class='num'>Earnings (d)</th>
<th class='num'>Conf.</th><th>Sector</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class='grid3'>
<div class='card'><h2>⏰ Earnings within 7 days</h2><ul>{earn_html}</ul></div>
<div class='card'><h2>📋 Latest committee payloads</h2><ul>{recent_payloads}</ul></div>
<div class='card'><h2>⚖️ Committee verdicts</h2><ul>{vrows}</ul></div>
</div>
<div class='grid2' style='margin-top:14px'>
<div class='card'><h2>🩺 Pipeline health</h2><ul>{ops}</ul>
<p class='muted' style='font-size:12px'>Runs in GitHub Actions (cron-job.org dispatch):
monitor every 15 min · pulse hourly · close 13:35 PT · weekly Friday.
State commits sync to this Mac via launchd.</p></div>
<div class='card'><h2>📜 monitor.log — local runs only</h2>
<div class='log'>{log_tail or "<span class='muted'>No local log (pipeline runs in CI).</span>"}</div></div>
</div>
</div></body></html>"""
    OUT.write_text(page)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    render()
