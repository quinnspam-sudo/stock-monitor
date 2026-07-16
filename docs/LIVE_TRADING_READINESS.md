# Live-trading readiness checklist

**Status: NOT a build task.** This system is paper-only and stays that way
for the current trial (through 2026-08-13). None of the items below are
being implemented now. This document exists so that if a decision to trade
real money is ever made, there is a pre-agreed gate to pass — not a config
flag to flip. See the trading boundary in [CLAUDE.md](../CLAUDE.md) and the
"already known and tracked" section of [SECURITY.md](../SECURITY.md).

Derived from the 2026-07-15 Codex audit's live-trading guidance, mapped to
this repo's actual code.

## What is already true (paper-side facts, verified in code)

- `paper=True` is hard-wired: `TradingClient(api, sec, paper=True)` at
  [broker.py:136](../broker.py), with no live code path in that module.
- `execute.py` refuses any non-paper mode: `if ex["mode"] != "paper": ...
  halting` at [execute.py:649](../execute.py).
- A kill switch exists (`config.execution.kill_switch`) and halts all
  execution at [execute.py:644](../execute.py) — but it lives *inside* the
  repo it controls (in-band; see item 5).
- Idempotency-by-signal exists: `executed_orders.json` dedups signals so a
  re-run doesn't re-buy ([execute.py:156](../execute.py)) — but order
  *submission* itself is not idempotent (see item 2).
- A reconcile pass compares Alpaca positions against the ledger each run
  ([execute.py:619](../execute.py)) — but only as a symbol-set diff (item 6).
- Broker-unavailable degrades gracefully — `connect()` returns `None` and
  the run skips ([broker.py:121](../broker.py)). Correct for paper;
  fail-*open* behavior a live system must not have (item 7).

## The gate — every item must be true before the first real order

1. **Private state store.** Real trade ledgers, order IDs, positions, and
   account values live in private storage — not this public repo, not git
   at all. See the forward-looking note in
   [DATA_CLASSIFICATION.md](DATA_CLASSIFICATION.md). CLAUDE.md already
   bans using git commits as an order/position database beyond the paper
   experiment. **Not true today:** all execution state is committed to a
   public repo by the workflows' `STATE_FILES` allowlists.

2. **Idempotent order submission.** Every order carries a deterministic
   client-order ID derived from the signal, so a crash/retry/duplicate run
   can never double-submit. **Not true today:** `buy_notional()` /
   `buy_option()` ([broker.py:73](../broker.py)) submit without a client
   order ID; dedup happens only after the fact via `executed_orders.json`,
   which is written at the *end* of the run ([execute.py:689](../execute.py))
   — a crash between submit and persist re-submits.

3. **Dedicated broker account isolation.** Live trading uses a separate
   Alpaca account, separate keys, separate ledger, separate deployment and
   alert channel from paper — never shared, per CLAUDE.md's trading
   boundary. **Not true today:** only one (paper) account exists.

4. **Non-null risk limits, enforced.** `max_open_positions`,
   `max_position_usd`, `per_name_max_usd`, and `daily_deploy_cap_usd` are
   all `null` in [config.json](../config.json) — intentional for the paper
   trial's 100%-adherence record, unacceptable for live. Live config must
   require non-null values and the executor must refuse to start without
   them (today the guards are simply skipped when `null`,
   [execute.py:180-185](../execute.py)).

5. **Out-of-band kill switch.** A halt mechanism that does not depend on
   this repo, GitHub Actions, or a git push landing — e.g. revoking the
   broker key or a broker-side trading block. Today's
   `config.execution.kill_switch` requires committing to the same pipeline
   it's meant to stop.

6. **Real reconciliation.** Beyond `reconcile()`'s symbol-set comparison:
   share/contract quantities, cost basis, cash, and pending orders must
   match, with a hard halt (not a Discord note) on drift.

7. **Fail-closed credentials and connections.** Missing keys, a failed
   connection, or unparseable config must abort loudly, not skip quietly.
   `broker.connect()`'s return-None-and-continue and `_load()`'s
   silent-default ([execute.py:83](../execute.py)) are the opposite of
   this, by design, for paper.

8. **Incident response procedures.** Written runbooks for: runaway orders,
   credential compromise (extend [SECURITY.md](../SECURITY.md)'s rotation
   runbooks to live keys), broker outage mid-position, and reconciliation
   drift — including who acts and within what time.

9. **A separately approved live-trading design.** CLAUDE.md requires this
   before removing `paper=True` or adding any live mode — a reviewed
   design doc, not an edit to `broker.py`.

10. **Human sign-off recorded in the repo.** The go-live decision is a
    commit that references this checklist with every item checked, made
    deliberately by Quinn.

---

This checklist exists so that a future decision to go live is a
deliberate, reviewable act — not a config flag flip.
