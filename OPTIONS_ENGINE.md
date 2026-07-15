# options_engine.py — independent call-conviction engine

A second, fully separate system from the stock pipeline. Shares only the
watchlist in `config.json`. It does NOT read stock ratings, the earnings
gate, or `calls.py`'s BUY-rider logic — it can fire on a stock-side HOLD
and stay silent on a stock-side BUY.

## How it decides

Four independent strategy judges, each voting bullish / not / GAPPED:

| Judge | Edge | Bullish when |
|---|---|---|
| vol_mispricing | IV vs forecast RV | ATM IV ≤ 1.05× EWMA-blended 20/60/120d realized vol |
| trend | momentum persistence | **5 of 5** (was ≥4/5): above 50d+200d SMA, rising 50d, 6-mo >+20%/+12% stock/ETF (was +15%/+8%), ≥93% of 52-wk high (was ≥90%), positive RS vs SPY |
| catalyst | event asymmetry | earnings ≤15d out, implied daily move ≤85% of avg historical earnings move (was just "less than"), term ratio ≤0.95 (was ≤1.0) |
| flow_proxy | positioning | call vol/OI turnover ≥0.45 (was ≥0.30) and call/put vol ≥2.0 stock / ≥1.3 ETF (was ≥1.5 / ≥1.0), same-day only — free data |

**Confluence bar (all required; tightened 2026-07-15 — this fires real
larger-dollar paper orders now, so frequency was traded for hit-rate — see
EXECUTION.md):** market regime pass (SPY>50d&200d, VIX<28, reused from
`consensus.py`) · ≥3 judges computable · **100% bullish (unanimous, was
≥75%)** · no vetoes (IV/RVf ≥1.15 (was ≥1.35), 6-mo momentum <0% (was
<-10% — any negative momentum vetoes now), price below 200d SMA).

### ETFs (added 2026-07-09)

The scan also covers `etf_watchlist` in `config.json` (~35 liquid index /
sector / commodity ETFs), through the same machinery with three
asset-class calibrations — not a separate engine, so future tuning stays in
sync:

- **catalyst is skipped** (no earnings) — confluence runs on the remaining
  3 judges, so ETF ideas need vol + trend + flow **unanimous** (was
  effectively unanimous under the 75% bar too, now explicitly required).
- **trend 6-mo momentum bar 12%** instead of 20% (baskets compound slower
  than single names; both raised from 8%/15% 2026-07-15).
- **flow call/put bar 1.3** instead of 2.0 — ETF put volume is structurally
  inflated by portfolio hedging (validated 2026-07-09: at 1.5, flow voted
  nay on all 35 ETFs; both bars raised 2026-07-15 keeping that same ratio).

Vetoes, contract gate, and the score bar are identical. ETF ideas are
tagged `[ETF]` in alerts and logged as `etf_call_conviction` in the signal
tracker.

**Contract selection is judge-led:** catalyst-led → Δ0.50–0.60 expiring 3–6
wks past earnings; trend-led → Δ0.65–0.75 stock-replacement, 45–90 DTE;
vol-led → Δ0.55–0.70, 45–75 DTE.

**Quality gate + score (tightened 2026-07-15):** OI ≥1500 (was ≥500), spread
≤3% of mid (was ≤5%), breakeven ≤0.45σ of the implied move (was ≤0.6σ),
premium ≤1.05× the zero-drift Black-Scholes fair value at the FORECAST vol
(was ≤1.15×). Composite score /100 (confluence 35, vol edge 25, contract
quality 25, expected value 15), pass bar **92** (was 85).

## Running

```
./venv/bin/python options_engine.py                 # full scan: watchlist + etf_watchlist
./venv/bin/python options_engine.py --ticker NVDA   # one name, verbose
./venv/bin/python options_engine.py --etfs-only     # ETF sweep only
./venv/bin/python options_engine.py --all           # print rejections too
./venv/bin/python options_engine.py --discord       # announce conviction calls
```

State: `options_state.json` (10-day per-name cooldown), `options_ideas.json`
(append ledger of actionable ideas). Every actionable idea is logged to
`signals.json` (kind `call_conviction`/`etf_call_conviction`) and **fully
auto-executed** the same day by `execute.py`'s `buy_options_pass` — a
1-contract paper buy on Alpaca, capped by `config.execution.
option_premium_usd_cap`, closed by `sell_options_pass` on
±`option_profit_target_pct`/`option_stop_loss_pct` or force-closed at expiry.
See `EXECUTION.md`. Silence for weeks is the system working, not failing —
it just means no trade fires, not that nothing would execute if one did.
