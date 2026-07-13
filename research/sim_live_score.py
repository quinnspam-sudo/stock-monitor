"""Flaw #2 research: backtest the ACTUAL live signal, not the proxy.

Reconstructs monitor.py's score_ticker() day-by-day (RSI(14) simple-rolling,
SMA20/50 structure, 3-mo return caps, 3-mo-high proximity, RSI band 45-70,
volume 5d/60d confirmation), requires score >= alert_threshold (76) AND the
same consensus price-vote supermajority + regime gate the live pipeline
enforces. Buys $10 per fire (re-entry when flat), NEW exits (-15%/25% trail,
market-conditioned), vs $10 SPY same dates. 1y and 6m windows.

NOT reconstructable (noted): factor conviction tier (needs historical
fundamentals — live alerts additionally require HIGH/MEDIUM), 24h cooldown
granularity (daily closes make it ~1 fire/day anyway), sharding latency.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path.home() / "Claude/stock-monitor"
CONFIG = json.loads((ROOT / "config.json").read_text())
THRESHOLD = CONFIG.get("alert_threshold", 76)
HIST_START = "2024-01-01"
WINDOWS = [("1y", "2025-07-14"), ("6m", "2026-01-02")]

wl = CONFIG["watchlist"]
print("Downloading…", file=sys.stderr)
raw = yf.download(wl, start=HIST_START, auto_adjust=True, progress=False, group_by="column")
px, vol = raw["Close"].dropna(how="all"), raw["Volume"]
idx = yf.download(["SPY", "^VIX", "^VIX3M"], start=HIST_START, auto_adjust=True,
                  progress=False, group_by="column")["Close"]
spy, vix, v3m = idx["SPY"], idx["^VIX"], idx["^VIX3M"]
regime = ((spy > spy.rolling(50).mean()) & (spy > spy.rolling(200).mean())
          & (vix.ffill() < 28) & ~((vix.ffill() / v3m.ffill()) > 1.02))
spy_weak = (spy < spy.rolling(50).mean()).reindex(px.index).fillna(False)
spy = spy.reindex(px.index).ffill()
regime = regime.reindex(px.index).fillna(False)

# --- score_ticker, vectorized (mirrors monitor.py exactly) ---
sma50 = px.rolling(50).mean()
sma20 = px.rolling(20).mean()
high3m = px.rolling(63).max()
ret1m = px / px.shift(21) - 1
ret3m = px / px.shift(63) - 1
deltas = px.diff()
gains = deltas.clip(lower=0).rolling(14).mean()
losses = (-deltas.clip(upper=0)).rolling(14).mean()
rs = gains / losses.replace(0, 1e-9)
rsi = 100 - 100 / (1 + rs)
vol_ratio = vol.rolling(5).mean() / vol.rolling(60).mean()

score = (
    (px > sma50).astype(float) * 20
    + (sma20 > sma50).astype(float) * 15
    + (ret3m * 100).clip(lower=0, upper=20)
    + (ret1m * 150).clip(lower=0, upper=15)
    + (px >= high3m * 0.97).astype(float) * 15
    + ((rsi >= 45) & (rsi <= 70)).astype(float) * 10
    + (vol_ratio > 1.1).astype(float) * 5
).round().clip(upper=100)

# --- consensus price votes (same as live consensus.py analogs) ---
spy_m6 = spy / spy.shift(126) - 1
sma200 = px.rolling(200).mean()
hi52 = px.rolling(252, min_periods=200).max()
m6, m3 = px / px.shift(126) - 1, px / px.shift(63) - 1
votes = [m6 > 0, (px >= 0.99 * hi52).where(hi52.notna()),
         (px > sma50).where(sma50.notna()), (px > sma200).where(sma200.notna()),
         (m6.sub(spy_m6, axis=0) > 0).where(m6.notna()), (m3 > 0).where(m3.notna())]
vt = sum(v.fillna(False).astype(int) for v in votes)
vk = sum(v.notna().astype(int) for v in votes)
consensus_ok = (vk >= 5) & (vt / vk.replace(0, pd.NA) >= 0.75) & ~(m6 < -0.10).fillna(True)

fire = (score >= THRESHOLD) & consensus_ok.fillna(False)
fire = fire & pd.DataFrame({c: regime for c in fire.columns}, index=fire.index)
spy_last = float(spy.iloc[-1])

def simulate(start, use_exits):
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
            while use_exits and j < len(dates):
                dj = dates[j]; c = series.at[dj]
                if pd.isna(c): j += 1; continue
                peak = max(peak, c)
                if (c <= entry * 0.85 or c <= peak * 0.75) and not spy_weak.at[dj]:
                    exit_j = j; break
                j += 1
            if exit_j is None:
                stocks += 10 * float(series.dropna().iloc[-1]) / entry
                break
            cash += 10 * float(series.at[dates[exit_j]]) / entry
            n_sells += 1
            i = exit_j + 1
    inv = 10 * n_buys
    if not inv: return None
    total = stocks + cash
    return n_buys, n_sells, total/inv*100-100, spy_val/inv*100-100

for label, start in WINDOWS:
    print(f"\n===== LIVE SCORE >= {THRESHOLD} + consensus + regime — {label} =====")
    for name, ex in [("never sell", False), ("new exits ", True)]:
        r = simulate(start, ex)
        if not r: print(name, "no fires"); continue
        nb, ns, ret, sret = r
        print(f"{name}: buys={nb:4d} sells={ns:4d} return {ret:+6.1f}% | SPY {sret:+5.1f}% | edge {ret-sret:+5.1f}pts")
