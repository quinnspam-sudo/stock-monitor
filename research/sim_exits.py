"""Exit-rule sweep on the Jan-Jul fire data: same $10-per-buy re-entry
portfolio, different sell rules. Finds which exit preserves the buy
signal's alpha.
"""
import json, sys
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path.home() / "Claude/stock-monitor"
CONFIG = json.loads((ROOT / "config.json").read_text())
START_FIRE, HIST_START = "2026-01-02", "2025-01-01"

wl = CONFIG["watchlist"]
print(f"Downloading {len(wl)} tickers…", file=sys.stderr)
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
sma50t, sma200t = px.rolling(50).mean(), px.rolling(200).mean()
hi52 = px.rolling(252, min_periods=200).max()
m6, m3 = px / px.shift(126) - 1, px / px.shift(63) - 1
votes = [m6 > 0, (px >= 0.99 * hi52).where(hi52.notna()),
         (px > sma50t).where(sma50t.notna()), (px > sma200t).where(sma200t.notna()),
         (m6.sub(spy_m6, axis=0) > 0).where(m6.notna()), (m3 > 0).where(m3.notna())]
vt = sum(v.fillna(False).astype(int) for v in votes)
vk = sum(v.notna().astype(int) for v in votes)
fire = (vk >= 5) & (vt / vk.replace(0, pd.NA) >= 0.75) & ~(m6 < -0.10).fillna(True)
fire = fire.fillna(False) & pd.DataFrame({c: regime for c in fire.columns}, index=fire.index)

low20 = px.shift(1).rolling(20).min()
low50 = px.shift(1).rolling(50).min()
volr = vol.rolling(5).mean() / vol.rolling(60).mean()
spy_last = float(spy.iloc[-1])
dates = px.loc[START_FIRE:].index

# exit(t, d, close, entry, peak) -> bool
def make_exit(kind):
    if kind == "none":
        return lambda t, d, c, e, pk: False
    if kind == "current":  # -7% stop + darvas20/vol
        def f(t, d, c, e, pk):
            if c <= e * 0.93: return True
            l, vr = low20.at[d, t], volr.at[d, t]
            return pd.notna(l) and c < l and (pd.isna(vr) or vr > 1.1)
        return f
    if kind == "stop15":
        return lambda t, d, c, e, pk: c <= e * 0.85
    if kind == "trail20":
        return lambda t, d, c, e, pk: c <= pk * 0.80
    if kind == "trail25":
        return lambda t, d, c, e, pk: c <= pk * 0.75
    if kind == "sma50":
        def f(t, d, c, e, pk):
            s = sma50t.at[d, t]
            return pd.notna(s) and c < s * 0.97  # 3% buffer below 50d
        return f
    if kind == "low50":
        def f(t, d, c, e, pk):
            l = low50.at[d, t]
            return pd.notna(l) and c < l
        return f
    if kind == "stop15+trail25":
        return lambda t, d, c, e, pk: c <= e * 0.85 or c <= pk * 0.75
    if kind == "stop10+trail20":
        return lambda t, d, c, e, pk: c <= e * 0.90 or c <= pk * 0.80
    if kind == "sma50+stop15":
        def f(t, d, c, e, pk):
            if c <= e * 0.85: return True
            s = sma50t.at[d, t]
            return pd.notna(s) and c < s * 0.97
        return f
    raise ValueError(kind)

def simulate(kind):
    ex = make_exit(kind)
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
                stocks += 10 * float(series.dropna().iloc[-1]) / entry
                break
            cash += 10 * float(series.at[dates[exit_j]]) / entry
            n_sells += 1
            i = exit_j + 1
    inv = 10 * n_buys
    total = stocks + cash
    print(f"{kind:16s} buys={n_buys:4d} sells={n_sells:4d} "
          f"total=${total:9,.2f} ({(total/inv-1)*100:+5.1f}%)  "
          f"SPY=${spy_val:9,.2f} ({(spy_val/inv-1)*100:+5.1f}%)  "
          f"edge={((total/inv)-(spy_val/inv))*100:+5.1f}pts")

for kind in ["none", "current", "stop15", "trail20", "trail25", "sma50",
             "low50", "stop15+trail25", "stop10+trail20", "sma50+stop15"]:
    simulate(kind)
