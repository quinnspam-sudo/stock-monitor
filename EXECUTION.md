# Paper-Trading Executor (`execute.py` + `broker.py`)

Turns the system's signals into real (paper) orders — the "robot" the rest of
stock-monitor already assumes. Added 2026-07-13 for a **one-month paper trial
(→ 2026-08-13)**.

## Why

The system already prescribes mechanical trades: the BUY alert says buy
`buy_amount_usd` equal-size, `sell_check` says exactly when to exit, and
`actual_trades.json` records "what actually happened". Until now a human typed
those into the Discord #buy-log (`Bought $20 of NVDA`). This executor removes
that human-lag step by placing the orders on an **Alpaca paper account** and
writing the identical `actual_trades.json` records — so `performance.py`,
`sell_check.py`, and the weekly review all pick them up unchanged.

## Hard safety boundaries

- **Paper only.** `broker.py` hard-wires `paper=True`; there is no code path to a
  live-money account. Going live later is a deliberate, separate change (live
  client + live keys + explicit config opt-in), not a flag.
- **Never touches the frozen trading rules.** It only *executes* them. Entry
  (score≥76 + consensus + regime) and exits (−15% / −30% / 25% trail) stay
  frozen per `EVALUATION_PROTOCOL.md`. The sell logic imports `sell_check`'s
  constants, so it cannot drift from the frozen thresholds.
- **Degrades to a no-op.** No keys, library missing, market closed, or
  `kill_switch` on → the run exits cleanly and prints why. The broker being
  unconfigured is never an error for the rest of the system.

## What it does each run (every 15 min, market hours, after monitor)

- **BUY** — executes *today's* fresh `buy_alert` signals from `signals.json`
  that aren't already in `executed_orders.json`, subject to the guardrails.
  (Only today's — it never back-fills a historical backlog on first activation.)
- **SELL** — applies the frozen `sell_check` exit rules to live paper positions
  and closes any that trigger (disaster stop / market-conditioned stop / trailing
  stop / annual rebalance).
- **BUY CALL** — executes fresh `call_conviction`/`etf_call_conviction`
  signals from the last 2 calendar days (written by `options_engine.py`) as
  1-contract paper buys, capped by `option_premium_usd_cap`. The 2-day window
  (vs. stock BUY's today-only) exists because the options scan runs once
  daily at 12:45 PT, only 5 minutes before execute's last run of the day
  (12:50 PT) — too tight a gap to guarantee same-day pickup, so a signal
  that narrowly misses today's window still fires on tomorrow's first run
  instead of being silently dropped (Quinn, 2026-07-15). Recorded to a
  **separate** `option_trades.json`
  ledger — options never touch `actual_trades.json`, so `performance.py`/
  `sell_check.py`'s equity math can't be contaminated by an OCC symbol.
- **SELL CALL** — closes an option position at ±`option_profit_target_pct`/
  `option_stop_loss_pct` on premium, or force-closes on/after expiry day
  regardless of P/L (an unattended account should never risk assignment or an
  expire-worthless outcome by inaction).
- **RECONCILE** — reports any drift between Alpaca's positions and the ledger.
- Announces non-quiet runs to the **#updates** Discord channel; commits state.

## Guardrails (config.json → `execution`)

| Key | Default | Purpose |
|---|---|---|
| `enabled` | `true` | master on/off |
| `kill_switch` | `false` | **set `true` to halt ALL execution instantly** |
| `mode` | `"paper"` | paper only; `"live"` is intentionally unsupported here |
| `trial_end` | `"2026-08-13"` | stop opening new positions after this date |
| `market_hours_only` | `true` | only trade while the market is open |
| `max_open_positions` | `null` | **unlimited** (Quinn: execute every signal) |
| `max_position_usd` | `buy_amount_usd` ($10) | per-order size |
| `per_name_max_usd` | = per-order size | don't stack a name past this (anti-double-buy) |
| `daily_deploy_cap_usd` | `null` | **unlimited** — no daily cap |
| `sell_cooldown_hours` | `24` | per-(ticker,exit) cooldown, mirrors sell_check |
| `option_premium_usd_cap` | `3000` | skip a call idea if 1 contract (premium×100) costs more (raised from the `300` code default 2026-07-15 — real conviction-call ideas run $2.6k-$5.2k/contract, so $300 skipped nearly everything) |
| `option_profit_target_pct` | `0.50` | close a call at +50% premium gain |
| `option_stop_loss_pct` | `-0.50` | close a call at -50% premium loss |

The only active guards are the kill switch, paper buying power, and the per-name
anti-double-buy cap (one $10 position per name, so a duplicate alert can't stack
it). Everything else executes.

## vs-SPY tracking (exact benchmark)

Every fill records `spy_at_trade` — SPY's price at the moment of that trade. The
benchmark is a **matched dollar-cost SPY**: every $10 the algo puts into a stock,
$10 goes into SPY at the same instant, and the SPY leg closes when the stock's
lot does. At any moment both routes hold identical cost-basis capital — the value
gap is the alpha (no cash-drag artifact, since SPY is funded only when the algo
funds a trade). Buys/sells are **FIFO lot-matched**, so repeated round-trips in
one name pair correctly (first sell ↔ first buy).

`./venv/bin/python execute.py --report` prints two things:
- **Head-to-head snapshot** — per position and total: stock return vs SPY-matched
  return vs alpha (open positions marked to now; closed to their exit).
- **Daily equity curve** — both routes valued at each day's close over the trial,
  with running alpha, so you can watch them track/diverge day by day.

## Trial end (2026-08-13) — auto-flatten

On/after `trial_end` the executor **liquidates the entire paper book once**
(idempotent), posts a 🏁 TRIAL COMPLETE summary, and then stays idle. Run
`execute.py --report` for the final vs-SPY tally and disable the `execute` cron
card.

**Kill switch (two independent paths):**
1. **Out-of-band (preferred, no commit needed):** set the GitHub Actions repo
   *variable* `STOCKMON_KILL_SWITCH` to `true` — Settings → Secrets and
   variables → Actions → Variables, or
   `gh variable set STOCKMON_KILL_SWITCH --body true`. The next run halts and
   posts a notice. This works even when pushes are failing or repo state is
   suspect, because it doesn't travel through git. Clear it with
   `gh variable delete STOCKMON_KILL_SWITCH` (or set it to `false`).
2. **In-repo fallback:** flip `config.execution.kill_switch` to `true` and push
   (or edit it in the repo on GitHub). Same effect, but requires a commit.

## Activation (one-time, requires you)

1. **Create a free Alpaca account** and open a **paper** account (no funding, no
   real money): <https://alpaca.markets>. Generate **paper** API keys, and
   enable **options trading** on that paper account (account-level setting —
   required for the call-buying pass, separate from the equity keys below).
2. **Add two GitHub repo secrets** (Settings → Secrets and variables → Actions):
   `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` (the paper keys).
3. **Add a cron-job.org card** for `execute.yml` (recipe = Card 5 in
   `CRON_TRIGGERS.md`): every 15 min, market hours, Mon–Fri.
4. That's it — it starts trading paper on the next fresh `buy_alert`. Watch the
   🤖 **PAPER EXECUTOR** posts in #updates and the Alpaca paper dashboard.

Until the secrets exist, every run no-ops harmlessly, so steps can be done in any
order.

## After the trial (2026-08-13)

`execute.py` stops opening new positions after `trial_end` on its own. To stop it
completely, disable the `execute` cron-job.org card. Then compare the paper book
to the machine signals (`signal_tracker`, `performance.py`) — a clean
100%-adherence record is exactly what `EVALUATION_PROTOCOL.md` wants for the
Oct 13 out-of-sample review, and it's the evidence for whether to ever go live.

## Run manually

```
./venv/bin/python execute.py --dry-run   # compute intended orders, place NOTHING
./venv/bin/python execute.py --force      # ignore the market-hours gate (testing)
./venv/bin/python execute.py --report     # paper book vs SPY (alpha per position + total)
```
