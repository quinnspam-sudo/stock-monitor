"""Regime-conditional exits, tested over 5y/1y/6m.

Variants (all on top of NEW rules: -15% stop, 25% trail):
  new           — baseline, sells fire regardless of market
  weak-only     — sells only fire when SPY < its 50d SMA (market down)
  weak+disaster — weak-only, plus an unconditional -30%-from-entry floor
  strong-only   — sells only fire when SPY > its 50d SMA (idiosyncratic cut)
  never         — buy & hold reference
"""
import json, sys
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path.home() / "Claude/stock-monitor"
CONFIG = json.loads((ROOT / "config.json").read_text())
HIST_START = "2020-01-01"
WINDOWS = [("5y", "2021-07-13"), ("1y", "2025-07-14"), ("6m", "2026-01-02")]

wl = CONFIG["watchlist"]
print("Downloading…", file=sys.stderr)
raw = yf.download(wl, start=HIST_START, auto_adjust=True, progress=False, group_by="column")
px = raw["Close"].dropna(how="all")
idx = yf.download(["SPY", "^VIX", "^VIX3M"], start=HIST_START, auto_adjust=True,
                  progress=False, group_by="column")["Close"]
spy, vix, v3m = idx["SPY"], idx["^VIX"], idx["^VIX3M"]
regime = ((spy > spy.rolling(50).mean()) & (spy > spy.rolling(200).mean())
          & (vix.ffill() < 28) & ~((vix.ffill() / v3m.ffill()) > 1.02))
spy_weak = (spy < spy.rolling(50).mean()).reindex(px.index).fillna(False)
spy = spy.reindex(px.index).ffill()
regime = regime.reindex(px.index).fillna(False)
spy_m6 = spy / spy.shift(126) - 1
sma50, sma200 = px.rolling(50).mean(), px.rolling(200).mean()
hi52 = px.rolling(252, min_periods=200).max()
m6, m3 = px / px.shift(126) - 1, px / px.shift(63) - 1
votes = [m6 > 0, (px >= 0.99 * hi52).where(hi52.notna()),
         (px > sma50).where(sma50.notna()), (px > sma200).where(sma200.notna()),
         (m6.sub(spy_m6, axis=0) > 0).where(m6.notna()), (m3 > 0).where(m3.notna())]
vt = sum(v.fillna(False).astype(int) for v in votes)
vk = sum(v.notna().astype(int) for v in votes)
fire = (vk >= 5) & (vt / vk.replace(0, pd.NA) >= 0.75) & ~(m6 < -0.10).fillna(True)
fire = fire.fillna(False) & pd.DataFrame({c: regime for c in fire.columns}, index=fire.index)
spy_last = float(spy.iloc[-1])

def base_hit(c, e, pk): return c <= e * 0.85 or c <= pk * 0.75

EXITS = {
    "never":         lambda d, c, e, pk: False,
    "new (baseline)": lambda d, c, e, pk: base_hit(c, e, pk),
    "weak-only":     lambda d, c, e, pk: base_hit(c, e, pk) and spy_weak.at[d],
    "weak+disaster": lambda d, c, e, pk: (base_hit(c, e, pk) and spy_weak.at[d]) or c <= e * 0.70,
    "strong-only":   lambda d, c, e, pk: base_hit(c, e, pk) and not spy_weak.at[d],
}

def simulate(start, ex):
    dates = px.loc[start:].index
    stocks = cash = spy_val = 0.0
    n_buys = n_sells = 0
    for t in wl:
        if t not in fire.columns: continue
        f, series = fire[t], px[t]
        i = 0
        while i < len(dates):
            d = dates[i]
            if not f.at[d] or pd.isna(series.at[d]) or not series.at[d]:
                i += 1; continue
            entry = float(series.at[d]); peak = entry; n_buys += 1
            spy_val += 10 * spy_last / float(spy.at[d])
            j, exit_j = i + 1, None
            while j < len(dates):
                dj = dates[j]; c = series.at[dj]
                if pd.isna(c): j += 1; continue
                peak = max(peak, c)
                if ex(dj, c, entry, peak):
                    exit_j = j; break
                j += 1
            if exit_j is None:
                stocks += 10 * float(series.dropna().iloc[-1]) / entry
                break
            cash += 10 * float(series.at[dates[exit_j]]) / entry
            n_sells += 1
            i = exit_j + 1
    inv = 10 * n_buys
    total = stocks + cash
    return n_buys, n_sells, inv, total, spy_val

for label, start in WINDOWS:
    print(f"\n===== {label} (start {start}) =====")
    for name, ex in EXITS.items():
        nb, ns, inv, tot, sv = simulate(start, ex)
        print(f"{name:14s} buys={nb:4d} sells={ns:4d} → ${tot:>10,.2f} ({(tot/inv-1)*100:+6.1f}%) "
              f"| SPY ({(sv/inv-1)*100:+5.1f}%) | edge {(tot/inv-sv/inv)*100:+6.1f}pts")
