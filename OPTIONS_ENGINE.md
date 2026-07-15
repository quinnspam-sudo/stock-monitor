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
| trend | momentum persistence | ≥4 of 5: above 50d+200d SMA, rising 50d, 6-mo >+15%, ≥90% of 52-wk high, positive RS vs SPY |
| catalyst | event asymmetry | earnings ≤15d out, implied daily move < avg historical earnings move, term structure not inverted |
| flow_proxy | positioning | call vol/OI turnover ≥0.30 and call/put vol ≥1.5 (same-day only — free data) |

**Confluence bar (all required):** market regime pass (SPY>50d&200d, VIX<28,
reused from `consensus.py`) · ≥3 judges computable · ≥75% bullish · no vetoes
(IV/RVf ≥1.35, 6-mo momentum <-10%, price below 200d SMA).

### ETFs (added 2026-07-09)

The scan also covers `etf_watchlist` in `config.json` (~35 liquid index /
sector / commodity ETFs), through the same machinery with three
asset-class calibrations — not a separate engine, so future tuning stays in
sync:

- **catalyst is skipped** (no earnings) — confluence runs on the remaining
  3 judges, so ETF ideas need vol + trend + flow effectively unanimous.
- **trend 6-mo momentum bar 8%** instead of 15% (baskets compound slower
  than single names).
- **flow call/put bar 1.0** instead of 1.5 — ETF put volume is structurally
  inflated by portfolio hedging (validated 2026-07-09: at 1.5, flow voted
  nay on all 35 ETFs).

Vetoes, contract gate, and the 85 score bar are identical. ETF ideas are
tagged `[ETF]` in alerts and logged as `etf_call_conviction` in the signal
tracker.

**Contract selection is judge-led:** catalyst-led → Δ0.50–0.60 expiring 3–6
wks past earnings; trend-led → Δ0.65–0.75 stock-replacement, 45–90 DTE;
vol-led → Δ0.55–0.70, 45–75 DTE.

**Quality gate + score:** OI ≥500, spread ≤5% of mid, breakeven ≤0.6σ of the
implied move, premium ≤1.15× the zero-drift Black-Scholes fair value at the
FORECAST vol. Composite score /100 (confluence 35, vol edge 25, contract
quality 25, expected value 15), pass bar **85**.

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
