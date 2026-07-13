# Task: set up three scheduled triggers on cron-job.org (assume no prior context)

> **STATUS 2026-07-09 (task complete — kept as the PAT-rotation runbook):** all 9
> jobs verified. Every job now runs in timezone America/Los_Angeles (was UTC —
> would have made close/weekly fire before the closing bell after the November
> DST change), the options job was moved to 12:45 PT and enabled, and the jobs
> formerly named for UTC times are now `close-1335pt` / `monitor-1300pt`. The
> PAT behind every job expires ~2026-08-07; when rotated, update the
> Authorization header on ALL 9 jobs (see Step 3 for where it lives).

## What this is about, in plain English

Quinn runs an automated stock-monitoring system. The programs live in a private
GitHub repository called `quinnspam-sudo/stock-monitor` and run in the cloud using
a GitHub feature called **Actions workflows** — think of each workflow as a program
that runs when poked.

GitHub's own scheduler doesn't work on this account, so the poking is done by a
separate free website: **cron-job.org**. Each "cronjob" on that site is a tiny
scheduled task that, at set times, sends one HTTPS request to a special GitHub URL.
That request is the poke: GitHub receives it and starts the matching workflow.

Six workflows already have their cronjobs set up and working. Up to **three are
missing**: `options.yml`, `weekly.yml`, and `backtest.yml`. Your job is to check
what exists, create only what's missing, test it, and report back. Everything
happens in a web browser on `https://console.cron-job.org`. You never need to touch
the code.

## Vocabulary you'll need

- **Cronjob** — one scheduled task on cron-job.org: a URL + a schedule + request settings.
- **Cron expression** — a 5-part text code for a schedule, e.g. `45 13 * * 5` means
  "at 13:45 on day-of-week 5 (Friday)". You will copy-paste these exactly; you don't
  need to understand them beyond that.
- **Request method / POST** — the type of HTTPS request. These must be POST (a
  "send data" request), not the default GET.
- **Header** — a named label attached to a request. The important one here is
  `Authorization`, whose value is a secret token proving the request comes from
  Quinn. **This token is a password. Never write it into your notes, your report,
  or anywhere outside cron-job.org's own form fields.**
- **Request body** — the data sent with a POST. Here it is always the exact text
  `{"ref":"main"}` (which tells GitHub "run the version on the main branch").
- **HTTP 204** — the success response for this kind of poke. It literally means
  "worked, nothing more to say". 401/403/404/422 are failures (see Troubleshooting).

## Hard rules

1. **Never edit, disable, or delete any cronjob that already exists.** They are
   live production. You only ADD. If you must undo something, delete only a job you
   yourself created in this session.
2. **The secret token stays inside cron-job.org.** You'll copy it from an existing
   job's form field into a new job's form field. Never transcribe it anywhere else.
3. **When reality doesn't match these instructions** — a button isn't where
   described, a job already exists but with a different schedule, a test keeps
   failing — STOP that step, note exactly what you saw, and move on or report.
   Do not improvise fixes to existing things.
4. Before creating any job, re-check the job list so you never create a duplicate.

## Step 0 — Log in

Open `https://console.cron-job.org`. It should already be logged in to Quinn's
account ([account-email-redacted]). If it shows a login page and you don't have the
password available, STOP and ask Quinn — do not try password recovery.

## Step 1 — Write down what already exists

You should land on a dashboard listing existing cronjobs (a menu item like
"Cronjobs" shows the list). For EVERY job in the list, record:

- Its **title**
- Its **URL** — every URL here ends in `.../actions/workflows/SOMETHING.yml/dispatches`.
  The `SOMETHING.yml` part tells you which workflow it pokes. Record that filename.
- Its **schedule** as displayed, and its **timezone** if shown
- Whether it is **enabled**
- Its most recent execution result: open the job and find its history tab/section —
  the last executions should show status **204**. Record the latest status code.

Expected (but verify, don't assume): six workflows covered by seven jobs —
`monitor.yml` (twice — it needs two schedule patterns), `pulse.yml`, `close.yml`,
`sell_check.yml`, `buy_intake.yml` — all enabled, all recently returning 204.

Then open ONE known-good job fully (the `close.yml` one is a good pick) and study
its settings screens. Note (names only, never the secret value):
- where the request method is set (should say POST),
- which headers it has (expect at least `Authorization`, possibly
  `Accept` and `Content-Type`),
- what its request body says (expect `{"ref":"main"}`),
- whether failure notifications are switched on,
- which title style it uses (so your new jobs match).

This job is your **template** — every job you create must have the same shape.

## Step 2 — Decide what's missing

Compare the list you built against these three targets:

| Target workflow | Purpose (context only) | Wanted schedule |
|---|---|---|
| `options.yml`  | daily options-market scan | 13:45 Pacific, Monday–Friday |
| `weekly.yml`   | Friday performance review | 13:45 Pacific, Fridays |
| `backtest.yml` | Saturday scoring backtest | 09:00 Pacific, Saturdays |
| `discover.yml` | weekly watchlist discovery | 09:00 Pacific, Saturdays |

For each: **exists with this schedule** (do nothing) / **exists with a different
schedule** (do NOT change it — just note the difference for the report) /
**missing** (create it in Step 3).

Note: a workflow named `options` was manually poked once on 2026-07-09 — a run
existing on GitHub does NOT prove a cronjob exists. Only the cron-job.org list
counts as proof.

## Step 3 — Create the missing jobs (one recipe card each)

Click the create button (labeled something like **CREATE CRONJOB**). Fill in the
fields exactly as below. The form usually has a basic/"Common" section and an
"Advanced" section — the method, headers, and body live under Advanced.

**Getting the Authorization value:** open the template job (from Step 1) in another
tab, go to its headers, and copy the full value of its `Authorization` header (it
looks like `Bearer github_pat_…` — copy the WHOLE thing including the word
`Bearer`). Paste it into the new job's `Authorization` header value. Copy
field-to-field only.

**Timezone:** the schedule section should offer a timezone setting — set it to
**America/Los_Angeles**. If (and only if) there is genuinely no timezone option and
schedules are UTC, use the UTC alternative given on each card and say so in your
report.

---

### Card 1 — options

- Title: `stock-monitor options` (adjust to match the existing naming style)
- URL: `https://api.github.com/repos/quinnspam-sudo/stock-monitor/actions/workflows/options.yml/dispatches`
- Schedule: custom cron expression `45 13 * * 1-5`, timezone America/Los_Angeles
  ( = 13:45 Mon–Fri Pacific; UTC fallback: `45 20 * * 1-5`)
- Request method: `POST`
- Headers:
  - `Authorization` → pasted from template job
  - `Accept` → `application/vnd.github+json`
  - `Content-Type` → `application/json` (include if the template job has it)
- Request body: `{"ref":"main"}`
- Failure notification: same setting as the template job
- Enabled: yes → Save

### Card 2 — weekly

Identical to Card 1 except:
- Title: `stock-monitor weekly`
- URL: `.../actions/workflows/weekly.yml/dispatches` (same prefix as Card 1)
- Schedule: `45 13 * * 5`, timezone America/Los_Angeles
  ( = Fridays 13:45 Pacific; UTC fallback: `45 20 * * 5`)

### Card 3 — backtest

Identical to Card 1 except:
- Title: `stock-monitor backtest`
- URL: `.../actions/workflows/backtest.yml/dispatches`
- Schedule: `0 9 * * 6`, timezone America/Los_Angeles
  ( = Saturdays 09:00 Pacific; UTC fallback: `0 16 * * 6`)

### Card 4 — discover

Identical to Card 1 except:
- Title: `stock-monitor discover`
- URL: `.../actions/workflows/discover.yml/dispatches`
- Schedule: `30 9 * * 6`, timezone America/Los_Angeles
  ( = Saturdays 09:30 Pacific — 30 min after `backtest`, so the two weekend
    yfinance-heavy runs don't overlap; UTC fallback: `30 16 * * 6`)

### Card 5 — execute (paper-trading executor)

Identical to Card 1 except:
- Title: `stock-monitor execute`
- URL: `.../actions/workflows/execute.yml/dispatches`
- Schedule: `5,20,35,50 6-12 * * 1-5`, timezone America/Los_Angeles
  ( = every 15 min, 5 min after each `monitor` run, ~06:05–12:50 Pacific
    Mon–Fri so buy_alert signals are already written; UTC fallback:
    `5,20,35,50 13-19 * * 1-5`)
- **Prerequisite:** repo secrets `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` (paper
  keys) must exist, or every run no-ops. See EXECUTION.md.
- **Trial:** ends 2026-08-13 — `execute.py` stops opening positions after that
  date; **disable this card on 2026-08-13** to stop it entirely.

---

## Step 4 — Test each job you created

For each new job, use the console's immediate-test function (a button like
**TEST RUN** on the job's page, or an execute-now option in the list).

**Success = status 204.** Anything else → Troubleshooting below.

Then verify the poke really started the program on GitHub's side: open
`https://github.com/quinnspam-sudo/stock-monitor/actions` — this requires being
logged in to Quinn's GitHub account (`quinnspam-sudo`), because the repository is
private. A new run of the matching workflow should appear within about a minute of
your test. **If you can't log in to GitHub, skip this sub-step, rely on the 204,
and flag in your report that GitHub-side verification is still pending.**

Normal, harmless side effects of testing (mention in report, do nothing about them):
- Testing **weekly** on a day that isn't Friday: the run starts, immediately prints
  "Not Friday — skipping", and ends green. The trigger is still proven.
- Testing **backtest** midweek: it may post one messy partial-week message to
  Quinn's Discord. Harmless.
- Testing **options**: it runs a real ~8-minute market scan and posts one summary
  line to Quinn's Discord #updates channel. Expected.

Finally, confirm each new job shows **enabled** in the list.

## Troubleshooting

| Symptom | Meaning | What to do |
|---|---|---|
| Test returns 401 or 403 | Authorization header wrong/missing | Re-copy the header from the template job once. If it fails again, STOP — the token itself may be the problem. Report it. |
| Test returns 404 | URL typo (usually the filename) | Check the URL against the card character-by-character. |
| Test returns 422 | Body wrong | Body must be exactly `{"ref":"main"}` and Content-Type `application/json`. |
| UI doesn't match these notes | Site layout changed | Look for equivalent labels; if genuinely stuck, screenshot-describe what you see in the report. |
| A target job already exists | Nothing to create | Record its actual schedule; touch nothing. |

## Step 5 — Report back (fill this in)

```
CRON-JOB.ORG TRIGGER REPORT — <date/time>

Existing jobs found (title / workflow file / schedule / enabled / last status):
1. ...

Target check:
- options.yml : [already existed / created / created-with-UTC-fallback] — test status ___ — GitHub run seen? [yes/no/skipped]
- weekly.yml  : same fields
- backtest.yml: same fields

Discrepancies / anything odd: ...
Confirmation: no pre-existing job was modified, disabled, or deleted. [yes]
Side effects observed (Discord posts etc.): ...
```

## Note for Quinn (not part of the Cowork task)

The secret token behind every one of these jobs is a fine-grained GitHub PAT,
scoped to this repo's Actions permission only, **expiring ~2026-08-07**. When it is
rotated, the `Authorization` header of EVERY job must be updated or all triggers
start failing with 401. This document doubles as the runbook for that.
