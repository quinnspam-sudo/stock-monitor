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

The only active guards are the kill switch, paper buying power, and the per-name
anti-double-buy cap (one $10 position per name, so a duplicate alert can't stack
it). Everything else executes.

## vs-SPY tracking (exact benchmark)

Every fill records `spy_at_trade` — SPY's price at the moment of that trade — so
the benchmark is measured from the same instant as the trade, not the day's
close. `./venv/bin/python execute.py --report` prints, per position and in
aggregate, the stock return vs what the same $10 in SPY at the same instant would
have done (the alpha). This is the clean out-of-sample scorecard for the trial.

## Trial end (2026-08-13) — auto-flatten

On/after `trial_end` the executor **liquidates the entire paper book once**
(idempotent), posts a 🏁 TRIAL COMPLETE summary, and then stays idle. Run
`execute.py --report` for the final vs-SPY tally and disable the `execute` cron
card.

**Kill switch:** flip `config.execution.kill_switch` to `true` and push (or edit
it in the repo on GitHub) — the next run halts and posts a notice. Nothing else
needed.

## Activation (one-time, requires you)

1. **Create a free Alpaca account** and open a **paper** account (no funding, no
   real money): <https://alpaca.markets>. Generate **paper** API keys.
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
