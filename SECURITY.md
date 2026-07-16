# Security policy

This repository is **public** and runs unattended via GitHub Actions.
It currently trades **paper money only** — see the trading boundary in
[CLAUDE.md](CLAUDE.md).

## Scope

This is a personal automation project, not a maintained open-source
product. There's no bug bounty and no SLA on responses, but real
findings are taken seriously — particularly anything touching secret
handling or the paper/live trading boundary.

## Reporting a vulnerability

Please **do not open a public GitHub issue** for a security finding.
Instead, contact the repo owner directly (see the GitHub profile for
`quinnspam-sudo`) with:

- What you found and where (file/line if applicable).
- Why it matters (impact).
- Steps to reproduce, if any.

## What's already known and tracked

- The repo publishes paper-trading state (scores, signals, paper order
  ledgers) by design — see `CLAUDE.md` for what's intentionally public
  vs. what should never be committed.
- A live-trading remediation plan (private state storage, idempotent
  order submission, non-null risk limits, out-of-band kill switch) is
  scoped but not implemented, since the system doesn't trade live money.
  Do not treat the absence of these as an open vulnerability against the
  current paper-only system — they're prerequisites for a future live
  system, not fixes to a present one.

## Rotation runbooks

If a credential is ever suspected compromised:

- **Alpaca (paper) keys** — revoke in the Alpaca dashboard, generate a
  replacement, update the GitHub repo secret, confirm the old key fails.
- **Discord webhook/bot token** — regenerate under Discord's
  Integrations/Developer Portal, update the repo secret, review recent
  channel/bot activity for anything unauthorized.
- **GitHub PAT** (powers the cron-job.org triggers — see
  `CRON_TRIGGERS.md`) — revoke under GitHub Developer Settings, create a
  replacement scoped to this repo's Actions permission only, update the
  Authorization header on every cron-job.org job, confirm the old PAT
  returns 401.

Never include a live credential's actual value, current expiration
date, or storage location in this file or any tracked file — describing
*how* to rotate one is fine, documenting the current one in use is not.
