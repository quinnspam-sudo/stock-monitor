"""Committee payload engine.

Computes local proxy scores (11 categories, /110) from yfinance data, tracks them
in scores.json, and when a Phase 3 threshold is breached writes a consolidated
prompt payload to committee_prompts/ for manual pasting into Claude Pro.

Local scores are deterministic heuristics — a noise gate, not the committee's
verdict. The pasted payload lets the real committee (Claude) do the judgment.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

PACIFIC = ZoneInfo("America/Los_Angeles")

ROOT = Path(__file__).parent
LEDGER_PATH = ROOT / "scores.json"
PROMPTS_DIR = ROOT / "committee_prompts"

# Phase 3 trigger thresholds
OVERALL_DELTA = 8      # /110
TIMING_DELTA = 15      # /100
CONFIDENCE_DELTA = 10  # percentage points

GAPPED_SOURCES = [
    "Congressional trades", "Options skew / flow",
    "Institutional flow (13F deltas)", "SEC filing stream", "Earnings call transcripts",
    "Credit ratings",
]

HISTORY_PATH = ROOT / "history.json"

RATING_BANDS = [(88, "Strong Buy"), (75, "Buy"), (60, "Watch"), (45, "Hold"), (30, "Reduce"), (0, "Sell")]


def market_open_today():
    """True if NYSE traded today — guards cron runs on market holidays.

    Uses Pacific time explicitly rather than naive datetime.now(): on GitHub
    Actions the runner's system tz is UTC, so a naive "today" would be wrong
    for roughly a third of the day (any UTC time before ~13:00, i.e. still
    the prior evening in PT) — e.g. a manual/off-schedule trigger in early
    UTC morning would compare SPY's last close against the wrong calendar day.
    """
    try:
        h = yf.Ticker("SPY").history(period="5d")
        return h.index[-1].date() == datetime.now(PACIFIC).date()
    except Exception:
        return True  # fail open: better a wasted run than a missed session


def rating_for(overall):
    for floor, label in RATING_BANDS:
        if overall >= floor:
            return label
    return "Sell"


def append_history(ticker, cur):
    """Append this run's scores to history.json (used by the daily close summary)."""
    hist = json.loads(HISTORY_PATH.read_text()) if HISTORY_PATH.exists() else {}
    day = datetime.now().strftime("%Y-%m-%d")
    hist.setdefault(day, {}).setdefault(ticker, []).append({
        "time": datetime.now().strftime("%H:%M"),
        "overall": cur["overall"], "timing": cur["timing"],
        "confidence": cur["confidence"], "rating": rating_for(cur["overall"]),
    })
    # keep last 30 days
    for old in sorted(hist)[:-30]:
        del hist[old]
    HISTORY_PATH.write_text(json.dumps(hist, indent=2))


def load_ledger():
    return json.loads(LEDGER_PATH.read_text()) if LEDGER_PATH.exists() else {}


def save_ledger(ledger):
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2))


def thematic_concentration(cfg):
    """User-defined theme concentration (config.json "categories") vs raw
    yfinance sector — the themes are what the watchlist was actually built
    around (e.g. "AI Infrastructure"), which is more decision-relevant than
    yfinance's generic "Technology" bucket."""
    categories = cfg.get("categories", {})
    watchlist = cfg.get("watchlist", [])
    covered = {t for names in categories.values() for t in names}
    uncategorized = [t for t in watchlist if t not in covered]
    if uncategorized:
        categories = {**categories, "Uncategorized": uncategorized}
    total = len(watchlist) or 1
    return [f"{theme}: {len(names)} ({len(names) / total:.0%})"
            for theme, names in sorted(categories.items(), key=lambda kv: -len(kv[1]))]


def _clamp(x, lo=1, hi=10):
    return max(lo, min(hi, x))


def gather(ticker, timing_score):
    """Pull yfinance data and compute local proxy category scores."""
    tk = yf.Ticker(ticker)
    info = tk.info or {}

    def g(key):
        v = info.get(key)
        return v if isinstance(v, (int, float)) else None

    fields = {
        "forwardPE": g("forwardPE"), "trailingPE": g("trailingPE"),
        "enterpriseToEbitda": g("enterpriseToEbitda"), "enterpriseToRevenue": g("enterpriseToRevenue"),
        "pegRatio": g("trailingPegRatio"), "freeCashflow": g("freeCashflow"),
        "operatingCashflow": g("operatingCashflow"), "totalRevenue": g("totalRevenue"),
        "revenueGrowth": g("revenueGrowth"), "earningsGrowth": g("earningsGrowth"),
        "grossMargins": g("grossMargins"), "operatingMargins": g("operatingMargins"),
        "profitMargins": g("profitMargins"), "ebitdaMargins": g("ebitdaMargins"),
        "debtToEquity": g("debtToEquity"), "currentRatio": g("currentRatio"),
        "totalCash": g("totalCash"), "totalDebt": g("totalDebt"),
        "returnOnEquity": g("returnOnEquity"), "returnOnAssets": g("returnOnAssets"),
        "beta": g("beta"), "recommendationMean": g("recommendationMean"),
        "targetMeanPrice": g("targetMeanPrice"), "currentPrice": g("currentPrice"),
        "heldPercentInstitutions": g("heldPercentInstitutions"),
        "numberOfAnalystOpinions": g("numberOfAnalystOpinions"),
    }

    fpe, rg, gm, om, pm = (fields[k] for k in
                           ("forwardPE", "revenueGrowth", "grossMargins", "operatingMargins", "profitMargins"))
    fcf, rev = fields["freeCashflow"], fields["totalRevenue"]
    fcf_margin = (fcf / rev) if fcf and rev else None
    de, cr = fields["debtToEquity"], fields["currentRatio"]
    roe, beta, rec = fields["returnOnEquity"], fields["beta"], fields["recommendationMean"]

    cats = {
        "Valuation": _clamp(round(10 - (fpe - 10) / 5)) if fpe and fpe > 0 else 5,
        "Cash Generation": _clamp(round(fcf_margin * 33)) if fcf_margin is not None else 5,
        "Growth": _clamp(round(3 + (rg or 0) * 25)) if rg is not None else 5,
        "Revenue Visibility": 5,  # GAPPED — no recurring-revenue data in yfinance
        "Margin Quality": _clamp(round((om or 0) * 25 + 2)) if om is not None else 5,
        "Balance Sheet": _clamp(round(10 - (de or 0) / 30)) if de is not None else 5,
        "Capital Allocation": _clamp(round(2 + (roe or 0) * 20)) if roe is not None else 5,
        "Macro Exposure": _clamp(round(10 - abs((beta or 1) - 1) * 5)) if beta is not None else 5,
        "Competitive Moat": _clamp(round((gm or 0) * 12)) if gm is not None else 5,
        "Analyst Sentiment": _clamp(round(12 - rec * 2.2)) if rec else 5,
        "Technical Position": _clamp(round(timing_score / 10)),
    }
    # Which categories fell back to the neutral default (5) because their source
    # field was missing, vs genuinely computed a 5 — the committee needs to know
    # which proxy scores are estimates, not just the aggregate confidence %.
    cats_defaulted = {
        "Valuation": not (fpe and fpe > 0),
        "Cash Generation": fcf_margin is None,
        "Growth": rg is None,
        "Revenue Visibility": True,
        "Margin Quality": om is None,
        "Balance Sheet": de is None,
        "Capital Allocation": roe is None,
        "Macro Exposure": beta is None,
        "Competitive Moat": gm is None,
        "Analyst Sentiment": rec is None,
        "Technical Position": False,
    }
    overall = sum(cats.values())

    sector = info.get("sector") or "Unknown"
    industry = info.get("industry") or "Unknown"

    # Upcoming earnings date (best-effort)
    days_to_earnings = None
    earnings_date = None
    try:
        cal = tk.calendar or {}
        dates = cal.get("Earnings Date") or []
        if dates:
            earnings_date = dates[0]
            days_to_earnings = (dates[0] - datetime.now().date()).days
    except Exception:
        pass

    # Earnings gate: actionable-BUY window + positivity prediction (never fatal)
    import earnings_gate as _egate
    try:
        gate = _egate.evaluate(tk, info, earnings_date)
    except Exception:
        gate = None

    # Call-option layer: only evaluated when the gate is open — option-chain
    # fetches are heavy, and a call idea is meaningless without the catalyst.
    call_idea = None
    if gate and gate.get("actionable"):
        import calls as _calls
        try:
            call_idea = _calls.evaluate(tk, info.get("currentPrice"), earnings_date)
        except Exception:
            call_idea = None

    # Supplementary context yfinance can provide (best-effort; never fatal)
    news = []
    try:
        for item in (tk.news or [])[:5]:
            c = item.get("content", item)
            title = c.get("title")
            if title:
                news.append(f"{title} ({(c.get('pubDate') or '')[:10]})")
    except Exception:
        pass
    insiders = []
    try:
        df = tk.insider_transactions
        if df is not None and len(df):
            for _, row in df.head(5).iterrows():
                insiders.append(f"{row.get('Insider', '?')} — {row.get('Text', row.get('Transaction', '?'))}"
                                f" ({str(row.get('Start Date', ''))[:10]})")
    except Exception:
        pass

    present = sum(1 for v in fields.values() if v is not None)
    confidence = round(present / len(fields) * 70)  # cap at 70% — GAPPED sources penalize the rest

    return {"fields": fields, "categories": cats, "categories_defaulted": cats_defaulted,
            "overall": overall, "timing": timing_score, "confidence": confidence,
            "rating": rating_for(overall), "news": news, "insiders": insiders,
            "sector": sector, "industry": industry, "days_to_earnings": days_to_earnings,
            "earnings_gate": gate, "call_idea": call_idea}


def check_triggers(prev, cur):
    """Return list of breached Phase 3 rules (empty = suppress, no payload)."""
    if prev is None:
        return ["Initial evaluation — no prior ledger entry"]
    reasons = []
    if abs(cur["overall"] - prev["overall"]) >= OVERALL_DELTA:
        reasons.append(f"Overall score Δ {cur['overall'] - prev['overall']:+d} (threshold ±{OVERALL_DELTA})")
    if abs(cur["timing"] - prev["timing"]) >= TIMING_DELTA:
        reasons.append(f"Timing score Δ {cur['timing'] - prev['timing']:+d} (threshold ±{TIMING_DELTA})")
    if abs(cur["confidence"] - prev["confidence"]) >= CONFIDENCE_DELTA:
        reasons.append(f"Confidence Δ {cur['confidence'] - prev['confidence']:+d}pp (threshold ±{CONFIDENCE_DELTA})")
    prev_rating = prev.get("rating")
    if prev_rating and prev_rating != cur["rating"]:
        reasons.append(f"Rating change: {prev_rating} → {cur['rating']}")
    dte, prev_dte = cur.get("days_to_earnings"), prev.get("days_to_earnings")
    if dte is not None and 0 <= dte <= 2 and (prev_dte is None or prev_dte > 2):
        reasons.append(f"Earnings imminent: {dte} day(s) out — pre-earnings committee review")
    gate, prev_gate = cur.get("earnings_gate") or {}, prev.get("earnings_gate") or {}
    if gate.get("actionable") and not prev_gate.get("actionable"):
        reasons.append(
            f"Earnings gate OPENED — earnings in {gate.get('bdays_to_earnings')} business day(s), "
            f"positivity {gate.get('positivity')}/100, beat streak "
            f"{gate.get('beats')}/{gate.get('beats_n')} — buy decision is now actionable")
    return reasons


def payload_worthy(prev, cur, reasons):
    """Gate-aware payload policy: Quinn's paste time is the scarce resource, so
    a full committee payload is only written when a decision is actually live.
    Everything else gets digested into a single updates-channel line instead.

    Worthy: earnings inside the 10-business-day window (buy decisions possible,
    and pre-earnings reviews of anything held), first-ever evaluation (one-time
    baseline), or an exit-side rating move (out of Buy/Strong Buy, or into
    Reduce/Sell) — sell decisions don't wait for an earnings window.
    """
    if (cur.get("earnings_gate") or {}).get("in_window"):
        return True
    if prev is None:
        return True
    prev_r, cur_r = prev.get("rating"), cur.get("rating")
    if prev_r and prev_r != cur_r and (
            prev_r in ("Buy", "Strong Buy") or cur_r in ("Reduce", "Sell")):
        return True
    return False


def check_rank_triggers(ledger, current_scores, top_n=5):
    """Detect entries/exits of the top-N ranked opportunities. Returns {ticker: reason}."""
    prev_order = [t for t, _ in sorted(((t, v["overall"]) for t, v in ledger.items() if "overall" in v),
                                       key=lambda x: -x[1])]
    new_order = [t for t, _ in sorted(current_scores.items(), key=lambda x: -x[1])]
    if not prev_order:
        return {}
    prev_rank = {t: i + 1 for i, t in enumerate(prev_order)}
    new_rank = {t: i + 1 for i, t in enumerate(new_order)}
    out = {}
    # Hysteresis: require crossing a one-slot buffer so boundary jitter doesn't churn
    for t in new_rank:
        pr, nr = prev_rank.get(t), new_rank[t]
        if pr is None:
            continue
        if nr <= top_n and pr > top_n + 1:
            out[t] = f"Entered Top {top_n} ranked opportunities (rank {pr} → {nr})"
        elif pr <= top_n and nr > top_n + 1:
            out[t] = f"Exited Top {top_n} ranked opportunities (rank {pr} → {nr})"
    return out


def write_payload(ticker, cur, prev, reasons, kind="Standard"):
    """Write a consolidated committee prompt payload file; return its path."""
    PROMPTS_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    path = PROMPTS_DIR / f"{now:%Y-%m-%d_%H%M}_{ticker}_{kind.lower()}.md"

    defaulted = cur.get("categories_defaulted", {})
    cat_lines = "\n".join(
        f"  - {k}: {v}/10" + ("  [ESTIMATE — source data missing, do not trust]" if defaulted.get(k) else "")
        for k, v in cur["categories"].items()
    )
    n_defaulted = sum(1 for v in defaulted.values() if v)
    field_lines = "\n".join(f"  - {k}: {v}" for k, v in cur["fields"].items() if v is not None)
    missing = [k for k, v in cur["fields"].items() if v is None]
    gap_lines = "\n".join(f"  - {s}: Data Status: GAPPED" for s in GAPPED_SOURCES + missing)
    if cur.get("factors"):
        import factors as _factors
        factor_block = _factors.render(cur["factors"])
    else:
        factor_block = "  - Factor screen unavailable this run (treat as GAPPED)"
    import earnings_gate as _egate
    gate_block = _egate.render(cur.get("earnings_gate"))
    call_block = ""
    if cur.get("call_idea") is not None:
        import calls as _calls
        call_block = ("\n## Call-option candidate (earnings-catalyst; committee should judge "
                      "premium vs expected move, not just direction)\n"
                      + _calls.render(cur["call_idea"]) + "\n")
    news_block = "\n".join(f"  - {n}" for n in cur.get("news", [])) or "  - none available"
    insider_block = "\n".join(f"  - {i}" for i in cur.get("insiders", [])) or "  - none available (treat as GAPPED)"
    prev_block = (
        f"- Previous Overall Score: {prev['overall']}/110\n"
        f"- Previous Timing Score: {prev['timing']}/100\n"
        f"- Previous Confidence: {prev['confidence']}%\n"
        f"- Previous evaluation date: {prev['date']}"
    ) if prev else "- No prior evaluation on record (initial run)."

    path.write_text(f"""# COMMITTEE DATA PAYLOAD — {ticker} ({kind})
Generated: {now:%Y-%m-%d %H:%M} local | Source: stock-monitor local daemon
Instructions: Paste this payload into the Investment Committee session (Phase 1-4
protocol already loaded). Run the 9-member committee, score all 11 categories with
justifications, and output the matching Template.

## Company profile
- Sector: {cur.get('sector', 'Unknown')} | Industry: {cur.get('industry', 'Unknown')}
- Next earnings: {'in ' + str(cur['days_to_earnings']) + ' day(s)' if cur.get('days_to_earnings') is not None else 'Data Status: GAPPED'}

## Trigger(s) breached
{chr(10).join('- ' + r for r in reasons)}

## Prior ledger state
{prev_block}

## Local proxy scores (deterministic noise gate — NOT the committee verdict)
- Overall (proxy): {cur['overall']}/110 → local rating band: {cur.get('rating', rating_for(cur['overall']))}
- Timing: {cur['timing']}/100
- Data-completeness confidence (proxy): {cur['confidence']}%
- Category proxies ({n_defaulted}/{len(defaulted)} are ESTIMATES from missing data — weigh accordingly):
{cat_lines}

## Earnings gate (actionable-BUY policy: earnings within 10 business days AND
## strict positivity pass — score >=70, >=3 signals, beat streak >=3/4. A Buy
## rating without this gate is thesis-only, NOT actionable; committee should
## confirm or veto the positivity call using transcript/guidance judgment)
{gate_block}
{call_block}
## Evidence-backed factor screen (mechanical; committee should weigh explicitly)
{factor_block}
  - Interpretation guide: Magic Formula = Greenblatt cheapness+quality rank within
    the monitored universe; F-Score 8-9 strong / 0-2 weak (Piotroski); PEG <= 1
    attractive per Lynch GARP (ignore for cyclicals); 6-12 mo momentum is the
    Carhart UMD factor; quality gates are Buffett-style quantitative tells.
    Graham Number/margin of safety is asset-and-earnings based (1934-era value
    investing) — expect it to look deeply "overvalued" for asset-light,
    high-multiple growth/tech names; that's the methodology working as
    designed, not a flaw, and should be weighted down for this watchlist's
    growth names accordingly. CANSLIM (O'Neil) is a 7-criterion growth+
    breakout+market-regime checklist, not a continuous score — read the
    per-criterion breakdown, not just the count. Dividend quality only
    applies to actual payers (GAPPED for non-payers, not penalized). Fama-
    French Size/Value tilts are descriptive only and deliberately excluded
    from the conviction blend (a small-cap/cheap-book-to-market tilt would
    bias against this watchlist's mega-cap growth names) — Profitability/
    Investment legs are folded into Quality Minus Junk (AQR-style) instead.
    Insider signal only means something as a cluster (3+ distinct buyers,
    zero sales in 90 days per Lakonishok & Lee) — a single insider trade is
    noise. Analyst revision momentum compares current-quarter/next-year EPS
    estimates to 90 days ago; the 52-week breakout check is O'Neil/Darvas-
    style and distinct from the 3-month-high check in the momentum score above.

## Raw data fields (yfinance)
{field_lines}

## Recent news headlines
{news_block}

## Recent insider transactions
{insider_block}

## Gapped data sources (penalize Confidence Score accordingly)
{gap_lines}
""")
    import obsidian
    obsidian.mirror_payload(path)
    return path
