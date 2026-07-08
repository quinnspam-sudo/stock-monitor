"""Evidence-backed factor screens (cross-style playbook integration).

Computes per-ticker, from best-effort yfinance data (missing inputs yield
None and are reported as GAPPED rather than guessed):

  - Magic Formula (Greenblatt): earnings yield + return on capital, ranked
    cross-sectionally over the watchlist via rank_universe()
  - Piotroski F-Score: 9 binary tests on annual statements
  - PEG / GARP (Lynch)
  - Momentum 6/12-month (Carhart UMD)
  - Buffett-style quality gates
  - Graham/Buffett intrinsic value & margin of safety (Graham Number)
  - CANSLIM (O'Neil): 7-criterion growth+technical+market-regime checklist
  - Dividend growth quality (yield/payout/growth trend)
  - Fama-French 5-factor tilts (Size/Value descriptive; Profitability/
    Investment scored — Size/Value deliberately excluded from the
    conviction blend since a small-cap/cheap-B/M tilt would bias against
    the mega-cap growth names this watchlist is actually built around)
  - Quality Minus Junk (AQR): profitability + safety + payout composite
  - Insider cluster-buying signal (Form 4 Purchase/Sale text parsing)
  - Analyst estimate revision momentum (eps_trend current vs 90 days ago)
  - 52-week high breakout (O'Neil/Darvas-style, distinct from the 3-month
    high check in monitor.py's momentum score)
"""
from datetime import datetime, timedelta

import yfinance as yf

_SPY_CACHE = {}


def _spy_benchmark():
    """SPY 6-month return + whether SPY is above its own 50-day SMA — used
    as the 'L' (leader vs market) and 'M' (market direction) CANSLIM inputs.
    Cached per-process since every ticker in a run needs the same benchmark."""
    if "data" in _SPY_CACHE:
        return _SPY_CACHE["data"]
    try:
        h = yf.Ticker("SPY").history(period="1y")["Close"]
        mom_6m = float(h.iloc[-1] / h.iloc[-126] - 1) if len(h) >= 127 else None
        sma50 = float(h.rolling(50).mean().iloc[-1]) if len(h) >= 50 else None
        above_sma50 = (float(h.iloc[-1]) > sma50) if sma50 else None
        data = {"mom_6m": mom_6m, "above_sma50": above_sma50}
    except Exception:
        data = {"mom_6m": None, "above_sma50": None}
    _SPY_CACHE["data"] = data
    return data


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
    hist = None
    try:
        hist = tk.history(period="1y")
        h = hist["Close"]
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

    # --- Graham/Buffett intrinsic value & margin of safety ---
    eps = info.get("trailingEps")
    bvps = info.get("bookValue")
    price = info.get("currentPrice") or (float(hist["Close"].iloc[-1]) if hist is not None and len(hist) else None)
    graham_number = (22.5 * eps * bvps) ** 0.5 if eps and bvps and eps > 0 and bvps > 0 else None
    out["graham_number"] = graham_number
    out["margin_of_safety"] = (graham_number - price) / graham_number if graham_number and price else None

    # --- CANSLIM (O'Neil): 7 criteria, each True/False/None(gapped) ---
    spy = _spy_benchmark()
    fifty2_high = info.get("fiftyTwoWeekHigh")
    vol_ratio = None
    if hist is not None and len(hist) >= 60:
        try:
            vol_ratio = float(hist["Volume"].iloc[-5:].mean() / hist["Volume"].iloc[-60:].mean())
        except Exception:
            vol_ratio = None
    rs = (out["mom_6m"] - spy["mom_6m"]) if out["mom_6m"] is not None and spy["mom_6m"] is not None else None
    canslim_tests = {
        "C: current qtr earnings growth >=25%": (info.get("earningsQuarterlyGrowth") or 0) >= 0.25
            if isinstance(info.get("earningsQuarterlyGrowth"), (int, float)) else None,
        "A: annual earnings growth >=25%": (info.get("earningsGrowth") or 0) >= 0.25
            if isinstance(info.get("earningsGrowth"), (int, float)) else None,
        "N: near 52-wk high (>=90%)": (price >= fifty2_high * 0.90)
            if price and fifty2_high else None,
        "S: volume trend up (>=1.1x)": (vol_ratio >= 1.1) if vol_ratio is not None else None,
        "L: leader (RS vs SPY, 6mo)": (rs > 0) if rs is not None else None,
        "I: institutional sponsorship (>=30%)": (info.get("heldPercentInstitutions") or 0) >= 0.30
            if isinstance(info.get("heldPercentInstitutions"), (int, float)) else None,
        "M: market direction (SPY > 50-day SMA)": spy["above_sma50"],
    }
    out["canslim"] = canslim_tests
    out["canslim_score"] = sum(1 for v in canslim_tests.values() if v)
    out["canslim_gaps"] = sum(1 for v in canslim_tests.values() if v is None)

    # --- Dividend growth quality (yield/payout/growth trend) ---
    div_yield = info.get("trailingAnnualDividendYield")
    div_rate = info.get("trailingAnnualDividendRate")
    payout_ratio = (div_rate / eps) if div_rate and eps and eps > 0 else None
    div_cagr = None
    try:
        divs = tk.dividends
        if divs is not None and len(divs) > 4:
            cutoff = divs.index.max() - timedelta(days=5 * 365)
            recent = divs[divs.index >= cutoff]
            # annualize by summing trailing-12mo buckets, compare first vs last full year
            if len(recent) >= 8:
                yearly = recent.resample("YE").sum()
                yearly = yearly[yearly > 0]
                if len(yearly) >= 2:
                    years = (yearly.index[-1] - yearly.index[0]).days / 365.25
                    if years > 0 and yearly.iloc[0] > 0:
                        div_cagr = float((yearly.iloc[-1] / yearly.iloc[0]) ** (1 / years) - 1)
    except Exception:
        div_cagr = None
    out["dividend"] = {
        "yield": div_yield, "payout_ratio": payout_ratio, "cagr_5y": div_cagr,
    }
    if div_yield:  # only score dividend quality for actual dividend payers
        d_parts = []
        d_parts.append(100 if 0.015 <= div_yield <= 0.06 else 60 if div_yield > 0 else 0)
        if payout_ratio is not None:
            d_parts.append(100 if payout_ratio < 0.60 else 40 if payout_ratio < 0.90 else 10)
        if div_cagr is not None:
            d_parts.append(max(0, min(100, 50 + div_cagr * 300)))
        out["dividend_quality"] = round(sum(d_parts) / len(d_parts))
    else:
        out["dividend_quality"] = None  # not a dividend payer — GAPPED, not penalized

    # --- Fama-French 5-factor tilts (Size/Value descriptive only; see
    # module docstring for why they're excluded from the conviction blend) ---
    mcap = info.get("marketCap")
    size_bucket = ("Mega" if mcap and mcap >= 200e9 else "Large" if mcap and mcap >= 10e9
                    else "Mid" if mcap and mcap >= 2e9 else "Small" if mcap else "GAPPED")
    ptb = info.get("priceToBook")
    value_tilt = ("Value" if isinstance(ptb, (int, float)) and ptb < 3
                  else "Growth" if isinstance(ptb, (int, float)) else "GAPPED")
    op_profitability = gm  # gross profit / revenue, reused from Piotroski inputs above
    asset_growth = (ta / ta_p - 1) if ta and ta_p else None  # FF5 "Investment": low = conservative = favorable
    out["ff5"] = {
        "size": size_bucket, "value_tilt": value_tilt,
        "profitability": op_profitability, "asset_growth": asset_growth,
    }

    # --- Quality Minus Junk (AQR): profitability + safety + payout ---
    qmj_parts = []
    gpoa = (gp / ta) if gp is not None and ta else None  # gross profit over assets (Novy-Marx)
    if gpoa is not None:
        qmj_parts.append(max(0, min(100, gpoa * 200)))
    beta = info.get("beta")
    if isinstance(beta, (int, float)):
        qmj_parts.append(max(0, min(100, 100 - abs(beta - 1) * 60)))  # low-beta = safer
    if isinstance(de, (int, float)):
        qmj_parts.append(max(0, min(100, 100 - de / 2)))  # lower D/E = safer
    payout_yield = (div_yield or 0) + (1 - (shares / shares_p) if shares and shares_p and shares < shares_p else 0)
    if div_yield is not None or (shares is not None and shares_p is not None):
        qmj_parts.append(max(0, min(100, payout_yield * 1000)))
    out["qmj_score"] = round(sum(qmj_parts) / len(qmj_parts)) if qmj_parts else None

    # --- Insider cluster-buying signal (Lakonishok & Lee: cluster buying is
    # the more reliable insider signal, vs any single insider's trade) ---
    insider_signal = {"buys": 0, "sells": 0, "distinct_buyers": 0, "cluster_buy": False}
    try:
        df = tk.insider_transactions
        if df is not None and len(df):
            cutoff = datetime.now() - timedelta(days=90)
            recent = df[df["Start Date"] >= cutoff] if "Start Date" in df.columns else df.head(20)
            buyers = set()
            for _, row in recent.iterrows():
                text = str(row.get("Text", "")).lower()
                insider = row.get("Insider", "?")
                if "purchase" in text:
                    insider_signal["buys"] += 1
                    buyers.add(insider)
                elif "sale" in text:
                    insider_signal["sells"] += 1
            insider_signal["distinct_buyers"] = len(buyers)
            insider_signal["cluster_buy"] = len(buyers) >= 3 and insider_signal["sells"] == 0
    except Exception:
        insider_signal = None
    out["insider"] = insider_signal
    if insider_signal:
        net = insider_signal["buys"] - insider_signal["sells"]
        base = 50 + net * 8 + (20 if insider_signal["cluster_buy"] else 0)
        out["insider_score"] = max(0, min(100, base)) if (insider_signal["buys"] or insider_signal["sells"]) else None
    else:
        out["insider_score"] = None

    # --- Analyst estimate revision momentum (current vs 90 days ago) ---
    revision = None
    try:
        trend = tk.eps_trend
        if trend is not None and len(trend):
            deltas = []
            for period in ("0y", "+1y"):
                if period in trend.index:
                    row = trend.loc[period]
                    cur_est, old_est = row.get("current"), row.get("90daysAgo")
                    if cur_est and old_est:
                        deltas.append((cur_est - old_est) / abs(old_est))
            if deltas:
                revision = sum(deltas) / len(deltas)
    except Exception:
        revision = None
    out["analyst_revision"] = revision
    out["analyst_revision_score"] = max(0, min(100, 50 + revision * 500)) if revision is not None else None

    # --- 52-week high breakout (O'Neil/Darvas-style) ---
    pct_from_high = (price / fifty2_high - 1) if price and fifty2_high else None
    breakout = (pct_from_high is not None and pct_from_high >= -0.01
                and vol_ratio is not None and vol_ratio >= 1.2)
    out["breakout"] = {"pct_from_52wk_high": pct_from_high, "breakout": breakout, "vol_ratio": vol_ratio}
    out["breakout_score"] = (100 if breakout else max(0, min(100, 50 + pct_from_high * 200))
                             if pct_from_high is not None else None)

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

    mos = f.get("margin_of_safety")
    graham = (f"Graham Number ${f['graham_number']:,.2f}, margin of safety {mos:+.1%}"
              if f.get("graham_number") and mos is not None else "GAPPED")

    cs = f.get("canslim", {})
    canslim = (f"{f.get('canslim_score', 0)}/7 criteria met"
               + (f" ({f['canslim_gaps']} gapped)" if f.get("canslim_gaps") else "")
               + " — " + "; ".join(f"{k.split(':')[0]}: {'Y' if v else 'N' if v is not None else '?'}"
                                    for k, v in cs.items()))

    div = f.get("dividend", {})
    dq = f.get("dividend_quality")
    dividend = (f"yield {div['yield']:.1%}, payout {div['payout_ratio']:.0%}"
                if div.get("yield") and div.get("payout_ratio") is not None
                else f"yield {div['yield']:.1%}" if div.get("yield") else "not a dividend payer")
    dividend += f", quality score {dq}/100" if dq is not None else ""
    if div.get("cagr_5y") is not None:
        dividend += f", 5yr div CAGR {div['cagr_5y']:+.1%}"

    ff5 = f.get("ff5", {})
    ff5_line = (f"Size: {ff5.get('size', 'GAPPED')}, Value tilt: {ff5.get('value_tilt', 'GAPPED')} "
                f"(descriptive only, not scored — see interpretation guide), "
                f"Profitability: {pct(ff5.get('profitability'))}, "
                f"Asset growth: {pct(ff5.get('asset_growth'))}")

    qmj = f.get("qmj_score")
    qmj_line = f"{qmj}/100" if qmj is not None else "GAPPED"

    ins = f.get("insider")
    insider_line = (f"{ins['buys']} buy txns / {ins['sells']} sell txns, "
                    f"{ins['distinct_buyers']} distinct buyers"
                    + (" — CLUSTER BUY signal (bullish)" if ins.get("cluster_buy") else "")
                    if ins else "GAPPED")

    rev = f.get("analyst_revision")
    revision_line = f"{rev:+.1%} (current vs 90 days ago)" if rev is not None else "GAPPED"

    bo = f.get("breakout", {})
    breakout_line = (f"{bo['pct_from_52wk_high']:+.1%} from 52-wk high"
                     + (", volume-confirmed BREAKOUT" if bo.get("breakout") else "")
                     if bo.get("pct_from_52wk_high") is not None else "GAPPED")

    return (f"  - Magic Formula rank: {magic} (earnings yield {ey}, return on capital {roc})\n"
            f"  - Piotroski F-Score: {fs} (8-9 strong, 0-2 weak)\n"
            f"  - PEG (GARP): {peg}\n"
            f"  - Momentum: 6-mo {pct(f.get('mom_6m'))}, 12-mo {pct(f.get('mom_12m'))}\n"
            f"  - Quality gates (Buffett-style): {gates}\n"
            f"  - Graham/Buffett intrinsic value: {graham}\n"
            f"  - CANSLIM (O'Neil): {canslim}\n"
            f"  - Dividend growth quality (if applicable): {dividend}\n"
            f"  - Fama-French 5-factor tilts: {ff5_line}\n"
            f"  - Quality Minus Junk (AQR-style): {qmj_line}\n"
            f"  - Insider transactions (90d, cluster-buy check): {insider_line}\n"
            f"  - Analyst estimate revision momentum: {revision_line}\n"
            f"  - 52-week high breakout (O'Neil/Darvas): {breakout_line}")


def conviction(f):
    """Blend factor evidence into a 0-100 conviction score + tier label.
    Confluence logic: no single factor can carry the score (playbook lesson —
    every factor has multi-year down stretches). Weights below are relative,
    not required to sum to 1 — only available (non-gapped) parts are blended,
    normalized by the sum of weights actually present, so a ticker missing
    several inputs (e.g. no dividend, thin analyst coverage) isn't penalized
    for gaps, only scored on what's known.

    Fama-French Size/Value tilts are intentionally excluded here (see module
    docstring) — Profitability/Investment legs are folded into QMJ instead,
    which captures the same academic ground without biasing toward small/
    cheap names that would fight this watchlist's growth/momentum intent.
    """
    parts, weights = [], []
    if f.get("magic_rank") and f.get("magic_universe"):
        pct = 1 - (f["magic_rank"] - 1) / max(1, f["magic_universe"] - 1)
        parts.append(pct * 100); weights.append(0.15)
    if f.get("f_score") is not None and f.get("f_score_gaps", 9) < 5:
        parts.append(f["f_score"] / 9 * 100); weights.append(0.12)
    gates = [v for v in f.get("quality_gates", {}).values() if v is not None]
    if gates:
        parts.append(sum(gates) / len(gates) * 100); weights.append(0.10)
    moms = [m for m in (f.get("mom_6m"), f.get("mom_12m")) if m is not None]
    if moms:
        avg = sum(moms) / len(moms)
        parts.append(max(0, min(100, 50 + avg * 150))); weights.append(0.10)
    if f.get("margin_of_safety") is not None:
        parts.append(max(0, min(100, 50 + f["margin_of_safety"] * 100))); weights.append(0.12)
    if f.get("canslim_gaps", 7) < 4:
        parts.append(f["canslim_score"] / 7 * 100); weights.append(0.10)
    if f.get("dividend_quality") is not None:
        parts.append(f["dividend_quality"]); weights.append(0.06)
    if f.get("qmj_score") is not None:
        parts.append(f["qmj_score"]); weights.append(0.10)
    if f.get("insider_score") is not None:
        parts.append(f["insider_score"]); weights.append(0.08)
    if f.get("analyst_revision_score") is not None:
        parts.append(f["analyst_revision_score"]); weights.append(0.05)
    if f.get("breakout_score") is not None:
        parts.append(f["breakout_score"]); weights.append(0.04)
    if not parts:
        return None, "UNRATED (insufficient factor data)"
    score = round(sum(p * w for p, w in zip(parts, weights)) / sum(weights))
    peg = f.get("peg")
    if isinstance(peg, (int, float)) and peg <= 1:
        score = min(100, score + 5)  # GARP bonus
    tier = ("HIGH" if score >= 70 else "MEDIUM" if score >= 50 else "LOW")
    return score, tier
