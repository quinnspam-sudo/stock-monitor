"""Six-month fire-and-hold backtest — would the system's BUY fires have beaten SPY?

Replays the last ~6 months over the CURRENT stock watchlist and finds, for each
ticker, the FIRST date the (price-reconstructable) BUY-alert logic would have
fired. Then measures buy-and-hold return from that date's close through the
latest close, against SPY over the identical window.

HONEST LIMITS (read before trusting the numbers):
  - Only price-based signals can be reconstructed as-of a past date with free
    yfinance data. Fundamental votes (F-Score, analyst revisions, insider,
    CANSLIM, earnings positivity, quality gates) and the earnings-window gate
    are NOT replayed — historical snapshots don't exist for free. So this is
    an upper bound on fire frequency: the real system would have fired on a
    SUBSET of these names/dates.
  - Current-watchlist survivorship bias: names dropped along the way aren't
    tested.

Replayed per day t (using data up to and including t only):
  REGIME  — SPY close > 50d SMA and > 200d SMA; VIX < 28; VIX/VIX3M <= 1.02.
  VOTES   — price analogs of consensus.py systems, need >=75% true of >=5
            computable:
              mom_6m > 0                      (momentum_6m)
              close >= 0.99 * 52wk high       (breakout_52wk, factors.py bar)
              close > 50d SMA                 (trend / timing proxy)
              close > 200d SMA                (trend / quality proxy)
              mom_6m - SPY mom_6m > 0         (relative strength)
              mom_3m > 0                      (timing proxy)
  VETO    — mom_6m < -10% (falling knife).

Run: ./venv/bin/python backtest_fire_alpha.py [--start YYYY-MM-DD]
Writes committee_prompts/<today>_FIRE_ALPHA_BACKTEST.md and prints a summary.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text())

SUPERMAJORITY = 0.75
MIN_VOTES = 5
VIX_MAX = 28.0


def download_closes(tickers, start):
    px = yf.download(tickers, start=start, auto_adjust=True, progress=False,
                     group_by="column")["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame(tickers[0])
    return px.dropna(how="all")


def regime_series(start):
    idx = yf.download(["SPY", "^VIX", "^VIX3M"], start=start, auto_adjust=True,
                      progress=False, group_by="column")["Close"]
    spy, vix, v3m = idx["SPY"], idx["^VIX"], idx["^VIX3M"]
    ok = (spy > spy.rolling(50).mean()) & (spy > spy.rolling(200).mean())
    ok &= vix.ffill() < VIX_MAX
    term = (vix.ffill() / v3m.ffill())
    ok &= ~(term > 1.02)
    return ok.fillna(False), spy


def main():
    start_fire = "2026-01-12"
    if "--start" in sys.argv:
        start_fire = sys.argv[sys.argv.index("--start") + 1]
    hist_start = "2025-01-01"  # enough runway for 200d SMA / 252d high by Jan

    watchlist = CONFIG["watchlist"]
    print(f"Downloading {len(watchlist)} tickers + SPY/VIX from {hist_start}…")
    regime_ok, spy = regime_series(hist_start)
    px = download_closes(watchlist, hist_start)

    spy = spy.reindex(px.index).ffill()
    regime_ok = regime_ok.reindex(px.index).fillna(False)
    spy_m6 = spy / spy.shift(126) - 1

    sma50 = px.rolling(50).mean()
    sma200 = px.rolling(200).mean()
    hi52 = px.rolling(252, min_periods=200).max()
    m6 = px / px.shift(126) - 1
    m3 = px / px.shift(63) - 1

    votes = {
        "mom6": m6 > 0,
        "breakout": px >= 0.99 * hi52,
        "sma50": px > sma50,
        "sma200": px > sma200,
        "rs": m6.sub(spy_m6, axis=0) > 0,
        "mom3": m3 > 0,
    }
    vote_true = sum(v.fillna(False).astype(int) for v in votes.values())
    vote_known = sum(v.notna().astype(int) for v in
                     [m6 > 0, (px >= 0.99 * hi52).where(hi52.notna()),
                      (px > sma50).where(sma50.notna()),
                      (px > sma200).where(sma200.notna()),
                      (m6.sub(spy_m6, axis=0) > 0).where(m6.notna()),
                      (m3 > 0).where(m3.notna())])
    veto = m6 < -0.10

    fire = (vote_known >= MIN_VOTES) & \
           (vote_true / vote_known.replace(0, pd.NA) >= SUPERMAJORITY) & \
           ~veto.fillna(True)
    fire = fire.fillna(False) & pd.DataFrame(
        {c: regime_ok for c in fire.columns}, index=fire.index)

    window = fire.loc[start_fire:]
    last_date = px.index[-1]
    spy_last = float(spy.iloc[-1])

    rows = []
    for t in watchlist:
        if t not in window.columns:
            continue
        fired = window.index[window[t]]
        if not len(fired):
            continue
        d0 = fired[0]
        p0, p1 = float(px.at[d0, t]), float(px[t].iloc[-1])
        s0 = float(spy.at[d0])
        ret = p1 / p0 - 1
        spy_ret = spy_last / s0 - 1
        rows.append({"ticker": t, "fire_date": str(d0.date()),
                     "return": ret, "spy_return": spy_ret,
                     "alpha": ret - spy_ret})

    rows.sort(key=lambda r: -r["alpha"])
    n = len(rows)
    if not n:
        print("No fires in window."); return
    beat = sum(1 for r in rows if r["alpha"] > 0)
    avg_ret = sum(r["return"] for r in rows) / n
    avg_spy = sum(r["spy_return"] for r in rows) / n
    med_alpha = sorted(r["alpha"] for r in rows)[n // 2]

    lines = "\n".join(
        f"| {r['ticker']} | {r['fire_date']} | {r['return']:+.1%} | "
        f"{r['spy_return']:+.1%} | {r['alpha']:+.1%} |" for r in rows)
    today = datetime.now().strftime("%Y-%m-%d")
    report = f"""# FIRE-AND-HOLD BACKTEST — {start_fire} → {last_date:%Y-%m-%d}
Price-reconstructable approximation of the BUY-alert logic (see script header
for what could NOT be replayed — real system fires on a subset of these).

- Tickers that would have fired: **{n}** of {len(watchlist)} on the watchlist
- Beat SPY from their fire date: **{beat}/{n} ({beat/n:.0%})**
- Avg return {avg_ret:+.1%} vs avg SPY-over-same-windows {avg_spy:+.1%} → avg alpha **{avg_ret-avg_spy:+.1%}**, median alpha {med_alpha:+.1%}

| Ticker | First fire | Return to date | SPY same window | Alpha |
|---|---|---|---|---|
{lines}
"""
    out = ROOT / "committee_prompts" / f"{today}_FIRE_ALPHA_BACKTEST.md"
    out.write_text(report)
    print(report.split("| Ticker")[0])
    print(f"Full table: {out}")


if __name__ == "__main__":
    main()
