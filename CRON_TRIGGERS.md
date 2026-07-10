# Cowork task: verify + complete the cron-job.org triggers for stock-monitor

## Mission

The private GitHub repo `quinnspam-sudo/stock-monitor` runs its scheduled jobs as
GitHub Actions workflows, but GitHub's native `schedule:` trigger doesn't fire on
this account (anti-abuse throttle on new accounts). Scheduling is therefore done by
**cron-job.org** jobs that POST to each workflow's `workflow_dispatch` REST endpoint.

Your job: log the current state of every cron-job.org job, figure out which of the
target triggers below are missing, create ONLY the missing ones, test them, and
verify on the GitHub side that each test actually started a workflow run. Then report.

Deadline context: `weekly.yml` must fire **Friday 13:45 PT** (first-ever slot is the
next Friday after 2026-07-09) and `backtest.yml` **Saturday 09:00 PT** — if their
triggers are missing, those reviews silently never happen.

## Ground rules (read before touching anything)

1. **Never edit, disable, or delete an existing job.** Existing jobs are live
   production triggers. You are additive-only. Rollback = delete only jobs YOU created.
2. **The GitHub PAT never leaves cron-job.org.** New jobs need an
   `Authorization: Bearer <token>` header. Get the value by opening an EXISTING
   working job's settings (Advanced → headers) and copying it field-to-field into
   the new job. Do not write the token into your report, notes, or anywhere else.
3. **Stop and report instead of improvising** if: you can't log in, the console UI
   doesn't match these notes, an existing job already covers one of the targets but
   with a different schedule (report the difference, don't "fix" it), or a test
   returns 401/403 (PAT problem — retrying won't help).
4. Discord side effects of testing are expected and harmless (see Phase 4).

## Target state

One cron-job.org job per row (monitor has two rows — its window needs two cron
patterns). URL pattern for every job:

`https://api.github.com/repos/quinnspam-sudo/stock-monitor/actions/workflows/<FILE>/dispatches`

| Workflow file | Intended schedule (Pacific) | Cron (if job is set to timezone America/Los_Angeles) |
|---|---|---|
| monitor.yml (job 1) | every 15 min, 6:00–12:45 PT, Mon–Fri | `*/15 6-12 * * 1-5` |
| monitor.yml (job 2) | 13:00 PT, Mon–Fri | `0 13 * * 1-5` |
| pulse.yml | hourly 7:00–12:00 PT, Mon–Fri | `0 7-12 * * 1-5` |
| close.yml | 13:35 PT, Mon–Fri | `35 13 * * 1-5` |
| sell_check.yml | hourly 7:00–12:00 PT, Mon–Fri | `0 7-12 * * 1-5` |
| buy_intake.yml | every 15 min, all day, every day | `*/15 * * * *` |
| **options.yml** | daily 13:45 PT, Mon–Fri | `45 13 * * 1-5` |
| **weekly.yml** | Friday 13:45 PT | `45 13 * * 5` |
| **backtest.yml** | Saturday 09:00 PT | `0 9 * * 6` |

The bold three are the ones most likely missing (the first six are confirmed firing
as of 2026-07-09). But don't assume — Phase 1 establishes the truth. `options.yml`
ran once on 2026-07-09 at ~17:04 PT, which does NOT match its intended 13:45 slot,
so that run was probably a manual test, not proof of a trigger.

**Timezone caveat:** the original jobs may have been entered as UTC cron times
assuming PDT (UTC-7) — the repo's workflow comments say exact-PT alignment was
knowingly traded away. When you inspect an existing job, note which convention it
uses. For the NEW jobs, prefer setting the job's timezone to
**America/Los_Angeles** with the cron expressions above (exact PT year-round). If
the console only offers UTC, use the UTC equivalents (add 7 hours: options/weekly
`45 20 * * 1-5` / `45 20 * * 5`, backtest `0 16 * * 6`) and say so in your report.

## Phase 0 — Login

Go to `https://console.cron-job.org`. The account is Quinn's (email
[account-email-redacted]). If the browser isn't already logged in and you don't have
credentials available, STOP and ask — do not attempt password recovery.

## Phase 1 — Inventory

On the Cronjobs list page, for EVERY existing job record:
- Title
- Target URL — specifically which `<FILE>.yml` it dispatches
- Schedule (as displayed) and, if visible, the job's timezone setting
- Enabled/disabled status
- Latest execution status from the job's history (expect HTTP 204 on success)

Open at least one known-good job (e.g. the close.yml one) fully and record its
configuration shape: request method, headers present (names only — do not transcribe
the Authorization value), request body, notification settings. New jobs must match
this shape.

## Phase 2 — Gap analysis

Compare inventory against the target table. Classify each target row:
**present-and-matching / present-but-different (report, don't touch) / missing.**

## Phase 3 — Create each missing job

For each missing row, create a new cronjob:

- **Title:** follow the existing naming convention from Phase 1 (e.g. if existing
  jobs are titled `stock-monitor close`, use `stock-monitor options`).
- **URL:** the dispatch URL from the pattern above with the right filename.
- **Schedule:** custom cron expression + timezone per the target table.
- **Request method:** POST.
- **Headers** (copied field-for-field from the known-good job, plus these names):
  - `Authorization` — copy the exact value from the existing job
  - `Accept: application/vnd.github+json`
  - `Content-Type: application/json` (include if the existing job has it)
- **Request body:** `{"ref":"main"}`
- **Notifications:** mirror the existing jobs' failure-notification setting.
- Save.

## Phase 4 — Test and verify (both sides)

For each job you created:

1. Use the console's test/execute-now function. **Success = HTTP 204 (No Content).**
   - 401/403 → the Authorization header wasn't copied correctly, or PAT issue. Fix
     the copy once; if it persists, STOP and report.
   - 404 → wrong URL (check the filename spelling).
   - 422 → request body missing/malformed (`{"ref":"main"}`).
2. Then open `https://github.com/quinnspam-sudo/stock-monitor/actions` and confirm a
   run of that workflow appeared within ~1 minute of your test. The 204 alone is not
   full proof — the run appearing is.
3. Expected side effects (all harmless, mention them in the report, don't react):
   - **weekly.yml** tested on a non-Friday: the run starts, then weekly.py prints
     "Not Friday — skipping" and exits green. That still proves the trigger.
   - **backtest.yml** tested midweek: may post a partial-week line to Discord.
   - **options.yml**: runs a real ~8-minute scan and posts one OPTIONS_SCAN digest
     line to the #updates Discord channel. Expected.
4. Confirm the new job is **enabled** after testing.

## Phase 5 — Report

Deliver a table: every target row → existed already? / created by you? / test HTTP
status / GitHub run confirmed (run id or timestamp) / schedule+timezone as saved.
Plus: any present-but-different jobs found in Phase 2, any UI mismatches with these
instructions, and confirmation that no existing job was modified.

## Maintenance note (for the human, not for this task)

The PAT behind all these jobs is a fine-grained token scoped to this repo's Actions
permission only, **expiring ~2026-08-07**. When it's rotated, every job's
Authorization header must be updated or all triggers start returning 401.
