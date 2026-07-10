"""Depth enrichment — fills formerly-GAPPED payload sources with free data.

Each function returns a list of committee-payload lines, or None when the
source is genuinely unavailable for that name (renderer then marks it GAPPED
as before — a fetch failure must look like a gap, never like clean data).

Sources filled (2026-07-09, from the standing GAPPED list):
  - Short interest trend  — shares short vs prior month, days-to-cover,
    % of float (yfinance info fields)
  - Institutional flow    — top 13F holders WITH quarter-over-quarter
    pctChange (yfinance institutional_holders)
  - SEC filing stream     — last filings with type + date (tk.sec_filings)
  - Options skew / flow   — 25-delta put/call IV skew from the ~45d chain,
    plus same-day call/put volume and OI totals

Still genuinely gapped (no free source): congressional trades, earnings
call transcripts, credit ratings.
"""
import math
from datetime import date

import calls  # bs_delta reuse


def short_interest(info):
    try:
        ss = info.get("sharesShort")
        prior = info.get("sharesShortPriorMonth")
        if not ss:
            return None
        lines = []
        if prior:
            chg = ss / prior - 1
            direction = "RISING" if chg > 0.03 else "FALLING" if chg < -0.03 else "flat"
            lines.append(f"Shares short {ss:,} vs {prior:,} prior month ({chg:+.1%} — {direction})")
        else:
            lines.append(f"Shares short {ss:,} (prior month unavailable)")
        if info.get("shortRatio"):
            lines.append(f"Days-to-cover {info['shortRatio']:.1f}"
                         + (" — squeeze-prone above ~5" if info["shortRatio"] >= 5 else ""))
        if info.get("shortPercentOfFloat"):
            lines.append(f"Short interest {info['shortPercentOfFloat']:.1%} of float"
                         + (" — crowded short" if info["shortPercentOfFloat"] >= 0.10 else ""))
        return lines
    except Exception:
        return None


def institutional_flow(tk):
    """Top 13F holders with quarter-over-quarter position change — the
    'are the big allocators adding or trimming' read."""
    try:
        df = tk.institutional_holders
        if df is None or not len(df) or "pctChange" not in df.columns:
            return None
        lines = []
        adds = trims = 0
        for _, row in df.head(6).iterrows():
            chg = row.get("pctChange")
            chg_s = f"{chg:+.1%} q/q" if isinstance(chg, (int, float)) and chg == chg else "n/a"
            if isinstance(chg, (int, float)) and chg == chg:
                adds += chg > 0.001
                trims += chg < -0.001
            lines.append(f"{row.get('Holder', '?')}: {row.get('pctHeld', 0):.2%} held, {chg_s}")
        lines.insert(0, f"Top holders: {adds} adding / {trims} trimming this quarter")
        return lines
    except Exception:
        return None


def sec_filings(tk, limit=5):
    try:
        filings = tk.sec_filings
        if not filings:
            return None
        out = []
        for f in filings[:limit]:
            d = f.get("date")
            t = f.get("type", "?")
            flag = " ⚠️" if t in ("8-K", "SC 13D", "S-1", "424B5", "DEFM14A") else ""
            out.append(f"{d} {t}{flag} — {(f.get('title') or '')[:70]}")
        return out
    except Exception:
        return None


def option_skew(tk, spot):
    """25-delta put/call skew and same-day flow from the ~45d expiry.
    High put skew = downside protection bid (fear); call-over-put skew
    (negative number here) = upside chase. Returns payload lines."""
    try:
        expiries = list(tk.options or ())
        if not expiries or not spot:
            return None
        exp = min(expiries, key=lambda e: abs((date.fromisoformat(e) - date.today()).days - 45))
        ch = tk.option_chain(exp)
        t_years = max((date.fromisoformat(exp) - date.today()).days, 1) / 365

        def iv_at_delta(chain, target, is_put):
            best = None
            for _, row in chain.iterrows():
                iv = row.get("impliedVolatility")
                if not isinstance(iv, (int, float)) or iv <= 0.01:
                    continue
                d = calls.bs_delta(spot, row["strike"], t_years, iv)
                if d is None:
                    continue
                if is_put:
                    d = d - 1  # put delta from call delta (same strike/iv)
                gap = abs(abs(d) - target)
                if best is None or gap < best[0]:
                    best = (gap, float(iv))
            return best[1] if best and best[0] < 0.10 else None

        put25 = iv_at_delta(ch.puts, 0.25, True)
        call25 = iv_at_delta(ch.calls, 0.25, False)
        atm_row = ch.calls.iloc[(ch.calls["strike"] - spot).abs().argsort()[:1]]
        atm = float(atm_row["impliedVolatility"].iloc[0]) if len(atm_row) else None
        cv = sum(calls._safe_int(v) for v in ch.calls.get("volume", []))
        pv = sum(calls._safe_int(v) for v in ch.puts.get("volume", []))

        lines = [f"Reference expiry {exp} (~45d): ATM IV {atm:.1%}" if atm else f"Reference expiry {exp}"]
        if put25 and call25:
            rr = put25 - call25
            read = ("heavy downside-protection bid (fear)" if rr > 0.06
                    else "upside being chased (call skew)" if rr < -0.02
                    else "balanced")
            lines.append(f"25Δ put IV {put25:.1%} vs 25Δ call IV {call25:.1%} — skew {rr:+.1%} ({read})")
        if cv + pv > 0:
            lines.append(f"Same-day flow at this expiry: {cv:,} call vol vs {pv:,} put vol "
                         f"(C/P {cv / pv:.2f})" if pv else f"Same-day flow: {cv:,} calls, no put volume")
        return lines
    except Exception:
        return None
