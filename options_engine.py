"""Independent call-buying engine — multi-strategy confluence, decoupled from
the stock BUY pipeline.

This is NOT the earnings-rider in calls.py. That module answers "the stock
system says buy — which call expresses it?" This module answers a different
question with its own machinery: "does the OPTIONS market itself, plus the
underlying's behavior, present a rare high-conviction call-buying setup?"
It shares only the watchlist in config.json. It can flag a name the stock
side rates HOLD, and stays silent on names the stock side rates BUY.

Philosophy (Quinn, 2026-07-09): rare occurrence, very high accuracy. Long
calls have negative expected value by default — you pay theta and usually
pay an IV premium over realized vol. The only durable edges for a premium
BUYER are (a) vol that is priced too cheap, (b) trend persistence the market
underprices, (c) catalyst asymmetry, (d) positioning pressure. So the engine
runs four independent strategy JUDGES, one per edge, and only fires when a
supermajority agree at once — the same agreement-engineering philosophy as
consensus.py, applied to options.

Judges (each votes bullish / not / not-computable, with evidence):
  1. VOL_MISPRICING — contract IV vs a blended realized-vol forecast
     (EWMA-weighted 20/60/120d, a poor man's GARCH). Bullish when IV/RVf is
     cheap (<= 1.05): you're buying future movement below its likely cost.
  2. TREND — momentum persistence: price above rising 50d & 200d SMA, 6-mo
     return, proximity to 52-wk high, relative strength vs SPY. The academic
     momentum premium, expressed with convexity instead of shares.
  3. CATALYST — earnings posture: event inside the horizon, options implying
     LESS than the stock's own average earnings move (cheap event vol), and
     healthy term structure (crush priced in the front month, not our expiry).
  4. FLOW_PROXY — best-effort positioning read from free data: today's call
     volume vs open interest across the chain, call/put volume ratio. Weak
     alone (yfinance has no historical flow), so it can add conviction but
     a gap here never blocks the other judges.

Confluence bar (ALL required — silence for weeks is the system working):
  - Market regime pass (reuses consensus.market_regime: SPY>50d&200d, VIX<28)
  - >= 3 judges computable and >= 75% of computable judges bullish
  - No vetoes: IV/RVf >= 1.35 (paying up for vol kills the trade even in an
    uptrend), 6-mo momentum < -10%, price below 200d SMA
  - Contract quality gate: OI >= 500, spread <= 5% of mid, breakeven <= 0.6
    sigma of the option's own implied move, delta inside the target band
  - Composite score >= 85/100

Contract selection is judge-led, not stock-led:
  - TREND-led setup  -> stock-replacement call: delta 0.65-0.75, 45-90 DTE
    (buy intrinsic + persistence, minimize theta bleed per unit of delta)
  - CATALYST-led     -> delta 0.50-0.60, expiry 3-6 wks past earnings
    (post-event time value as IV-crush defense, same policy as calls.py)
  - Otherwise (vol-led) -> delta 0.55-0.70, 45-75 DTE

Expected-value sanity check: lognormal terminal-price EV of the call under
the FORECAST vol with zero drift (conservative — no momentum credit). The
premium must not exceed ~1.15x that zero-drift fair value.

State: options_state.json (cooldowns), options_ideas.json (append ledger).
Recommend-only, free data only, additive — touches nothing in the stock
pipeline. Run: `python options_engine.py [--discord] [--ticker NVDA]`.
"""
import argparse
import json
import math
import os
from datetime import date, datetime, timedelta

import yfinance as yf

import calls  # read-only reuse: bs_delta, avg_earnings_move, _safe_int
from consensus import market_regime

DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(DIR, "options_state.json")
LEDGER_PATH = os.path.join(DIR, "options_ideas.json")

RISK_FREE = 0.04
SUPERMAJORITY = 0.75
MIN_JUDGES = 3
PASS_SCORE = 85
COOLDOWN_DAYS = 10          # one idea per name per 2 trading weeks, max

# vetoes
VETO_IV_RVF = 1.35
VETO_MOM6 = -0.10

# contract quality gate (tight, matching the tightened calls.py policy)
MIN_OI = 500
MAX_SPREAD_PCT = 0.05
MAX_BREAKEVEN_SIGMA = 0.6
MAX_EV_PREMIUM = 1.15       # premium vs zero-drift fair value

DELTA_BANDS = {"trend": (0.65, 0.75), "catalyst": (0.50, 0.60), "vol": (0.55, 0.70)}
DTE_BANDS = {"trend": (45, 90), "catalyst": None, "vol": (45, 75)}  # catalyst uses earnings window
CATALYST_HORIZON_D = 15     # earnings within ~3 trading weeks counts as a live catalyst


# ---------------------------------------------------------------- vol forecast

def rv_annualized(close, days):
    rets = close.pct_change().dropna().tail(days)
    if len(rets) < max(10, days // 2):
        return None
    return float(rets.std()) * math.sqrt(252)


def forecast_rv(close):
    """EWMA-style blend of 20/60/120d realized vol, weighted toward recent.
    A deliberately simple stand-in for GARCH that needs no fitting and
    degrades gracefully on short histories."""
    parts = [(rv_annualized(close, 20), 0.5),
             (rv_annualized(close, 60), 0.3),
             (rv_annualized(close, 120), 0.2)]
    avail = [(v, w) for v, w in parts if v]
    if not avail:
        return None
    return sum(v * w for v, w in avail) / sum(w for _, w in avail)


# ------------------------------------------------------------------- judges

def judge_vol_mispricing(atm_iv, rvf):
    if not atm_iv or not rvf:
        return None, {}
    ratio = atm_iv / rvf
    return ratio <= 1.05, {"iv_rvf": round(ratio, 2), "atm_iv": round(atm_iv, 4),
                           "rv_forecast": round(rvf, 4)}


def judge_trend(close, spy_close):
    if close is None or len(close) < 200:
        return None, {}
    px = float(close.iloc[-1])
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    above = px > float(sma50.iloc[-1]) and px > float(sma200.iloc[-1])
    rising = float(sma50.iloc[-1]) > float(sma50.iloc[-21]) if len(sma50.dropna()) > 21 else False
    mom6 = px / float(close.iloc[-126]) - 1 if len(close) >= 126 else None
    hi52 = float(close.tail(252).max())
    near_high = px / hi52 >= 0.90
    rs = None
    if spy_close is not None and len(spy_close) >= 126 and mom6 is not None:
        spy6 = float(spy_close.iloc[-1]) / float(spy_close.iloc[-126]) - 1
        rs = mom6 - spy6
    checks = [above, rising, (mom6 is not None and mom6 > 0.15), near_high,
              (rs is not None and rs > 0)]
    ev = {"above_smas": above, "sma50_rising": rising,
          "mom_6m": round(mom6, 3) if mom6 is not None else None,
          "pct_of_52wk_high": round(px / hi52, 3),
          "rs_vs_spy_6m": round(rs, 3) if rs is not None else None}
    return sum(bool(c) for c in checks) >= 4, ev


def judge_catalyst(tk, close, atm_iv, next_earnings, term_ratio):
    """Bullish when a near catalyst exists AND the market prices its vol
    cheaply vs the stock's own history, with a healthy term structure."""
    if next_earnings is None:
        return None, {"note": "no earnings inside horizon"}
    days = (next_earnings - date.today()).days
    if days < 0 or days > CATALYST_HORIZON_D:
        return None, {"note": f"earnings {next_earnings} outside {CATALYST_HORIZON_D}d horizon"}
    em = calls.avg_earnings_move(tk, close)
    implied_1d = atm_iv / math.sqrt(252) if atm_iv else None
    cheap_event = (em is not None and implied_1d is not None and implied_1d < em)
    healthy_term = term_ratio is None or term_ratio <= 1.0
    ev = {"earnings_date": str(next_earnings), "days_to_earnings": days,
          "avg_earnings_move": round(em, 4) if em else None,
          "implied_daily_move": round(implied_1d, 4) if implied_1d else None,
          "term_ratio": term_ratio}
    if em is None or implied_1d is None:
        return None, ev
    return bool(cheap_event and healthy_term), ev


def judge_flow_proxy(tk, expiries):
    """Same-day chain totals only (free data has no flow history): call
    volume vs OI turnover and call/put volume ratio across the two nearest
    expiries. Suggestive, never decisive."""
    try:
        cv = pv = coi = 0
        for exp in list(expiries)[:2]:
            ch = tk.option_chain(exp)
            cv += sum(calls._safe_int(v) for v in ch.calls.get("volume", []))
            pv += sum(calls._safe_int(v) for v in ch.puts.get("volume", []))
            coi += sum(calls._safe_int(v) for v in ch.calls.get("openInterest", []))
        if cv + pv < 200 or coi <= 0:
            return None, {"note": "volume too thin to read"}
        turnover = cv / coi
        cp = cv / pv if pv else None
        ev = {"call_vol": cv, "put_vol": pv, "call_vol_oi_turnover": round(turnover, 2),
              "call_put_ratio": round(cp, 2) if cp else None}
        return (turnover >= 0.30 and cp is not None and cp >= 1.5), ev
    except Exception:
        return None, {"note": "chain flow unavailable"}


# ------------------------------------------------------- contract + EV math

def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def zero_drift_call_ev(spot, strike, t_years, vol):
    """Fair value of the call at expiry under lognormal terminal price with
    ZERO drift and the FORECAST vol — a conservative what-you're-owed number.
    (This is Black-Scholes with r=0 applied at the forecast vol.)"""
    if not all(v and v > 0 for v in (spot, strike, t_years, vol)):
        return None
    d1 = (math.log(spot / strike) + (vol * vol / 2) * t_years) / (vol * math.sqrt(t_years))
    d2 = d1 - vol * math.sqrt(t_years)
    return spot * _norm_cdf(d1) - strike * _norm_cdf(d2)


def pick_contract(tk, spot, lead, next_earnings):
    """Judge-led contract choice. Returns (contract|None, notes)."""
    notes = []
    d_lo, d_hi = DELTA_BANDS[lead]
    try:
        expiries = tk.options or ()
    except Exception:
        return None, ["option chain unavailable"]
    if lead == "catalyst" and next_earnings:
        lo = next_earnings + timedelta(days=21)
        hi = next_earnings + timedelta(days=45)
        window = [e for e in expiries if lo <= date.fromisoformat(e) <= hi]
    else:
        dte_lo, dte_hi = DTE_BANDS[lead] or (45, 90)
        lo = date.today() + timedelta(days=dte_lo)
        hi = date.today() + timedelta(days=dte_hi)
        window = [e for e in expiries if lo <= date.fromisoformat(e) <= hi]
    if not window:
        return None, [f"no expiry in the {lead}-led window {lo}..{hi}"]

    best = None
    for exp in window:
        try:
            chain = tk.option_chain(exp).calls
        except Exception:
            continue
        t_years = max((date.fromisoformat(exp) - date.today()).days, 1) / 365
        for _, row in chain.iterrows():
            iv, bid, ask = row.get("impliedVolatility"), row.get("bid"), row.get("ask")
            if not (isinstance(bid, (int, float)) and isinstance(ask, (int, float))
                    and bid > 0 and ask > 0):
                continue
            delta = calls.bs_delta(spot, row["strike"], t_years, iv)
            if delta is None or not (d_lo - 0.05 <= delta <= d_hi + 0.05):
                continue
            mid = (bid + ask) / 2
            cand = {"expiry": exp, "strike": float(row["strike"]), "delta": round(delta, 3),
                    "bid": float(bid), "ask": float(ask), "mid": round(mid, 2),
                    "iv": round(float(iv), 4) if isinstance(iv, (int, float)) else None,
                    "open_interest": calls._safe_int(row.get("openInterest")),
                    "volume": calls._safe_int(row.get("volume")),
                    "spread_pct": round((ask - bid) / mid, 4),
                    "contract": row.get("contractSymbol"),
                    "breakeven_move": round((row["strike"] + mid) / spot - 1, 4),
                    "t_years": round(t_years, 4)}
            in_band = d_lo <= delta <= d_hi
            key = (in_band, cand["open_interest"])
            if best is None or key > best[0]:
                best = (key, cand)
    if best is None:
        return None, notes + [f"no quoted call near the {d_lo:.2f}-{d_hi:.2f} delta band"]
    return best[1], notes


def atm_iv_and_term(tk, spot):
    """ATM IV of the ~45d expiry (our pricing reference) and the ratio of
    that IV to the front expiry's ATM IV (>1 = inverted for a buyer)."""
    def _atm(exp):
        ch = tk.option_chain(exp).calls
        ch = ch[ch["impliedVolatility"] > 0.01]
        if not len(ch):
            return None
        return float(ch.iloc[(ch["strike"] - spot).abs().argsort()[:1]]["impliedVolatility"].iloc[0])
    try:
        expiries = list(tk.options or ())
        if not expiries:
            return None, None, ()
        target = min(expiries, key=lambda e: abs((date.fromisoformat(e) - date.today()).days - 45))
        back = _atm(target)
        front = _atm(expiries[0]) if expiries[0] != target else None
        term = round(back / front, 2) if back and front else None
        return back, term, expiries
    except Exception:
        return None, None, ()


def next_earnings_date(tk):
    try:
        ed = tk.earnings_dates
        if ed is None or not len(ed):
            return None
        future = sorted(d.tz_localize(None).date() for d in ed.index
                        if d.tz_localize(None) > datetime.now())
        return future[0] if future else None
    except Exception:
        return None


# ---------------------------------------------------------------- evaluation

def evaluate(ticker, spy_close=None):
    """Full independent evaluation of one ticker. Never raises."""
    out = {"ticker": ticker, "actionable": False, "judges": {}, "evidence": {},
           "lead": None, "contract": None, "score": None, "vetoes": [], "reasons": [],
           "ts": datetime.now().isoformat(timespec="seconds")}
    try:
        tk = yf.Ticker(ticker)
        close = tk.history(period="1y")["Close"]
        spot = float(close.iloc[-1])
    except Exception as e:
        out["reasons"].append(f"no price history: {e}")
        return out
    out["spot"] = round(spot, 2)

    rvf = forecast_rv(close)
    atm_iv, term_ratio, expiries = atm_iv_and_term(tk, spot)
    earn = next_earnings_date(tk)

    votes = {}
    votes["vol_mispricing"], out["evidence"]["vol"] = judge_vol_mispricing(atm_iv, rvf)
    votes["trend"], out["evidence"]["trend"] = judge_trend(close, spy_close)
    votes["catalyst"], out["evidence"]["catalyst"] = judge_catalyst(tk, close, atm_iv, earn, term_ratio)
    votes["flow_proxy"], out["evidence"]["flow"] = judge_flow_proxy(tk, expiries)
    out["judges"] = votes

    # vetoes — any one is terminal
    iv_rvf = (atm_iv / rvf) if atm_iv and rvf else None
    if iv_rvf and iv_rvf >= VETO_IV_RVF:
        out["vetoes"].append(f"IV/RVf {iv_rvf:.2f} >= {VETO_IV_RVF} — vol too rich to buy")
    mom6 = out["evidence"]["trend"].get("mom_6m")
    if isinstance(mom6, (int, float)) and mom6 < VETO_MOM6:
        out["vetoes"].append(f"6-mo momentum {mom6:+.0%} < {VETO_MOM6:.0%} (falling knife)")
    if len(close) >= 200 and spot < float(close.rolling(200).mean().iloc[-1]):
        out["vetoes"].append("price below 200d SMA")
    regime = market_regime()
    out["regime"] = regime["detail"]
    if not regime["pass"]:
        out["vetoes"].append(f"hostile market regime: {regime['detail']}")

    computable = {k: v for k, v in votes.items() if v is not None}
    ayes = sum(1 for v in computable.values() if v)
    confluent = (len(computable) >= MIN_JUDGES
                 and ayes / len(computable) >= SUPERMAJORITY
                 and not out["vetoes"])
    out["confluence"] = f"{ayes}/{len(computable)} judges bullish (need >={SUPERMAJORITY:.0%} of >={MIN_JUDGES})"
    if not confluent:
        nays = sorted(k for k, v in computable.items() if not v)
        if nays:
            out["reasons"].append("against: " + ", ".join(nays))
        out["reasons"].extend(out["vetoes"])
        return out

    # which edge leads the setup -> contract style
    if votes.get("catalyst"):
        lead = "catalyst"
    elif votes.get("trend"):
        lead = "trend"
    else:
        lead = "vol"
    out["lead"] = lead

    c, notes = pick_contract(tk, spot, lead, earn)
    out["reasons"].extend(notes)
    if c is None:
        return out
    out["contract"] = c

    sigma_move = c["iv"] * math.sqrt(c["t_years"]) if c["iv"] else None
    be_sigma = (c["breakeven_move"] / sigma_move) if sigma_move else None
    fair = zero_drift_call_ev(spot, c["strike"], c["t_years"], rvf) if rvf else None
    ev_ratio = (c["mid"] / fair) if fair and fair > 0 else None
    out["evidence"]["contract_math"] = {
        "breakeven_sigma": round(be_sigma, 2) if be_sigma is not None else None,
        "zero_drift_fair_value": round(fair, 2) if fair else None,
        "premium_vs_fair": round(ev_ratio, 2) if ev_ratio else None}

    # composite score /100: confluence 35, vol edge 25, contract quality 25, EV 15
    conf_s = round(ayes / len(computable) * 100)
    vol_s = max(0, min(100, round(100 - max(0, (iv_rvf or 1.0) - 0.85) / 0.5 * 100)))
    liq_s = max(0, min(100, round((min(c["open_interest"], 2000) / 2000) * 50
                                  + (1 - min(c["spread_pct"], 0.10) / 0.10) * 50)))
    ev_s = max(0, min(100, round(100 - max(0, (ev_ratio or 1.0) - 0.9) / 0.5 * 100))) \
        if ev_ratio else None
    parts = [(conf_s, 35), (vol_s, 25), (liq_s, 25), (ev_s, 15)]
    avail = [(v, w) for v, w in parts if v is not None]
    out["score"] = round(sum(v * w for v, w in avail) / sum(w for _, w in avail))
    out["components"] = {"confluence": conf_s, "vol_edge": vol_s,
                         "contract_quality": liq_s, "expected_value": ev_s}

    fails = []
    if c["open_interest"] < MIN_OI:
        fails.append(f"OI {c['open_interest']} < {MIN_OI}")
    if c["spread_pct"] > MAX_SPREAD_PCT:
        fails.append(f"spread {c['spread_pct']:.0%} > {MAX_SPREAD_PCT:.0%}")
    if be_sigma is not None and be_sigma > MAX_BREAKEVEN_SIGMA:
        fails.append(f"breakeven {be_sigma:.2f} sigma > {MAX_BREAKEVEN_SIGMA}")
    if ev_ratio is not None and ev_ratio > MAX_EV_PREMIUM:
        fails.append(f"premium is {ev_ratio:.2f}x zero-drift fair value (max {MAX_EV_PREMIUM})")
    if out["score"] < PASS_SCORE:
        fails.append(f"score {out['score']} < {PASS_SCORE}")
    out["reasons"].extend(fails)
    out["actionable"] = not fails
    return out


# --------------------------------------------------------------- state + cli

def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def describe(r):
    c = r.get("contract")
    head = f"{r['ticker']} [{r.get('lead') or '-'}-led] {r.get('confluence', '')}"
    if not c:
        return head + " — no contract: " + "; ".join(r.get("reasons") or ["n/a"])
    m = r["evidence"].get("contract_math", {})
    return (f"{head}\n  {c['expiry']} ${c['strike']:g}C @ ~${c['mid']:.2f} "
            f"(Δ{c['delta']:.2f}, OI {c['open_interest']}, spread {c['spread_pct']:.0%}, "
            f"IV {c['iv']:.0%}, breakeven {c['breakeven_move']:+.1%} = {m.get('breakeven_sigma')}σ, "
            f"premium {m.get('premium_vs_fair')}x fair) — score {r['score']}/100"
            + (" ✅ CONVICTION CALL" if r["actionable"] else " ⚠️ " + "; ".join(r["reasons"])))


def render(r):
    """Committee-payload markdown block (same role calls.render used to fill)."""
    if not r:
        return "  - Options engine unavailable this run (treat as GAPPED)"
    lines = [f"  - Judge confluence: {r.get('confluence', 'GAPPED')} — "
             + ", ".join(f"{k} {'✔' if v else ('✘' if v is not None else 'GAPPED')}"
                         for k, v in (r.get("judges") or {}).items())]
    for veto in r.get("vetoes") or []:
        lines.append(f"  - HARD VETO: {veto}")
    c = r.get("contract")
    if not c:
        lines.append("  - No contract proposed: " + "; ".join(r.get("reasons") or ["n/a"]))
        return "\n".join(lines)
    m = (r.get("evidence") or {}).get("contract_math", {})
    comp = r.get("components", {})
    lines += [
        f"  - Proposed contract ({r.get('lead')}-led): {c.get('contract')} — {c['expiry']} "
        f"${c['strike']:g} call, mid ${c['mid']:.2f} (bid {c['bid']:.2f}/ask {c['ask']:.2f})",
        f"  - Delta {c['delta']:.2f} | OI {c['open_interest']} | volume {c['volume']} | "
        f"spread {c['spread_pct']:.1%} of mid | IV {c['iv']:.1%}",
        f"  - Breakeven {c['breakeven_move']:+.1%} = {m.get('breakeven_sigma', 'GAPPED')} sigma of "
        f"the implied move (max {MAX_BREAKEVEN_SIGMA}); premium {m.get('premium_vs_fair', 'GAPPED')}x "
        f"zero-drift fair value at forecast vol (max {MAX_EV_PREMIUM})",
        f"  - Score {r.get('score')}/100 (confluence {comp.get('confluence')}, vol edge "
        f"{comp.get('vol_edge')}, contract quality {comp.get('contract_quality')}, "
        f"EV {comp.get('expected_value')}; pass bar {PASS_SCORE})",
        f"  - OPTIONS VERDICT: {'CONVICTION CALL — committee to confirm' if r.get('actionable') else 'REJECTED'}"
        + (f" — {'; '.join(r['reasons'])}" if r.get("reasons") else ""),
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Independent call-conviction engine")
    ap.add_argument("--ticker", help="evaluate a single ticker (verbose)")
    ap.add_argument("--discord", action="store_true", help="announce actionable ideas")
    ap.add_argument("--all", action="store_true", help="print every result, not just actionable")
    args = ap.parse_args()

    cfg = _load(os.path.join(DIR, "config.json"), {})
    tickers = [args.ticker.upper()] if args.ticker else cfg.get("watchlist", [])
    try:
        spy_close = yf.Ticker("SPY").history(period="1y")["Close"]
    except Exception:
        spy_close = None

    state = _load(STATE_PATH, {})
    ledger = _load(LEDGER_PATH, [])
    actionable = []
    for t in tickers:
        last = state.get(t)
        if not args.ticker and last and \
                (datetime.now() - datetime.fromisoformat(last)).days < COOLDOWN_DAYS:
            continue
        r = evaluate(t, spy_close)
        if args.ticker or args.all or r["actionable"]:
            print(describe(r) + "\n")
        if r["actionable"]:
            actionable.append(r)
            state[t] = r["ts"]
            ledger.append(r)
            import signal_tracker
            c = r["contract"]
            signal_tracker.record("call_conviction", t, r.get("spot"),
                                  f"score {r['score']}/100, {r['lead']}-led",
                                  contract={k: c.get(k) for k in ("expiry", "strike", "mid", "delta")})

    if actionable:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f, indent=1)
        with open(LEDGER_PATH, "w") as f:
            json.dump(ledger, f, indent=1)
        if args.discord:
            import notify
            # Conviction calls are buy signals — post to the BUY channel (the
            # pinging channel), not #updates (Quinn, 2026-07-09).
            buy_webhook = notify.load_config()["discord_webhook_url"]
            for r in actionable:
                notify.send_message("🎯 OPTIONS ENGINE — independent conviction call\n"
                                    + describe(r) + "\nRecommend-only; committee verdict "
                                    "before acting.", kind="CALL_CONVICTION", mention=True,
                                    webhook_url=buy_webhook)
    if not args.ticker:
        print(f"Scanned {len(tickers)} names — {len(actionable)} conviction call(s). "
              "Silence is the bar working.")


if __name__ == "__main__":
    main()
