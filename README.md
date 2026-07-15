# stock-monitor

Watchlist monitor that scores stocks on momentum/trend signals and posts BUY alerts
to a private Discord server via webhook. Recommends only — never trades.

## How the ecosystem works (start here)

This isn't a single script — it's a small pipeline of scheduled jobs that all read/write
a shared set of JSON files in this repo, and talk to Discord for notifications:

1. **Scoring engine** (`monitor.py`, `factors.py`) — pulls price data from yfinance,
   computes an 11-category momentum/trend score per watchlist ticker, and diffs it
   against the last known score (`scores.json`). Crossing `alert_threshold` fires a
   Discord BUY alert.
2. **Notifications** (`notify.py`) — all Discord posting goes through here, routed to
   one of several webhooks depending on message type (buy alerts, updates, sells).
   Output only — Discord is not polled for anything (the old inbound buy-log bot
   was retired 2026-07-15, see below).
3. **Committee pipeline** (`committee.py`, `COMMITTEE_PROTOCOL.md`) — when a score move
   is big enough, writes a payload to `committee_prompts/` for you to manually paste into
   a Claude Pro chat, which acts as an "investment committee" and returns a verdict. This
   step is manual by design — it's not automated by API.
4. **Discovery** (`discover.py`, `DISCOVERY.md`) — weekly job that grows/prunes the
   watchlist automatically using free Yahoo screens, scored with the same pipeline.
5. **Paper execution** (`execute.py`, `broker.py`, `EXECUTION.md`) — optional: places
   *paper* (fake-money) trades on Alpaca for fresh BUY alerts and applies mechanical
   exit rules to open paper positions. Also fully executes `options_engine.py`'s
   conviction-call ideas as 1-contract paper option buys, with the same mechanical
   exit rules. No-ops entirely if Alpaca keys aren't set.
6. **Ledgers** — `recommendations.json` ("what the system said to do") and
   `actual_trades.json` ("what was actually bought/sold", auto-written by
   `execute.py`) are tracked separately and compared with `performance.py`.
7. **Scheduling** — in this fork, all of the above run as GitHub Actions
   (`.github/workflows/*.yml`), triggered by an external cron service (cron-job.org)
   calling each workflow's `workflow_dispatch` endpoint, since GitHub's native
   `schedule:` trigger was unreliable on this repo. Each run commits its updated
   state files back to the repo so the next run picks up where the last left off.
8. **Obsidian sync** (`obsidian.py`, `obsidian_sync.py`) — optional: mirrors every
   alert/payload into a local Obsidian vault. Purely cosmetic/archival — nothing else
   depends on it, and it's best-effort (failures never break monitoring).
9. **Dashboard** (`dashboard.py` → `dashboard.html`) — static ranked scoreboard,
   regenerated on every run.

Everything is **recommend-only by default**. The only thing that can place a real
(paper) order is `execute.py`, and it requires its own credentials to do anything.

## Forking this: what you'll need

To replicate this for yourself, fork the repo, then:

### 1. Required — Discord webhook (for any alerts at all)
- Create a Discord server (or channel in an existing one).
- **Server Settings → Integrations → Webhooks → New Webhook** → copy the URL.
- This becomes `DISCORD_WEBHOOK_URL`.

### 2. Set up secrets
Two ways to supply credentials, matching where the code runs:

**Locally** — create `secrets.json` in the repo root (already gitignored, never commits):
```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/...",
  "discord_updates_webhook_url": "https://discord.com/api/webhooks/...",
  "discord_sell_webhook_url": "https://discord.com/api/webhooks/...",
  "obsidian_vault": "/absolute/path/to/your/vault"
}
```
Only `discord_webhook_url` is required to get basic alerts working; the rest are
optional depending on which features you use (see table below).

**GitHub Actions** (if you want it running in the cloud like this fork does) — add
the same values as **repo secrets**: Settings → Secrets and variables → Actions →
New repository secret. The workflow YAMLs already reference these names, so no
code changes needed:

| Secret name | Required for | Where to get it |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Basic BUY alerts (`monitor.yml`) | Discord webhook, see above |
| `DISCORD_UPDATES_WEBHOOK_URL` | Intraday/close/weekly updates | Discord webhook, separate channel recommended |
| `DISCORD_SELL_WEBHOOK_URL` | Sell-signal alerts (`sell_check.yml`) | Discord webhook, separate channel recommended |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | Paper-trading executor (`execute.yml`) | Free [Alpaca](https://alpaca.markets) account → Paper Trading → API keys. Without these, `execute.py` just no-ops |

Nothing here needs a **paid** API — yfinance (free), Discord (free), Alpaca paper
trading (free) are all that's required. Obsidian sync is entirely optional and only
matters if you use Obsidian locally.

### 3. Wire up the cron scheduler (optional, only if you want it fully automated)
GitHub's own `schedule:` trigger can silently never fire on new repos/accounts (see
"Scheduled jobs" below for what happened here). If that happens to you too:
1. Generate a fine-grained GitHub PAT scoped to **Actions: write** on your fork only.
2. Create a free [cron-job.org](https://cron-job.org) account.
3. One job per workflow, POSTing to
   `https://api.github.com/repos/<you>/<repo>/actions/workflows/<file>.yml/dispatches`
   with `Authorization: Bearer <PAT>` and body `{"ref":"main"}`, on the schedule you want.
4. See `CRON_TRIGGERS.md` for the exact schedule this fork uses, and remember your PAT
   will expire — set a calendar reminder to rotate it.

Otherwise you can just run any script manually (`./venv/bin/python monitor.py`) or rely
on GitHub's native `schedule:` triggers, which work fine on established accounts/repos.

### 4. Local Python setup
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python notify.py       # sanity check: should post to Discord
./venv/bin/python monitor.py --dry-run   # score watchlist, no alerts sent
```

### 5. Customize
- `config.json` — your watchlist, alert thresholds, buy amount, categories.
- `EVALUATION_PROTOCOL.md` — the frozen scoring/exit rules; edit with care, these are
  what everything downstream (execution, sell rules) trusts.
- `COMMITTEE_PROTOCOL.md` — the manual Claude Pro committee workflow, optional.

---

## Setup (one time)

1. Create a private Discord server (or use an existing one) and a channel like `#buy-alerts`.
2. In Discord: **Server Settings → Integrations → Webhooks → New Webhook** →
   pick the channel → **Copy Webhook URL**.
3. Paste that URL into `secrets.json` (create it if missing) as `discord_webhook_url`:
   ```json
   {"discord_webhook_url": "https://discord.com/api/webhooks/..."}
   ```
   `secrets.json` is gitignored — the webhook never lands in version control or an
   `ultrareview`/`git init` of this folder. (You can also set the `DISCORD_WEBHOOK_URL`
   env var instead, which takes priority.)
4. Test it: `./venv/bin/python notify.py` — you should see a message in the channel.

## Usage

```bash
./venv/bin/python monitor.py            # score watchlist, send alerts for scores >= threshold
./venv/bin/python monitor.py --dry-run  # score only, no Discord messages
```

## Config (`config.json`)

- `watchlist` — tickers to monitor
- `alert_threshold` — score (0–100) required to trigger a BUY alert (default 75)
- `cooldown_hours` — suppress repeat alerts for the same ticker (default 24)

`obsidian_vault` (path to the Obsidian vault to mirror payloads into) lives in
`secrets.json` — a local absolute path stays out of git history (legacy
config.json fallback still works).

Secrets (`discord_webhook_url`) live in `secrets.json`, not `config.json` — see Setup above.

## Scheduled jobs (GitHub Actions + cron-job.org, runs even when the Mac is off — 2026-07-08)

As of 2026-07-07 the actual monitoring runs entirely on GitHub Actions
(`.github/workflows/*.yml` in the public repo `quinnspam-sudo/stock-monitor`),
not on this Mac — so alerts fire whether or not this machine is on, awake, or
connected to WiFi. Each workflow scores/checks, posts to Discord, then commits
updated state (`scores.json`, `history.json`, `committee_prompts/`, etc.) back
to the repo so the next run picks up where the last one left off.

**Trigger mechanism (as of 2026-07-08):** the workflows' own `on: schedule:`
cron triggers never fired — GitHub silently throttles native scheduled
workflow runs on brand-new accounts/repos as an anti-abuse measure (manual
`workflow_dispatch` worked reliably the whole time; 0 of dozens of scheduled
tick opportunities ever ran). There's no visible toggle for this and no
guaranteed clear time, so scheduling was moved to **cron-job.org** (free
external scheduler) calling each workflow's `workflow_dispatch` REST endpoint
directly — one job per workflow (`monitor.yml` needs two, for its two
different minute-patterns) on the exact same schedule the removed
`schedule:` blocks had. As of 2026-07-09 every cron-job.org job runs in
timezone **America/Los_Angeles** (originally UTC — which would have made
close/weekly fire BEFORE the closing bell once DST ended in November,
since the market is ET-anchored and US zones shift together). Job titles
`close-1335pt` and `monitor-1300pt` reflect the Pacific times. Manage/inspect the jobs at cron-job.org's console (account is Quinn's);
the API token used is a fine-grained GitHub PAT scoped only to this repo's
Actions permission, expiring ~2026-08-07 (30 days from creation — needs
rotating before then or the jobs will start failing with 401s).

- `monitor.yml` — every 15 min, ~6:00–13:00 PT Mon–Fri: scores, delta triggers, Template A payloads
- `pulse.yml` — hourly ~7:00–12:00 PT Mon–Fri: Template C intraday pulse payload
- `close.yml` — ~13:35 PT: Template D closing bell payload
- `options.yml` — daily 12:45 PT Mon–Fri (during market hours, so option chain
  quotes are live and alerts are actionable same-day): independent options-engine
  scan (watchlist + `etf_watchlist`), CALL_CONVICTION alerts + OPTIONS_SCAN
  heartbeat digest
- `weekly.yml` — Friday ~13:45 PT: weekly performance review payload (verdicts vs
  SPY, options book, machine-vs-committee signal tracker)
- `backtest.yml` — Saturday ~09:00 PT: backtests the *local scoring engine's* calls
  (not committee verdicts — that's `weekly.py`) against what each ticker actually
  did over the Mon–Fri just finished, using `history.json` snapshots
- `sell_check.yml` — hourly ~7:00–12:00 PT Mon–Fri: checks REAL open positions
  (`actual_trades.json`, computed via average-cost-basis accounting in
  `performance.py`) against market-conditioned mechanical sell rules — a
  -15% stop-loss and a 25% trailing stop off the peak close since entry,
  both active ONLY while SPY is above its 50-day SMA (a stock falling in a
  healthy market is idiosyncratic — cut it; falling with the market usually
  recovers with it); an unconditional -30% disaster floor; and the Magic
  Formula annual rebalance (365+ days held). Rules were retuned per
  `committee_prompts/2026-07-13_EXIT_RULES_BACKTEST.md` (the old -7% stop /
  +20% take-profit / Darvas 20-day breakdown erased the buy signal's alpha;
  market-conditioned stops were the best exit tested over 6m/1y/5y windows).
  Posts to a third, separate `#sell-alerts` channel/webhook
  (`discord_sell_webhook_url`), independent of the buy/updates split above.
  Every firing is also logged to `recommendations.json` (kind="sell_signal").
  Only covers tickers with an open position in `actual_trades.json` — not
  recommendations, since a stop-loss only makes sense against a real entry.
- `buy_intake.yml` — **retired 2026-07-15** (moved to `workflows_legacy_backup/`).
  Used to poll a Discord `#buy-log` channel via a real Discord Bot every 15
  min, all day, for hand-typed trade messages and record them into
  `actual_trades.json`. Made redundant once `execute.py` started
  auto-executing and auto-logging every trade to that same ledger directly —
  Discord's role is output-only now. Was ~1,585 GH Actions min/month for a
  channel nothing was posting to anymore.
- `execute.yml` — every 15 min, market hours Mon–Fri (5 min after `monitor`):
  the **paper-trading executor** (`execute.py`) — places Alpaca *paper* orders
  for fresh `buy_alert` signals and applies the frozen exit rules to open paper
  positions, writing the same `actual_trades.json` the Discord buy-log bot does.
  Removes the human-lag execution step; **paper only**, fully guardrailed, kill
  switch in `config.json`. One-month trial → 2026-08-13. Requires `ALPACA_*`
  secrets or it no-ops. See `EXECUTION.md`.
- `discover.yml` — Saturday ~09:30 PT: the watchlist discovery engine
  (`discover.py`) — sources new names from free Yahoo screens + sector
  top-companies, admits the ones clearing the rigorous-but-optimistic gate
  (favouring under-represented themes), and prunes structurally-dead names.
  Runs after Friday's `weekly.py` refreshes `watchlist_health.json` (the prune
  input). Adds to the watchlist only — never touches the frozen trading rules.
  See `DISCOVERY.md`.

### Two separate ledgers — recommendations vs actual trades (2026-07-08)

`recommendations.json` ("what did the system say to do") and
`actual_trades.json` ("what did I actually do") are deliberately never
merged:
  - `recommendations.json` — committee verdicts (`verdict.py add`, kind
    `committee_verdict`), real BUY alerts (`monitor.py`, kind `buy_alert`),
    and sell signals (`sell_check.py`, kind `sell_signal`)
  - `actual_trades.json` — real buys/sells, auto-written by `execute.py`

Compare the two anytime with `performance.py`:
```bash
./venv/bin/python performance.py actual                       # open positions (unrealized) + closed lots (realized)
./venv/bin/python performance.py recommendations               # every recommendation's % change vs price now
./venv/bin/python performance.py recommendations --kind buy_alert
```
Both are also mirrored into Obsidian as two separate running logs:
`Recommendations Log.md` and `Actual Trades Log.md` (under
`Claude-Code/Stock Monitor/`), so browsing the vault keeps the same
never-merged separation.

Cron times assume PDT (UTC-7); during standard time (~Nov–Mar) runs land about
an hour later than the equivalent PT time — harmless slack given the
noise-suppression thresholds, but adjust the cron lines by 1hr if exact PT
alignment matters. `monitor.py`/etc. still self-check `market_open_today()` /
real session windows, so an off-by-an-hour cron fire never produces bad data,
just a wasted/no-op run.

The Discord webhook lives only as an encrypted repo secret
(`DISCORD_WEBHOOK_URL`), never committed. If a workflow run fails (including
if Discord posting itself fails — see notify.py's `FAILURES` tracking) the
job goes red and GitHub emails the repo owner by default, so a broken webhook
can't fail silently forever.

### Local Mac's role now: Obsidian sync only

The old `~/Library/LaunchAgents/com.stockmonitor.*.plist` jobs are retired
(backed up in `launchd_legacy_backup/`, not deleted). The only local job left
is `com.stockmonitor.obsidiansync.plist`, which runs once daily at 1:30pm
Pacific (shortly after the 1pm PT market close) and on wake-catchup: it pulls
the repo, replays any Obsidian events
GitHub Actions queued while the Mac was off (`obsidian_queue.jsonl`) into the
real Jarbis vault via `obsidian_sync.py`, using each event's original
timestamp — so catch-up entries file under the day/week/month they actually
happened on, not the day they were synced. Then it pushes the cleared queue
back so nothing replays twice.

All jobs skip market holidays automatically (`--force` overrides). Output appends
to `monitor.log` (auto-rotated at ~1 MB). Edit schedule with `crontab -e`.

## Obsidian integration

All pings are offloaded to the Jarbis vault (`obsidian_vault` in config.json)
under `Claude-Code/Stock Monitor/`:

- `Pings/YYYY-MM-DD.md` — every alert/notice appended to a daily note
- `Weeks/YYYY-Www.md` — rollup of that ISO week's day notes, plus any weekly
  review/backtest payloads dated within it
- `Months/YYYY-MM.md` — rollup of that month's week notes
- `Committee Payloads/` — every payload mirrored with frontmatter
  (`status: awaiting-verdict`) so you can paste into Claude Pro from Obsidian.
  Recording a verdict (`verdict.py add`) flips the status to `verdict-recorded`
  and appends the rating/entry/note directly onto the payload note.
- `Tickers/TICKER.md` — per-ticker rollup: every committee payload and recorded
  verdict for that name in one note, so you can browse "everything ever said
  about NVDA" instead of hunting through daily pings. Regenerated automatically
  whenever a new payload is mirrored or a verdict is recorded.
- `Stock Monitor Hub.md` — index note; links to the current day/week/month note

Every day note links up to its week note, which links up to its month note,
which links up to the Hub — the vault is browsable day-by-day, week-by-week, or
month-by-month, not just as a flat pile of daily files. All three levels
(day/week/month) regenerate automatically on every ping, so they never drift.

Vault writes are best-effort: Obsidian problems never break monitoring.

## Dashboard

Every monitor run regenerates `dashboard.html` (ranked scoreboard with ratings,
intraday deltas, earnings proximity, sectors). Open it once and leave it up:

```bash
open ~/Claude/stock-monitor/dashboard.html   # auto-refreshes every 5 min
```

## Watchlist management

```bash
./venv/bin/python watchlist.py list          # tickers with current scores/ratings
./venv/bin/python watchlist.py add PLTR      # validates ticker before adding
./venv/bin/python watchlist.py remove TSLA   # also clears its ledger entry
```

### Automatic discovery (`discover.py`)

`discover.py` grows the watchlist on its own, weekly, on a **rigorous-but-
optimistic** bar — it asks "is this worth *watching*?" (durable quality, no
timing/regime gate) rather than the monitor's "should we buy it *now*?". It
sources new names from free Yahoo screens + sector top-companies, scores them
with the exact monitor pipeline, auto-adds the ones that clear the gate (into
the right thematic category, favouring under-represented themes), and prunes
structurally-dead names that can never alert. Every run is announced to
#updates and logged. It only curates watchlist membership — the frozen trading
rules (`EVALUATION_PROTOCOL.md`) still decide if/when any name alerts. Full
design in **`DISCOVERY.md`**.

```bash
./venv/bin/python discover.py            # full run (also runs Saturdays via discover.yml)
./venv/bin/python discover.py --dry-run  # propose mode — score/rank/print, change nothing
./venv/bin/python discover.py --report   # last run's summary
```

## Discord field guide

`./venv/bin/python guide.py` posts the alert field guide (every output type,
meaning, and call to action) to Discord — re-run after changing any output
format, and keep it pinned in the channel.

## Verdict journal (closing the loop)

After pasting a payload into Claude Pro and getting a committee verdict, record it:

```bash
./venv/bin/python verdict.py add AAPL "Buy" --entry 308 --note "margin expansion thesis"
./venv/bin/python verdict.py review   # performance of every verdict vs price since
```

## Weekly backtest (accuracy check)

Every Saturday, `backtest.py` grabs the first rating each ticker got during the
week just finished (from `history.json`) and checks it against that ticker's
actual return over the same week:

```bash
./venv/bin/python backtest.py --force   # run manually any day (skips the Saturday check)
```

Reports, per rating bucket (Buy/Strong Buy, Watch/Hold, Reduce/Sell): average
return, hit rate, and win rate vs SPY — plus whether top-half-scored tickers
actually beat bottom-half-scored ones that week (the core "does the scoring
signal mean anything" check). Output is a payload in `committee_prompts/`
(mirrored to Obsidian like other payloads) and a running history in
`backtest_log.json` so accuracy trends are visible over time, not just
week-to-week.

## Files

- `config.json` — watchlist, thresholds, Discord webhook
- `scores.json` — ledger of last proxy scores per ticker (delta baseline)
- `history.json` — intraday score history, last 30 days (feeds close.py)
- `recommendations.json` — "what did the system say to do": committee verdicts,
  real BUY alerts, sell signals (see performance.py)
- `actual_trades.json` — "what did I actually do": real buys/sells,
  auto-written by `execute.py` (see performance.py)
- `backtest_log.json` — weekly scoring-accuracy history (from `backtest.py`)
- `committee_prompts/` — generated payloads for Claude Pro (auto-pruned after 14 days)
- `alert_state.json` — Discord alert cooldowns
- `sell_alert_state.json` — sell-signal cooldowns (per ticker+kind)
- `discord_intake_state.json` — unused since buy_intake.yml was retired
  2026-07-15 (was the buy-log bot's last-processed Discord message ID)
- `discover_log.json` — every discovery run's adds/prunes/near-misses (from `discover.py`)
- `discover_state.json` — discovery reject cooldowns + prune-confirmation counters
- `watchlist_health.json` — dead-name report (from `watchlist_health.py`; read by the prune pass)
- `executed_orders.json` — paper-executor dedup ledger of orders placed (from `execute.py`)
- `execution_state.json` — paper-executor per-(ticker,exit) cooldowns + last run

## Committee pipeline (manual Claude Pro workflow)

Each run, [committee.py](committee.py) computes proxy scores for all 11 categories
(/110) plus timing and confidence from yfinance data, and diffs them against the
`scores.json` ledger. Only when a Phase 3 threshold is breached (overall Δ≥8,
timing Δ≥15, confidence Δ≥10pp, or first evaluation) does it write a consolidated
payload to `committee_prompts/` and ping Discord that payloads are ready. Paste
the payload file into your Claude Pro committee session to get the Template output.
Data yfinance can't provide (congressional trades, options skew, etc.) is marked
`Data Status: GAPPED` in every payload.

## Scoring

Current score is momentum/trend only (price vs 50-day SMA, 1/3-month returns,
proximity to 3-month high, RSI, volume confirmation) — a placeholder to expand
with fundamentals, earnings revisions, insider buying, etc. per the larger system design.
