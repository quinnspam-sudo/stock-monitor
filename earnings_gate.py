"""Earnings gate — actionable-BUY filter around upcoming earnings.

A stock is only surfaced as an actionable BUY when BOTH hold:
  1. Confirmed earnings within the next 10 US business days (weekends
     excluded; market holidays are not modeled — a known ~1-day slop).
  2. The Earnings Positivity Score predicts a positive report/call.

The positivity score (/100) blends five free-data signals, each backed by
published pre-earnings research:
  - Analyst EPS revision momentum, current quarter vs 90 days ago
    (Givoly & Lakonishok 1979: revisions drift, upgrades precede beats)
  - Earnings surprise history: beat streak + average surprise over the last
    4 reported quarters (Bernard & Thomas 1989 PEAD; beats persist —
    "earnings momentum")
  - Pre-earnings relative strength vs SPY over ~60 trading days
    (Frazzini & Lamont 2007 earnings-announcement premium; informed price
    action front-runs the print)
  - Recommendation upgrade/downgrade balance over the last 90 days
    (Womack 1996: analyst actions carry pre-announcement information)
  - Short interest level + month-over-month change (Boehmer, Jones & Zhang
    2008: high/rising short interest predicts negative surprises)

STRICT policy (per Quinn, 2026-07-09): gate passes only if score >= 70,
at least 3 of the 5 signals computed, AND the company beat estimates in
at least 3 of its last 4 reported quarters.

These are deterministic proxies — a noise gate, not the committee verdict.
"""
from datetime import date, timedelta

_SPY_CACHE = {}

PASS_SCORE = 70          # strict threshold /100
MIN_SIGNALS = 3          # of 5 must be computable
MIN_BEATS = 3            # of last 4 quarters (strict beat-streak requirement)
WINDOW_BDAYS = 10        # earnings must land within this many business days

WEIGHTS = {
    "revision_momentum": 0.30,
    "surprise_history": 0.30,
    "pre_earnings_momentum": 0.15,
    "recommendation_trend": 0.15,
    "short_interest": 0.10,
}


def _spy_close():
    """SPY 4-month closes, cached per-process (same run touches every ticker)."""
    if "h" not in _SPY_CACHE:
        try:
            import yfinance as yf
            _SPY_CACHE["h"] = yf.Ticker("SPY").history(period="4mo")["Close"]
        except Exception:
            _SPY_CACHE["h"] = None
    return _SPY_CACHE["h"]


def business_days_until(target, today=None):
    """Weekdays strictly after today, up to and including target.
    Holidays are not excluded (no free calendar source) — worst case the
    10-day window is off by one; acceptable for a gate this coarse."""
    today = today or date.today()
    if target is None or target < today:
        return None
    n, d = 0, today
    while d < target:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _clamp100(x):
    return max(0, min(100, round(x)))


def _sig_revision(tk):
    """Current-quarter EPS estimate now vs 90 days ago → 0-100 (50 = flat)."""
    trend = tk.eps_trend
    if trend is None or not len(trend):
        return None
    deltas = []
    for _, row in trend.iterrows():
        cur, ago = row.get("current"), row.get("90daysAgo")
        if cur and ago:
            deltas.append((cur - ago) / abs(ago))
    if not deltas:
        return None
    return _clamp100(50 + (sum(deltas) / len(deltas)) * 500)


def _sig_surprise(tk):
    """Last 4 reported quarters: beat count + avg surprise. Returns (score, beats, n)."""
    ed = tk.earnings_dates
    if ed is None or not len(ed):
        return None, None, 0
    reported = ed.dropna(subset=["Reported EPS", "EPS Estimate"]).head(4)
    if not len(reported):
        return None, None, 0
    beats = int((reported["Reported EPS"] > reported["EPS Estimate"]).sum())
    n = len(reported)
    surp = reported.get("Surprise(%)")
    avg_surp = float(surp.dropna().mean()) if surp is not None and len(surp.dropna()) else 0.0
    # beat rate carries 70 pts, average surprise magnitude the other 30
    score = _clamp100(beats / n * 70 + max(-1, min(1, avg_surp / 10)) * 30 + 15)
    return score, beats, n


def _sig_momentum(tk, spy_hist):
    """~60-trading-day return relative to SPY → 0-100 (50 = matches SPY)."""
    h = tk.history(period="4mo")["Close"]
    if len(h) < 40 or spy_hist is None or len(spy_hist) < 40:
        return None
    r = h.iloc[-1] / h.iloc[0] - 1
    spy_r = spy_hist.iloc[-1] / spy_hist.iloc[0] - 1
    return _clamp100(50 + (r - spy_r) * 250)


def _sig_recs(tk):
    """Upgrade vs downgrade balance, last ~90 days → 0-100 (50 = balanced)."""
    ud = tk.upgrades_downgrades
    if ud is None or not len(ud):
        return None
    try:
        recent = ud[ud.index >= (ud.index.max() - __import__("pandas").Timedelta(days=90))]
    except Exception:
        recent = ud.head(15)
    acts = recent.get("Action")
    if acts is None or not len(acts):
        return None
    ups = int((acts == "up").sum())
    downs = int((acts == "down").sum())
    if ups + downs == 0:
        return 50
    return _clamp100(50 + (ups - downs) / (ups + downs) * 40)


def _sig_short(info):
    """Short interest: low level + declining month-over-month is bullish."""
    spf = info.get("shortPercentOfFloat")
    if not isinstance(spf, (int, float)):
        return None
    score = 80 - min(spf, 0.20) * 300  # 1% float → 77, 10% → 50, 20%+ → 20
    ss, ssp = info.get("sharesShort"), info.get("sharesShortPriorMonth")
    if isinstance(ss, (int, float)) and isinstance(ssp, (int, float)) and ssp:
        chg = (ss - ssp) / ssp
        score -= max(-0.3, min(0.3, chg)) * 50  # rising shorts penalize, falling reward
    return _clamp100(score)


def evaluate(tk, info, earnings_date, spy_hist=None):
    """Full gate evaluation. Never raises; missing data degrades gracefully.

    Returns dict: {bdays_to_earnings, positivity, signals, beats, beats_n,
                   in_window, positivity_pass, actionable, reasons}
    """
    bdays = business_days_until(earnings_date)
    in_window = bdays is not None and 0 <= bdays <= WINDOW_BDAYS
    if spy_hist is None:
        spy_hist = _spy_close()

    signals, beats, beats_n = {}, None, 0
    try:
        signals["revision_momentum"] = _sig_revision(tk)
    except Exception:
        signals["revision_momentum"] = None
    try:
        signals["surprise_history"], beats, beats_n = _sig_surprise(tk)
    except Exception:
        signals["surprise_history"] = None
    try:
        signals["pre_earnings_momentum"] = _sig_momentum(tk, spy_hist)
    except Exception:
        signals["pre_earnings_momentum"] = None
    try:
        signals["recommendation_trend"] = _sig_recs(tk)
    except Exception:
        signals["recommendation_trend"] = None
    try:
        signals["short_interest"] = _sig_short(info or {})
    except Exception:
        signals["short_interest"] = None

    avail = {k: v for k, v in signals.items() if v is not None}
    positivity = None
    if avail:
        wsum = sum(WEIGHTS[k] for k in avail)
        positivity = round(sum(v * WEIGHTS[k] for k, v in avail.items()) / wsum)

    reasons = []
    if bdays is None:
        reasons.append("no confirmed upcoming earnings date")
    elif not in_window:
        reasons.append(f"earnings in {bdays} business days (window: ≤{WINDOW_BDAYS})")
    if len(avail) < MIN_SIGNALS:
        reasons.append(f"only {len(avail)}/{len(WEIGHTS)} positivity signals available (need ≥{MIN_SIGNALS})")
    if positivity is not None and positivity < PASS_SCORE:
        reasons.append(f"positivity {positivity}/100 below strict bar {PASS_SCORE}")
    if beats_n >= 1 and (beats or 0) < min(MIN_BEATS, beats_n):
        reasons.append(f"beat streak {beats}/{beats_n} quarters (strict bar: ≥{MIN_BEATS}/4)")
    elif beats_n == 0:
        reasons.append("no reported-quarter history to verify beat streak")

    positivity_pass = (positivity is not None and positivity >= PASS_SCORE
                       and len(avail) >= MIN_SIGNALS
                       and beats_n >= 1 and (beats or 0) >= min(MIN_BEATS, beats_n))
    return {
        "bdays_to_earnings": bdays,
        "positivity": positivity,
        "signals": signals,
        "beats": beats, "beats_n": beats_n,
        "in_window": in_window,
        "positivity_pass": positivity_pass,
        "actionable": in_window and positivity_pass,
        "reasons": reasons,
    }


def render(g):
    """Payload/markdown block for a gate result."""
    if not g:
        return "  - Earnings gate unavailable this run (treat as GAPPED)"
    sig_names = {"revision_momentum": "Analyst EPS revision momentum",
                 "surprise_history": "Earnings surprise history",
                 "pre_earnings_momentum": "Pre-earnings relative strength vs SPY",
                 "recommendation_trend": "Recommendation upgrades vs downgrades (90d)",
                 "short_interest": "Short interest level & trend"}
    lines = [f"  - Earnings in business days: {g['bdays_to_earnings'] if g['bdays_to_earnings'] is not None else 'GAPPED'}"
             f" (buy window: ≤{WINDOW_BDAYS})",
             f"  - Earnings Positivity Score: {g['positivity'] if g['positivity'] is not None else 'GAPPED'}/100"
             f" (strict pass bar {PASS_SCORE}, beat streak {g.get('beats')}/{g.get('beats_n')} last quarters)"]
    for k, label in sig_names.items():
        v = g["signals"].get(k)
        lines.append(f"    - {label}: {v if v is not None else 'GAPPED'}")
    lines.append(f"  - GATE VERDICT: {'ACTIONABLE BUY WINDOW' if g['actionable'] else 'NOT ACTIONABLE'}"
                 + (f" — {'; '.join(g['reasons'])}" if g["reasons"] else ""))
    return "\n".join(lines)
