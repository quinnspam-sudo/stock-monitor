"""Flaw #1 research: parameter sensitivity of the adopted exit rules.

If -15%/25% sits on a smooth plateau (neighbors perform similarly), the
choice is robust; if it's a lone spike, it's overfit. Grid over stop x trail,
market-conditioned (sells only when SPY > 50d SMA), re-entry, 1y and 6m.
"""
import json, sys
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path.home() / "Claude/stock-monitor"
CONFIG = json.loads((ROOT / "config.json").read_text())
HIST_START = "2024-01-01"
WINDOWS = [("1y", "2025-07-14"), ("6m", "2026-01-02")]

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

def simulate(start, stop_mult, trail_mult):
    dates = px.loc[start:].index
    stocks = cash = spy_val = 0.0
    n_buys = 0
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
                if (c <= entry * stop_mult or c <= peak * trail_mult) and not spy_weak.at[dj]:
                    exit_j = j; break
                j += 1
            if exit_j is None:
                stocks += 10 * float(series.dropna().iloc[-1]) / entry
                break
            cash += 10 * float(series.at[dates[exit_j]]) / entry
            i = exit_j + 1
    inv = 10 * n_buys
    total = stocks + cash
    return (total / inv - spy_val / inv) * 100

for label, start in WINDOWS:
    print(f"\n===== {label} — edge vs SPY (pts), rows=stop, cols=trail =====")
    trails = [0.80, 0.75, 0.70]
    print("         " + "".join(f"trail{(1-tr)*100:>3.0f}%" for tr in trails))
    for st in [0.90, 0.875, 0.85, 0.80]:
        row = f"stop{(1-st)*100:>4.1f}% "
        for tr in trails:
            row += f"{simulate(start, st, tr):+8.1f}"
        print(row)
