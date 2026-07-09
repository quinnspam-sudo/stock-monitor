"""Call-option layer — earnings-catalyst call buying on gate-open names.

Runs ONLY on tickers that already pass the stock pipeline's actionable-buy
gate (Buy signal + earnings ≤10 business days + strict positivity pass).
The stock algorithm decides WHETHER the setup is bullish; this module
decides WHICH call expresses it, and whether the premium is worth paying.

Selection policy (earnings-catalyst style, per Quinn 2026-07-09):
  - Expiry: 3-6 weeks PAST the earnings date — owning post-event time value
    is the standard defense against IV crush (implied vol collapses on the
    print; near-dated calls eat the full collapse).
  - Strike: Black-Scholes delta 0.50-0.60 — slightly ITM/ATM. High enough
    delta that the trade is a directional bet, not a lottery ticket.
  - Liquidity: open interest >= 100, bid/ask spread <= 10% of mid — wide
    spreads are a hidden entry+exit tax that dwarfs commission.
  - Premium richness: contract IV vs the stock's 30-day realized vol.
    IV/RV > 1.6 means paying a fat volatility premium into the event.
  - Breakeven feasibility: the % move needed to break even at expiry,
    measured in sigmas of the option's own implied move (IV * sqrt(T)).
    <=0.5 sigma is comfortable; >0.9 sigma means the call only pays on an
    outsized reaction. The stock's average earnings-day move (last 4
    prints) is reported as context for the committee, not hard-gated —
    a to-expiry breakeven can't fairly be gated on a 1-day move.

Score /100: liquidity 25, premium richness 25, breakeven 30, delta fit 20.
STRICT pass bar 65. Recommend-only — never executes, same as stocks.
"""
import math
from datetime import date, datetime, timedelta

RISK_FREE = 0.04
MIN_EXPIRY_BUFFER_D = 21   # expiry at least 3 weeks past earnings
MAX_EXPIRY_BUFFER_D = 45   # ... and at most ~6 weeks past
DELTA_LO, DELTA_HI = 0.50, 0.60
# High-conviction policy (Quinn, 2026-07-09): tightened from the launch values
# (OI 100 / spread 10% / IV_RV 1.6 / 0.9 sigma / bar 65). Fewer, better ideas.
MIN_OI = 500
MAX_SPREAD_PCT = 0.05
MAX_IV_RV = 1.2
MAX_BREAKEVEN_SIGMA = 0.6
PASS_SCORE = 80
MAX_TERM_INVERSION = 1.10  # chosen-expiry IV may exceed front-month IV by at most 10%


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_delta(spot, strike, t_years, iv):
    """Black-Scholes call delta. Good enough for strike targeting."""
    if not all(isinstance(v, (int, float)) and v > 0 for v in (spot, strike, t_years, iv)):
        return None
    d1 = (math.log(spot / strike) + (RISK_FREE + iv * iv / 2) * t_years) / (iv * math.sqrt(t_years))
    return _norm_cdf(d1)


def realized_vol_30d(hist_close):
    """Annualized 30-day realized volatility from a Close series."""
    if hist_close is None or len(hist_close) < 31:
        return None
    rets = hist_close.pct_change().dropna().tail(30)
    if len(rets) < 20:
        return None
    return float(rets.std()) * math.sqrt(252)


def avg_earnings_move(tk, hist_close):
    """Average absolute next-close move across the last 4 earnings prints."""
    try:
        ed = tk.earnings_dates
        if ed is None or not len(ed) or hist_close is None or not len(hist_close):
            return None
        idx = hist_close.index.tz_localize(None)
        moves = []
        past = [d for d in ed.index if d.tz_localize(None) < datetime.now()][:4]
        for d in past:
            d0 = d.tz_localize(None).normalize()
            after = [i for i, ts in enumerate(idx) if ts.normalize() > d0]
            if not after or after[0] == 0:
                continue
            i = after[0]
            moves.append(abs(hist_close.iloc[i] / hist_close.iloc[i - 1] - 1))
        return sum(moves) / len(moves) if moves else None
    except Exception:
        return None


def _clamp100(x):
    return max(0, min(100, round(x)))


def _safe_int(v):
    """yfinance chains use NaN for missing volume/OI — NaN is truthy, so
    `v or 0` doesn't catch it."""
    return int(v) if isinstance(v, (int, float)) and v == v else 0


def pick_contract(tk, spot, earnings_date):
    """Choose the best call per policy. Returns (contract dict | None, notes)."""
    notes = []
    try:
        expiries = tk.options or ()
    except Exception:
        return None, ["option chain unavailable"]
    if not expiries:
        return None, ["no listed options"]
    lo = earnings_date + timedelta(days=MIN_EXPIRY_BUFFER_D)
    hi = earnings_date + timedelta(days=MAX_EXPIRY_BUFFER_D)
    window = [e for e in expiries if lo <= date.fromisoformat(e) <= hi]
    if not window:
        # fall back to the first expiry past the minimum buffer
        late = [e for e in expiries if date.fromisoformat(e) >= lo]
        if not late:
            return None, [f"no expiry ≥{MIN_EXPIRY_BUFFER_D}d past earnings ({earnings_date})"]
        window = late[:1]
        notes.append(f"no expiry inside the 3-6wk post-earnings window; using {window[0]}")

    best = None
    for exp in window:
        try:
            chain = tk.option_chain(exp).calls
        except Exception:
            continue
        t_years = max((date.fromisoformat(exp) - date.today()).days, 1) / 365
        for _, row in chain.iterrows():
            iv = row.get("impliedVolatility")
            bid, ask = row.get("bid"), row.get("ask")
            if not (isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and ask > 0 and bid > 0):
                continue
            delta = bs_delta(spot, row["strike"], t_years, iv)
            if delta is None or not (DELTA_LO - 0.08 <= delta <= DELTA_HI + 0.08):
                continue
            mid = (bid + ask) / 2
            cand = {
                "expiry": exp, "strike": float(row["strike"]), "delta": round(delta, 3),
                "bid": float(bid), "ask": float(ask), "mid": round(mid, 2),
                "iv": round(float(iv), 4) if isinstance(iv, (int, float)) else None,
                "open_interest": _safe_int(row.get("openInterest")),
                "volume": _safe_int(row.get("volume")),
                "spread_pct": round((ask - bid) / mid, 4),
                "contract": row.get("contractSymbol"),
                "breakeven_move": round((row["strike"] + mid) / spot - 1, 4),
                "t_years": round(t_years, 4),
            }
            # prefer: inside the delta band, then most liquid
            in_band = DELTA_LO <= delta <= DELTA_HI
            key = (in_band, cand["open_interest"])
            if best is None or key > best[0]:
                best = (key, cand)
    if best is None:
        return None, notes + ["no quoted call near the 0.50-0.60 delta band"]
    return best[1], notes


def front_month_iv(tk, spot, earnings_date, chosen_expiry):
    """ATM IV of the nearest expiry that still contains the earnings event.
    Healthy pre-earnings term structure: front IV > back IV (the crush lives
    in the front month, not in our post-event expiry). Returns None on gaps."""
    try:
        fronts = [e for e in (tk.options or ())
                  if earnings_date <= date.fromisoformat(e) < date.fromisoformat(chosen_expiry)]
        if not fronts:
            return None
        chain = tk.option_chain(fronts[0]).calls
        chain = chain[(chain["impliedVolatility"] > 0.01)]
        if not len(chain):
            return None
        atm = chain.iloc[(chain["strike"] - spot).abs().argsort()[:1]]
        return float(atm["impliedVolatility"].iloc[0])
    except Exception:
        return None


def evaluate(tk, spot, earnings_date, hist_close=None):
    """Full call-idea evaluation for an already gate-open ticker.
    Never raises. Returns dict with contract, score, pass/fail, reasons."""
    out = {"contract": None, "score": None, "actionable": False, "reasons": [], "context": {}}
    if not isinstance(spot, (int, float)) or spot <= 0 or earnings_date is None:
        out["reasons"].append("missing spot price or earnings date")
        return out
    try:
        if hist_close is None:
            hist_close = tk.history(period="1y")["Close"]
    except Exception:
        hist_close = None

    c, notes = pick_contract(tk, spot, earnings_date)
    out["reasons"].extend(notes)
    if c is None:
        return out
    out["contract"] = c

    rv = realized_vol_30d(hist_close)
    em = avg_earnings_move(tk, hist_close)
    iv_rv = (c["iv"] / rv) if c["iv"] and rv else None
    # breakeven distance in units of the implied 1-sigma move to expiry
    sigma_move = c["iv"] * math.sqrt(c["t_years"]) if c["iv"] else None
    be_sigma = (c["breakeven_move"] / sigma_move) if sigma_move else None
    fiv = front_month_iv(tk, spot, earnings_date, c["expiry"])
    term_ratio = (c["iv"] / fiv) if c["iv"] and fiv else None
    out["context"] = {"realized_vol_30d": round(rv, 4) if rv else None,
                      "iv_rv_ratio": round(iv_rv, 2) if iv_rv else None,
                      "avg_earnings_move": round(em, 4) if em else None,
                      "breakeven_sigma": round(be_sigma, 2) if be_sigma else None,
                      "front_month_iv": round(fiv, 4) if fiv else None,
                      "term_ratio": round(term_ratio, 2) if term_ratio else None}

    # --- component scores ---
    liq = _clamp100((min(c["open_interest"], 1000) / 1000) * 60
                    + (1 - min(c["spread_pct"], 0.25) / 0.25) * 40)
    rich = _clamp100(100 - max(0, (iv_rv - 1.0)) / (MAX_IV_RV - 1.0) * 70) if iv_rv else None
    brk = _clamp100(100 - max(0, be_sigma - 0.4) / (MAX_BREAKEVEN_SIGMA - 0.4) * 60) \
        if be_sigma is not None else None
    dfit = _clamp100(100 - abs(c["delta"] - (DELTA_LO + DELTA_HI) / 2) * 400)

    parts = [(liq, 25), (rich, 25), (brk, 30), (dfit, 20)]
    avail = [(v, w) for v, w in parts if v is not None]
    score = round(sum(v * w for v, w in avail) / sum(w for _, w in avail)) if avail else None
    out["score"] = score
    out["components"] = {"liquidity": liq, "premium_richness": rich,
                         "breakeven": brk, "delta_fit": dfit}

    if c["open_interest"] < MIN_OI:
        out["reasons"].append(f"open interest {c['open_interest']} < {MIN_OI}")
    if c["spread_pct"] > MAX_SPREAD_PCT:
        out["reasons"].append(f"bid/ask spread {c['spread_pct']:.0%} > {MAX_SPREAD_PCT:.0%} of mid")
    if iv_rv and iv_rv > MAX_IV_RV:
        out["reasons"].append(f"IV/RV {iv_rv:.2f} > {MAX_IV_RV} — premium too rich into the event")
    if be_sigma is not None and be_sigma > MAX_BREAKEVEN_SIGMA:
        out["reasons"].append(f"breakeven {c['breakeven_move']:.1%} is {be_sigma:.2f} sigma of the "
                              f"implied move (max {MAX_BREAKEVEN_SIGMA}) — needs an outsized reaction")
    if term_ratio is not None and term_ratio > MAX_TERM_INVERSION:
        out["reasons"].append(f"term structure inverted: our expiry IV is {term_ratio:.2f}x the "
                              f"front month — we'd be the ones holding the crush premium")
    if score is not None and score < PASS_SCORE:
        out["reasons"].append(f"call score {score}/100 below bar {PASS_SCORE}")

    out["actionable"] = (score is not None and score >= PASS_SCORE
                         and c["open_interest"] >= MIN_OI
                         and c["spread_pct"] <= MAX_SPREAD_PCT
                         and not (iv_rv and iv_rv > MAX_IV_RV)
                         and not (be_sigma is not None and be_sigma > MAX_BREAKEVEN_SIGMA)
                         and not (term_ratio is not None and term_ratio > MAX_TERM_INVERSION))
    return out


def describe(idea, ticker=""):
    """One-line human summary of a call idea (for Discord)."""
    c = idea.get("contract")
    if not c:
        return f"{ticker}: no viable call contract — {'; '.join(idea.get('reasons') or ['n/a'])}"
    ctx = idea.get("context", {})
    return (f"{ticker} {c['expiry']} ${c['strike']:g}C @ ~${c['mid']:.2f} "
            f"(Δ{c['delta']:.2f}, OI {c['open_interest']}, spread {c['spread_pct']:.0%}, "
            f"IV {c['iv']:.0%}" + (f", IV/RV {ctx['iv_rv_ratio']}" if ctx.get("iv_rv_ratio") else "")
            + f", breakeven {c['breakeven_move']:+.1%}"
            + (f" vs avg earnings move {ctx['avg_earnings_move']:.1%}" if ctx.get("avg_earnings_move") else "")
            + f") — call score {idea.get('score')}/100"
            + (" ✅" if idea.get("actionable") else " ⚠️ " + "; ".join(idea.get("reasons") or [])))


def render(idea):
    """Committee-payload markdown block."""
    if not idea:
        return "  - Call-option screen unavailable this run (treat as GAPPED)"
    c = idea.get("contract")
    if not c:
        return f"  - No viable call contract: {'; '.join(idea.get('reasons') or ['n/a'])}"
    comp = idea.get("components", {})
    ctx = idea.get("context", {})
    lines = [
        f"  - Proposed contract: {c.get('contract')} — {c['expiry']} ${c['strike']:g} call, "
        f"mid ${c['mid']:.2f} (bid {c['bid']:.2f}/ask {c['ask']:.2f})",
        f"  - Delta {c['delta']:.2f} | OI {c['open_interest']} | volume {c['volume']} | "
        f"spread {c['spread_pct']:.1%} of mid",
        f"  - IV {c['iv']:.1%} vs 30d realized {ctx.get('realized_vol_30d') or 'GAPPED'} "
        f"(IV/RV {ctx.get('iv_rv_ratio') or 'GAPPED'}; >={MAX_IV_RV} = too rich)",
        f"  - Breakeven at expiry: {c['breakeven_move']:+.1%} = {ctx.get('breakeven_sigma') or 'GAPPED'} sigma "
        f"of the implied move (max {MAX_BREAKEVEN_SIGMA}); avg earnings-day move for context: "
        f"{('%.1f%%' % (ctx['avg_earnings_move']*100)) if ctx.get('avg_earnings_move') else 'GAPPED'}",
        f"  - Term structure: our expiry IV vs front-month IV = "
        f"{ctx.get('term_ratio') or 'GAPPED'} (healthy <1.0 — crush belongs in the front month; "
        f"max {MAX_TERM_INVERSION})",
        f"  - Call score: {idea.get('score')}/100 (liquidity {comp.get('liquidity')}, "
        f"premium {comp.get('premium_richness')}, breakeven {comp.get('breakeven')}, "
        f"delta fit {comp.get('delta_fit')}; pass bar {PASS_SCORE})",
        f"  - CALL VERDICT: {'CANDIDATE — committee to confirm' if idea.get('actionable') else 'REJECTED'}"
        + (f" — {'; '.join(idea['reasons'])}" if idea.get("reasons") else ""),
    ]
    return "\n".join(lines)
