# Watchlist Discovery Engine (`discover.py`)

Draws genuinely new names into the watchlist on a **rigorous-but-optimistic**
bar, and prunes structurally-dead ones. Added 2026-07-13.

## The one idea

Discovery answers a *different* question than the monitor:

| | Question | Gates on |
|---|---|---|
| **monitor.py** | "Should we buy this **right now**?" | live timing + market **regime** + consensus supermajority |
| **discover.py** | "Is this a name worth **watching**?" | durable quality (real fundamentals, conviction tier, no structural veto) — **but not** timing/regime |

A name can be an excellent watchlist candidate while today's tape would
(correctly) block a BUY. Discovery keeps the rigorous quality floors and drops
the timing/regime gates that are the monitor's job. That separation is the whole
design: promising names get *in*; the monitor still decides, unchanged, *when* —
or whether — any of them ever alert.

## Frozen-rules boundary

Per `EVALUATION_PROTOCOL.md` the trading rules (entry/exit thresholds) are FROZEN
until 2026-10-13. Discovery only curates watchlist **membership**. Adding a name
cannot change how or when the frozen rules fire on it — it only makes the monitor
start watching it. Discovery thresholds themselves (the `discovery` block in
`config.json`) are *new* and may be calibrated freely; they are not the frozen
rules.

## The rigorous-but-optimistic gate (`qualifies()`)

**RIGOROUS floors** — all must hold, or the name is rejected (and put on a
30-day re-look cooldown so we don't re-score the same rejects every week):

- factor conviction tier is **not UNRATED** (real fundamentals resolved)
- `confidence >= min_confidence` (45) — enough real data, not mostly gaps
- `overall >= min_overall` (60/110) — above the proxy midpoint
- **no structural veto** — F-Score ≤ 3, estimate revisions < −2%, or 6-mo
  momentum < −10% (falling knife). The *regime* veto is deliberately ignored
  here — a hostile tape is a reason not to **buy**, not a reason not to **watch**.

A **MEDIUM or HIGH** conviction tier is required to be admitted at all — LOW
tier (factor conviction < 50) can never enter, even at a strong price. (The
first live run exposed this: LOW-tier names were slipping in via the
near-buyable branch on price proximity alone — not actually rigorous.)

**OPTIMISTIC promise** — any one admits a MEDIUM/HIGH name that cleared the floors:

- conviction tier **HIGH**, or
- ≥10% **revenue** growth (earningsGrowth is *not* used — a tiny prior-year EPS
  base explodes the % on turnaround names; the first live run waved in names on
  +680%/+990%/+1250% earnings noise, so only revenue growth qualifies now), or
- **near-buyable**: blended score within 12 of `alert_threshold`, or
- **hyper-growth**: ≥20% revenue growth with overall ≥ 65

Calibrated to a natural handful per run — **not a quota**. A per-run safety
ceiling (`per_run_add_cap`, 12) only trips as a logged circuit breaker — it
keeps a big cold-start backlog from dumping into an already-large watchlist; if
it recurs steadily, recalibrate the gate deliberately (same discipline as
`consensus.SUPERMAJORITY`).

## Sourcing (free + dynamic)

1. **Yahoo predefined screens** via `yf.screen` — growth / undervalued /
   aggressive-small-cap / most-active cross-sections (the optimistic net).
2. **Sector top-companies** (`yf.Sector`) for the non-tech sectors a tech-heavy
   book is thin on — the diversification injector.
3. **Curated seed** — reuses `grow_watchlist.POOL` as a fallback (not duplicated).

Deduped against the watchlist, ETFs, prior adds/prunes, and cooling rejects.
Each candidate is scored with the **exact** monitor pipeline
(`score_ticker → committee.gather → factors.compute → conviction →
consensus.evaluate`) — no parallel math. The eval budget (120/run) caps yfinance
load; anything past it queues for next run (and is announced).

## Diversification

Admitted names are ranked by `blended score + under-representation bonus`, so a
book flagged 100%-correlated-tech fills its thin themes first. The bonus is
ordering only — it never gates admission (the quality bar does that).

## Pruning (confirmation-gated, cheap)

Reads `watchlist_health.json` — the report `watchlist_health.py --deep` already
produces every Friday — rather than re-scanning 420 names. A name flagged dead
(no price, or UNRATED fundamentals → can never alert, e.g. BESIY/DSCSY) must
appear dead `prune_confirmations` (2) runs running before removal. Anything that
recovers resets its counter.

## Integration points

- **Auto-adds** to `config.json` (watchlist + the right thematic category) and
  seeds `scores.json` + `history.json` so new names have scores immediately.
- **Announces** every run to the **#updates** Discord channel (never the BUY
  channel — discovery is not a buy signal): adds, prunes, top near-misses.
- **Logs** everything to `discover_log.json`; cooldowns/prune-counters/source
  cursor live in `discover_state.json`.
- **Weekly payload**: `discover.report_lines()` feeds a section into
  `weekly.py`'s committee review.
- **Reversible**: `./venv/bin/python watchlist.py remove TICKER`.

## Run

```
./venv/bin/python discover.py            # full run: source, add, prune, push, announce
./venv/bin/python discover.py --dry-run  # score + rank + print, mutate NOTHING (propose mode)
./venv/bin/python discover.py --no-prune # add only
./venv/bin/python discover.py --report   # print the last run's summary
```

## Schedule

`discover.yml` runs on `workflow_dispatch`, triggered by a **cron-job.org** card
(GitHub native `schedule:` doesn't fire on this repo — see `CRON_TRIGGERS.md`).
Suggested slot: **Saturday 09:00 PT** — after Friday's `weekly.py` refreshes
`watchlist_health.json` (the prune input), on a weekend so a batch of yfinance
fetches never competes with weekday monitor/options runs.

## Tuning (`config.json` → `discovery`)

All thresholds live in the `discovery` block. The ones you'd actually touch if
the add rate drifts: `min_overall`, `min_confidence`, `near_buy_margin`,
`growth_floor`, `hypergrowth` (the gate), `eval_budget` (cost/coverage),
`per_run_add_cap` (circuit breaker), `prune_confirmations` (prune caution).
