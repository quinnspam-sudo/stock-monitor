"""Evidence-backed factor screens (cross-style playbook integration).

Computes per-ticker: Magic Formula inputs (earnings yield EBIT/EV, return on
capital), Piotroski F-Score (9 binary tests on annual statements), PEG (GARP),
6/12-month momentum, and Buffett-style quality gates. Cross-sectional Magic
Formula ranks are computed over the whole watchlist via rank_universe().

All values are best-effort from yfinance; missing inputs yield None and are
reported as gapped rather than guessed.
"""
import yfinance as yf


def _row(df, names):
    """First matching row's two most recent annual values (cur, prior)."""
    if df is None or df.empty:
        return None, None
    for n in names:
        if n in df.index:
            vals = df.loc[n].dropna()
            cur = float(vals.iloc[0]) if len(vals) > 0 else None
            prior = float(vals.iloc[1]) if len(vals) > 1 else None
            return cur, prior
    return None, None


def compute(ticker):
    tk = yf.Ticker(ticker)
    info = tk.info or {}
    try:
        inc, bal, cf = tk.financials, tk.balance_sheet, tk.cashflow
    except Exception:
        inc = bal = cf = None

    out = {}

    # --- Magic Formula inputs (Greenblatt) ---
    ebit, ebit_prior = _row(inc, ["EBIT", "Operating Income"])
    ev = info.get("enterpriseValue")
    cur_assets, cur_assets_p = _row(bal, ["Current Assets", "Total Current Assets"])
    cur_liab, cur_liab_p = _row(bal, ["Current Liabilities", "Total Current Liabilities"])
    net_ppe, _ = _row(bal, ["Net PPE", "Property Plant Equipment Net"])
    out["earnings_yield"] = ebit / ev if ebit and ev else None
    cap = ((cur_assets or 0) - (cur_liab or 0) + (net_ppe or 0)) if (cur_assets or net_ppe) else None
    out["return_on_capital"] = ebit / cap if ebit and cap and cap > 0 else None

    # --- Piotroski F-Score (9 binary tests, annual YoY) ---
    ni, ni_p = _row(inc, ["Net Income", "Net Income Common Stockholders"])
    ta, ta_p = _row(bal, ["Total Assets"])
    cfo, _ = _row(cf, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    ltd, ltd_p = _row(bal, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"])
    shares, shares_p = _row(bal, ["Ordinary Shares Number", "Share Issued"])
    gp, gp_p = _row(inc, ["Gross Profit"])
    rev, rev_p = _row(inc, ["Total Revenue"])
    tests, gaps = [], 0

    def add(cond):
        nonlocal gaps
        if cond is None:
            gaps += 1
            tests.append(0)
        else:
            tests.append(1 if cond else 0)

    roa = ni / ta if ni is not None and ta else None
    roa_p = ni_p / ta_p if ni_p is not None and ta_p else None
    add(roa > 0 if roa is not None else None)                                   # 1 positive ROA
    add(cfo > 0 if cfo is not None else None)                                   # 2 positive CFO
    add(roa > roa_p if roa is not None and roa_p is not None else None)         # 3 ROA rising
    add(cfo > ni if cfo is not None and ni is not None else None)               # 4 accruals: CFO > NI
    lev = ltd / ta if ltd is not None and ta else (0 if ltd == 0 else None)
    lev_p = ltd_p / ta_p if ltd_p is not None and ta_p else (0 if ltd_p == 0 else None)
    add(lev <= lev_p if lev is not None and lev_p is not None else None)        # 5 leverage falling
    curr = cur_assets / cur_liab if cur_assets and cur_liab else None
    curr_p = cur_assets_p / cur_liab_p if cur_assets_p and cur_liab_p else None
    add(curr > curr_p if curr is not None and curr_p is not None else None)     # 6 current ratio rising
    add(shares <= shares_p if shares is not None and shares_p is not None else None)  # 7 no dilution
    gm = gp / rev if gp is not None and rev else None
    gm_p = gp_p / rev_p if gp_p is not None and rev_p else None
    add(gm > gm_p if gm is not None and gm_p is not None else None)             # 8 gross margin rising
    at = rev / ta if rev is not None and ta else None
    at_p = rev_p / ta_p if rev_p is not None and ta_p else None
    add(at > at_p if at is not None and at_p is not None else None)             # 9 asset turnover rising
    out["f_score"] = sum(tests)
    out["f_score_gaps"] = gaps

    # --- GARP / PEG (Lynch) ---
    out["peg"] = info.get("trailingPegRatio")

    # --- Momentum 6/12-month (Carhart UMD) ---
    try:
        h = tk.history(period="1y")["Close"]
        out["mom_6m"] = float(h.iloc[-1] / h.iloc[-126] - 1) if len(h) >= 127 else None
        out["mom_12m"] = float(h.iloc[-1] / h.iloc[0] - 1) if len(h) >= 200 else None
    except Exception:
        out["mom_6m"] = out["mom_12m"] = None

    # --- Buffett-style quality gates ---
    roe = info.get("returnOnEquity")
    de = info.get("debtToEquity")
    gm_i = info.get("grossMargins")
    out["quality_gates"] = {
        "ROE >= 15%": (roe >= 0.15) if isinstance(roe, (int, float)) else None,
        "Debt/Equity < 0.5": (de < 50) if isinstance(de, (int, float)) else None,
        "Gross margin > 40%": (gm_i > 0.40) if isinstance(gm_i, (int, float)) else None,
        "CFO > Net Income": (cfo > ni) if cfo is not None and ni is not None else None,
    }
    return out


def rank_universe(factor_map):
    """Cross-sectional Magic Formula rank (Greenblatt): sum of earnings-yield
    rank + return-on-capital rank; 1 = best. Mutates each dict in place."""
    def ranks(key):
        vals = [(t, f[key]) for t, f in factor_map.items() if f.get(key) is not None]
        vals.sort(key=lambda x: -x[1])
        return {t: i + 1 for i, (t, _) in enumerate(vals)}
    ey, roc = ranks("earnings_yield"), ranks("return_on_capital")
    combined = [(t, ey[t] + roc[t]) for t in factor_map if t in ey and t in roc]
    combined.sort(key=lambda x: x[1])
    order = {t: i + 1 for i, (t, _) in enumerate(combined)}
    for t, f in factor_map.items():
        f["magic_rank"] = order.get(t)
        f["magic_universe"] = len(combined)
    return factor_map


def render(f):
    """Markdown block for a committee payload."""
    def pct(x):
        return f"{x:+.1%}" if x is not None else "GAPPED"
    gates = "; ".join(f"{k}: {'PASS' if v else 'FAIL' if v is not None else 'GAPPED'}"
                      for k, v in f.get("quality_gates", {}).items())
    magic = (f"#{f['magic_rank']} of {f['magic_universe']} in universe"
             if f.get("magic_rank") else "GAPPED")
    fs = f"{f['f_score']}/9" + (f" ({f['f_score_gaps']} tests gapped)" if f.get("f_score_gaps") else "")
    ey = f"{f['earnings_yield']:.1%}" if f.get("earnings_yield") is not None else "GAPPED"
    roc = f"{f['return_on_capital']:.1%}" if f.get("return_on_capital") is not None else "GAPPED"
    peg = f"{f['peg']:.2f}" + (" (GARP: attractive <= 1)" if f["peg"] <= 1 else "") \
        if isinstance(f.get("peg"), (int, float)) else "GAPPED"
    return (f"  - Magic Formula rank: {magic} (earnings yield {ey}, return on capital {roc})\n"
            f"  - Piotroski F-Score: {fs} (8-9 strong, 0-2 weak)\n"
            f"  - PEG (GARP): {peg}\n"
            f"  - Momentum: 6-mo {pct(f.get('mom_6m'))}, 12-mo {pct(f.get('mom_12m'))}\n"
            f"  - Quality gates (Buffett-style): {gates}")


def conviction(f):
    """Blend factor evidence into a 0-100 conviction score + tier label.
    Confluence logic: no single factor can carry the score (playbook lesson —
    every factor has multi-year down stretches)."""
    parts, weights = [], []
    if f.get("magic_rank") and f.get("magic_universe"):
        pct = 1 - (f["magic_rank"] - 1) / max(1, f["magic_universe"] - 1)
        parts.append(pct * 100); weights.append(0.30)
    if f.get("f_score") is not None and f.get("f_score_gaps", 9) < 5:
        parts.append(f["f_score"] / 9 * 100); weights.append(0.25)
    gates = [v for v in f.get("quality_gates", {}).values() if v is not None]
    if gates:
        parts.append(sum(gates) / len(gates) * 100); weights.append(0.25)
    moms = [m for m in (f.get("mom_6m"), f.get("mom_12m")) if m is not None]
    if moms:
        avg = sum(moms) / len(moms)
        parts.append(max(0, min(100, 50 + avg * 150))); weights.append(0.20)
    if not parts:
        return None, "UNRATED (insufficient factor data)"
    score = round(sum(p * w for p, w in zip(parts, weights)) / sum(weights))
    peg = f.get("peg")
    if isinstance(peg, (int, float)) and peg <= 1:
        score = min(100, score + 5)  # GARP bonus
    tier = ("HIGH" if score >= 70 else "MEDIUM" if score >= 50 else "LOW")
    return score, tier
