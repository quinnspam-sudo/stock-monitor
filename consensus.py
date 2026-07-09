"""High-conviction consensus gate — the last line before a BUY alert.

Philosophy: there is no guaranteed profit in markets; what CAN be engineered
is agreement. Each methodology here has published evidence and multi-year
losing stretches; the consensus requires a SUPERMAJORITY of independent
systems to be bullish at once, with hard vetoes any single system can throw.
This trades alert frequency for hit rate — silence for weeks is expected
and is the system working, not failing.

Layers (all must hold for an actionable BUY):
  1. MARKET REGIME — SPY above both its 50d and 200d SMA (O'Neil's "M":
     3 of 4 stocks follow the market), and VIX below panic level. No
     stock-level signal overrides a hostile tape.
  2. SUPERMAJORITY VOTE — >=75% of the computable systems below must be
     bullish, with at least 6 systems computable:
       momentum (timing score), factor conviction tier, Piotroski F-Score,
       CANSLIM criteria count, analyst estimate revisions, insider signal,
       6-mo momentum sign, 52-wk breakout proximity, earnings positivity
       margin (above the strict bar, not just at it), quality gates.
  3. HARD VETOES — any one kills the alert regardless of the vote:
     F-Score <= 3 (Piotroski's shorts), estimate revisions worse than -2%,
     6-mo momentum below -10% (falling knife), VIX >= 28 / SPY below 200d.

Downstream of (not replacing) the earnings gate: this runs only on names
that already cleared Buy threshold + factor tier + earnings window +
positivity. Recommend-only, as ever.
"""
import yfinance as yf

_REGIME_CACHE = {}

VIX_MAX = 28.0
MIN_SYSTEMS = 6
SUPERMAJORITY = 0.75


def market_regime():
    """Cached per-process. Returns dict with pass/fail + the evidence."""
    if "r" in _REGIME_CACHE:
        return _REGIME_CACHE["r"]
    out = {"spy_above_50d": None, "spy_above_200d": None, "vix": None, "pass": False,
           "detail": ""}
    try:
        h = yf.Ticker("SPY").history(period="1y")["Close"]
        if len(h) >= 200:
            px = float(h.iloc[-1])
            out["spy_above_50d"] = px > float(h.rolling(50).mean().iloc[-1])
            out["spy_above_200d"] = px > float(h.rolling(200).mean().iloc[-1])
    except Exception:
        pass
    try:
        vh = yf.Ticker("^VIX").history(period="5d")["Close"]
        if len(vh):
            out["vix"] = round(float(vh.iloc[-1]), 1)
    except Exception:
        pass
    out["pass"] = bool(out["spy_above_50d"]) and bool(out["spy_above_200d"]) \
        and (out["vix"] is None or out["vix"] < VIX_MAX)
    out["detail"] = (f"SPY>{'50d' if out['spy_above_50d'] else '!50d'}"
                     f"/{'200d' if out['spy_above_200d'] else '!200d'}, "
                     f"VIX {out['vix'] if out['vix'] is not None else 'n/a'}"
                     f" (max {VIX_MAX})")
    _REGIME_CACHE["r"] = out
    return out


def evaluate(momentum_score, f, gate, supermajority=SUPERMAJORITY):
    """Vote across independent systems. f = factors dict, gate = earnings_gate.
    supermajority may be overridden by the alert tuner (0.60-0.80 band).
    Returns {votes, systems, ayes, pass, vetoes, regime, detail}."""
    f = f or {}
    gate = gate or {}
    votes = {}  # name -> True (bullish) / False (not) / None (not computable)

    votes["momentum_timing"] = momentum_score >= 75 if isinstance(momentum_score, (int, float)) else None

    conv = f.get("_conviction")  # (score, tier) injected by caller if available
    votes["factor_tier_high"] = (conv[1] == "HIGH") if conv else None

    fs = f.get("f_score")
    votes["piotroski"] = fs >= 6 if isinstance(fs, (int, float)) else None

    cs = f.get("canslim_score")
    votes["canslim"] = cs >= 5 if isinstance(cs, (int, float)) else None

    rev = f.get("analyst_revision")
    votes["estimate_revisions"] = rev > 0 if isinstance(rev, (int, float)) else None

    ins = f.get("insider_score")
    votes["insider_signal"] = ins >= 50 if isinstance(ins, (int, float)) else None

    m6 = f.get("mom_6m")
    votes["momentum_6m"] = m6 > 0 if isinstance(m6, (int, float)) else None

    bo = f.get("breakout_score")
    votes["breakout_52wk"] = bo >= 50 if isinstance(bo, (int, float)) else None

    pos = gate.get("positivity")
    votes["positivity_margin"] = pos >= 80 if isinstance(pos, (int, float)) else None

    qg = f.get("quality_gates")
    if isinstance(qg, dict) and qg:
        known = [v for v in qg.values() if v is not None]
        votes["quality_gates"] = (sum(bool(v) for v in known) / len(known) >= 0.5) if known else None
    else:
        votes["quality_gates"] = None

    vetoes = []
    if isinstance(fs, (int, float)) and fs <= 3:
        vetoes.append(f"F-Score {fs} <= 3 (Piotroski short zone)")
    if isinstance(rev, (int, float)) and rev < -0.02:
        vetoes.append(f"estimate revisions {rev:+.1%} < -2%")
    if isinstance(m6, (int, float)) and m6 < -0.10:
        vetoes.append(f"6-mo momentum {m6:+.0%} < -10% (falling knife)")

    regime = market_regime()
    if not regime["pass"]:
        vetoes.append(f"hostile market regime: {regime['detail']}")

    computable = {k: v for k, v in votes.items() if v is not None}
    ayes = sum(1 for v in computable.values() if v)
    ok = (len(computable) >= MIN_SYSTEMS
          and ayes / len(computable) >= supermajority
          and not vetoes)

    nays = sorted(k for k, v in computable.items() if not v)
    gapped = sorted(k for k, v in votes.items() if v is None)
    detail = (f"{ayes}/{len(computable)} systems bullish "
              f"(need >={supermajority:.0%} of >={MIN_SYSTEMS})"
              + (f"; against: {', '.join(nays)}" if nays else "")
              + (f"; not computable: {', '.join(gapped)}" if gapped else "")
              + (f"; VETO: {'; '.join(vetoes)}" if vetoes else "")
              + f"; regime {regime['detail']}")
    return {"votes": votes, "systems": len(computable), "ayes": ayes,
            "pass": ok, "vetoes": vetoes, "regime": regime, "detail": detail}


def render(c):
    """Committee-payload markdown block."""
    if not c:
        return "  - Consensus gate unavailable this run (treat as GAPPED)"
    lines = [f"  - Verdict: {'PASS' if c['pass'] else 'FAIL'} — {c['ayes']}/{c['systems']} "
             f"systems bullish (supermajority {SUPERMAJORITY:.0%}, min {MIN_SYSTEMS} computable)"]
    for k, v in c["votes"].items():
        mark = "✔" if v else ("✘" if v is not None else "GAPPED")
        lines.append(f"    - {k}: {mark}")
    for veto in c["vetoes"]:
        lines.append(f"  - HARD VETO: {veto}")
    lines.append(f"  - Market regime: {c['regime']['detail']} — "
                 f"{'OK' if c['regime']['pass'] else 'HOSTILE'}")
    return "\n".join(lines)
