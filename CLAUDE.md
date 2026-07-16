# Security and trading invariants

This repository is **public**. Treat every tracked file, commit, and
workflow log as visible to anyone, forever — including after a later commit
"fixes" it, since git history persists.

Context: a 2026-07-15 security audit (Codex) of this repo found zero leaked
credentials, but flagged that the public repo is used to store trading
state, and that nothing currently stops that state from including real
trades if the retired Discord buy-log intake were ever revived. See the
conversation/PR history around that date for the full report and the
phased remediation plan (Phase 0 = this file + explicit git-add allowlists,
already done; Phases 1-5 = private state storage, idempotent order
submission, non-null risk limits, broker account isolation, out-of-band
kill switch — not yet done, required before live trading).

## Credentials and private data

- Never place credentials, webhook URLs, tokens, authorization headers,
  private keys, account identifiers, real positions, or real trade records
  in tracked files, examples, fixtures, logs, screenshots, prompts, or commits.
- Secrets live in `secrets.json` (gitignored) locally, or GitHub Actions
  repo secrets in CI — never in `config.json` or any tracked file.
- Redact credential-like values to the first four and final four characters
  if you ever need to reference one in conversation or a commit message.
- Never print secret values while debugging, including in workflow logs.
- Do not add local absolute home-directory paths to tracked files (e.g.
  `/Users/<name>/...`) — use `$HOME`, a relative path, or a placeholder.

## Git safety

- **Never use `git add -A` or `git add .` in application code or CI
  workflows.** Every `.github/workflows/*.yml` state-commit step stages an
  explicit `STATE_FILES` allowlist for exactly this reason (fixed
  2026-07-15) — if you add a workflow or a script starts writing a new
  state file, add that file to the relevant workflow's `STATE_FILES` list
  by name. Don't reach for `-A` as a shortcut.
- Stage only an explicit, reviewed list of files — same rule applies to
  interactive `git add` when committing by hand in this repo.
- Treat generated logs, ledgers, order IDs, execution state, and dashboards
  as private-by-default unless there's a specific reason they're meant to
  be public (this repo currently publishes paper-trading state only —
  see the audit note above).
- Before a commit that touches trading/execution code, inspect the staged
  diff for anything that looks like a secret, a personal path, or real
  (non-paper) trade data.
- Do not rewrite history or rotate/revoke credentials without explicit
  approval from Quinn — this repo's history has been surgically rewritten
  once before for a privacy fix (see commit `0689201` and its predecessor),
  so treat that as precedent, not something to repeat casually.

## Trading boundary

- The repository is **paper-only**. `broker.py` hard-wires `paper=True`;
  `execute.py` rejects any `execution.mode` other than `"paper"`.
- Do not remove `paper=True`, add a live endpoint, accept live credentials,
  or introduce a live-mode flag without a separately approved live-trading
  design (see Phases 1-5 in the audit remediation plan referenced above).
- Paper and any future live trading must use separate accounts,
  credentials, databases, deployments, configuration, ledgers, alerts, and
  kill switches — never share a ledger or account between them.
- Any live implementation must fail closed (missing config/credentials =
  refuse to run, not silently no-op) and require non-null risk limits
  (`max_open_positions`, `daily_deploy_cap_usd` are currently `null` by
  design for the paper trial — that's correct for paper, wrong for live).
- Never use git commits as the order, position, fill, or deduplication
  database for anything beyond the current paper-trading experiment.

## Broker and executor changes

Changes to `broker.py`, `execute.py`, `sell_check.py`, execution
configuration, or workflow files that touch trading should get:
1. A dry-run demonstration (`execute.py --dry-run --force`) before trusting
   the change against a real (even paper) account.
2. A check of what happens on a partial fill, a timeout, or a re-run after
   a crash mid-order — this repo has already hit a related bug once (the
   2026-07-15 fix for unhandled exceptions crashing execute.py mid-run).
3. A one-line security-impact note in the commit message if the change
   touches credentials, state files, or what gets committed to git.

## Workflow changes

- Default new GitHub Actions workflows to `contents: read` unless they
  genuinely need to commit state back.
- Use an explicit `STATE_FILES` allowlist for any state-commit step —
  never `git add -A`.
- Don't pass secrets to steps that don't need them.
- Don't let a workflow persist environment dumps, SDK traces, or any
  generated file that isn't already accounted for in that workflow's
  known write-list.

## Documentation

- Keep README/EXECUTION/OPTIONS_ENGINE claims consistent with actual
  code behavior — this repo has been burned by stale docs before (e.g.
  "recommend-only" language surviving a change to full auto-execution).
  When you change behavior, update the doc in the same commit.
- Never document the current value, expiration date, or storage location
  of a live credential — describing *how* to get one is fine (see README's
  secrets table), documenting the actual one in use is not.
- Label paper vs. real, and automated vs. manual, activity explicitly
  anywhere trades are described — don't let the two blur in prose even if
  they're technically separated in the data.
