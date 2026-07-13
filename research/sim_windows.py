"""Multi-window replay: 5y / 1y / 6m starts, $10 per fire with re-entry,
three exit variants (never sell, NEW rules -15% stop + 25% trail, OLD rules
-7% stop + Darvas 20d), each vs $10 SPY on the same buy dates.
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
print(f"Downloading {len(wl)} tickers from {HIST_START}…", file=sys.stderr)
raw = yf.download(wl, start=HIST_START, auto_adjust=True, progress=False, group_by="column")
px, vol = raw["Close"].dropna(how="all"), raw["Volume"]
idx = yf.download(["SPY", "^VIX", "^VIX3M"], start=HIST_START, auto_adjust=True,
                  progress=False, group_by="column")["Close"]
spy, vix, v3m = idx["SPY"], idx["^VIX"], idx["^VIX3M"]
regime = ((spy > spy.rolling(50).mean()) & (spy > spy.rolling(200).mean())
          & (vix.ffill() < 28) & ~((vix.ffill() / v3m.ffill()) > 1.02))
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

low20 = px.shift(1).rolling(20).min()
volr = vol.rolling(5).mean() / vol.rolling(60).mean()
spy_last = float(spy.iloc[-1])

def exit_none(t, d, c, e, pk): return False
def exit_new(t, d, c, e, pk): return c <= e * 0.85 or c <= pk * 0.75
def exit_old(t, d, c, e, pk):
    if c <= e * 0.93: return True
    l, vr = low20.at[d, t], volr.at[d, t]
    return pd.notna(l) and c < l and (pd.isna(vr) or vr > 1.1)

def simulate(start, ex, reenter):
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
                if ex(t, dj, c, entry, peak):
                    exit_j = j; break
                j += 1
            if exit_j is None:
                last = series.dropna()
                stocks += 10 * float(last.iloc[-1]) / entry
                break
            cash += 10 * float(series.at[dates[exit_j]]) / entry
            n_sells += 1
            if not reenter: break
            i = exit_j + 1
        # non-reenter with a sell: stop this ticker (handled by break above)
    inv = 10 * n_buys
    if not inv: return None
    total = stocks + cash
    return (n_buys, n_sells, inv, total, (total/inv-1)*100, spy_val, (spy_val/inv-1)*100,
            (total/inv - spy_val/inv)*100)

for label, start in WINDOWS:
    print(f"\n===== {label} window (start {start}) =====")
    for name, ex, re_ in [("never sell", exit_none, False),
                          ("NEW rules ", exit_new, True),
                          ("OLD rules ", exit_old, True)]:
        r = simulate(start, ex, re_)
        if r is None: print(name, "no fires"); continue
        nb, ns, inv, tot, ret, sv, sret, edge = r
        print(f"{name}: buys={nb:4d} sells={ns:4d} invested=${inv:>7,} → "
              f"${tot:>10,.2f} ({ret:+6.1f}%) | SPY ${sv:>10,.2f} ({sret:+5.1f}%) | edge {edge:+5.1f}pts")
