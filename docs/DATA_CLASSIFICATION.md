# Data classification

This repo is **public**, and everything tracked in git is public forever
(history persists — see [CLAUDE.md](../CLAUDE.md), "Security and trading
invariants"). This document makes explicit which class every category of
data this repo handles belongs to, so nothing lands in git by accident of
being "just another state file."

Three classes:

| Class | Meaning |
|---|---|
| **Public** | Tracked in git by design; fine for anyone to read, forever. |
| **Internal** | Not a credential, but shouldn't be published. Kept local / gitignored. |
| **Credential** | Must never be tracked, logged, or committed — no exceptions. |

## Why the tracked trading state is public

Everything currently tracked is **paper-trading state**. Per the trading
boundary in [CLAUDE.md](../CLAUDE.md#trading-boundary): `broker.py`
hard-wires `paper=True` ([broker.py:136](../broker.py)), and `execute.py`
halts on any `execution.mode` other than `"paper"`
([execute.py:649](../execute.py)). No tracked file can contain a real
trade, position, or account value — the paper ledger is deliberately
publishable as an auditable track record. That is a *decision*, recorded
here, not an accident.

## Classification of tracked files

### Public — code and documentation
`*.py`, `research/*.py`, `.github/workflows/*.yml`, `requirements.txt`,
`README.md`, `CLAUDE.md`, `SECURITY.md`, `CODEOWNERS`, and the protocol
docs (`COMMITTEE_PROTOCOL.md`, `EVALUATION_PROTOCOL.md`, `EXECUTION.md`,
`DISCOVERY.md`, `OPTIONS_ENGINE.md`, `CRON_TRIGGERS.md`, `RESUME.md`).
Open-source pipeline code and its docs. Credentials are read only from the
environment or `secrets.json` (`broker.py:_keys()`, `obsidian.py:_vault()`) —
never from tracked files.

### Public — paper-trading ledgers (written by `execute.py`)
- `actual_trades.json` — paper fills (ticker, shares, price, `spy_at_trade`).
  Written by `_record_trade()` in [execute.py](../execute.py); identical
  schema to the retired Discord buy-log intake.
- `option_trades.json` — paper option fills (separate ledger by design; not
  yet present because no option order has filled).
- `executed_orders.json` — signal-dedup ledger with Alpaca **paper** order
  UUIDs. Order IDs of a paper account identify nothing financial.
- `execution_state.json` — sell cooldown timestamps, last-run marker.

### Public — scoring/signal/alert state (written by `monitor.py`, `options_engine.py`, etc.)
`scores.json`, `signals.json`, `history.json`, `alert_state.json`,
`sell_alert_state.json`, `alert_stats.json`, `regime_state.json`,
`options_ideas.json`, `options_state.json`, `watchlist_health.json`,
`discover_state.json`, `discover_log.json`, `grow_log.json`, `grow.out`,
`backtest_log.json`, `discord_intake_state.json`. All derived from public
market data plus this repo's own (public) scoring rules — tickers, scores,
timestamps, cooldowns. Nothing account-specific.

### Public — generated dashboards and committee prompts
- `dashboard.html`, `ecosystem.html` — rendered views of the same public
  state above (`dashboard.py`, `ecosystem.py`).
- `committee_prompts/*.md` — generated LLM prompt payloads built from
  public market data and scores. They contain no credentials or account
  data, but they're the noisiest category (~776 files); anything new added
  here should be checked against that expectation before committing.
- `obsidian_queue.jsonl` — queued vault events (alert text) written on CI
  by `obsidian.py` for `obsidian_sync.py` to replay locally. Same content
  as the Discord alerts; the vault *path* itself deliberately never appears
  here (it lives in `secrets.json`, see below).

### Public — configuration
`config.json` — watchlist, categories, thresholds, and the `execution`
block (paper guardrails, all currently `null` risk caps for the trial).
Explicitly forbidden from ever holding a secret
([CLAUDE.md](../CLAUDE.md#credentials-and-private-data)).

### Internal — local only, gitignored
- `monitor.log`, `pull_state.log` — local run logs.
- `venv/`, `__pycache__/`, `*.pyc` — build artifacts.
- The **Obsidian vault path** inside `secrets.json` (`obsidian_vault`): not
  a credential, but a personal absolute home-directory path — CLAUDE.md
  bans those from tracked files.

### Credential — never tracked, ever
Stored **only** in gitignored `secrets.json` locally or GitHub Actions repo
secrets in CI. Never in `config.json`, logs, prompts, or commits:
- Alpaca **paper** API key + secret (`ALPACA_API_KEY` / `ALPACA_SECRET_KEY`)
- Discord webhook URL / bot token
- GitHub PAT used by the cron-job.org triggers (see `CRON_TRIGGERS.md`)

Rotation procedures live in [SECURITY.md](../SECURITY.md#rotation-runbooks).
A webhook URL *is* a credential — possession is authorization.

## Forward-looking note: live trading changes everything above

If live trading is ever built (see
[LIVE_TRADING_READINESS.md](LIVE_TRADING_READINESS.md)), **real trade data
must NOT inherit the "public" classification**. Real fills, positions,
order IDs, account values, and ledgers would be **internal at minimum** and
must live in a private state store, never in this public repo — separate
account, ledger, and storage per CLAUDE.md's trading boundary. Nothing to
act on today; this note exists so the future decision is made consciously
rather than by the paper precedent.
