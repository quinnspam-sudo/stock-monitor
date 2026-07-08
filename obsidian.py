"""Obsidian bridge — offloads all pings and payloads into the Jarbis vault.

Structure created under <vault>/Claude-Code/Stock Monitor/:
    Pings/YYYY-MM-DD.md        — every alert/notice, timestamped, one daily note
    Weeks/YYYY-Www.md          — rollup of that ISO week's day notes + weekly payloads
    Months/YYYY-MM.md          — rollup of that month's week notes
    Committee Payloads/*.md    — mirrored payload files (paste into Claude Pro from Obsidian)
    Tickers/TICKER.md          — per-ticker rollup: every payload + recorded verdict
    Stock Monitor Hub.md       — index note linking everything, incl. the current day/week/month

Every day note links up to its week note, every week note links up to its
month note, and the month note links up to the Hub — so the vault can be
browsed day-by-day, week-by-week, or month-by-month, not just by flat date list.

Vault root comes from secrets.json key "obsidian_vault" (gitignored — a local
absolute path has no business in a git history, even a private one), with a
legacy fallback to config.json for old setups. All writes are best-effort:
Obsidian being unavailable never breaks monitoring.
"""
import json
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")

CONFIG_PATH = Path(__file__).parent / "config.json"
SECRETS_PATH = Path(__file__).parent / "secrets.json"
RECOMMENDATIONS_PATH = Path(__file__).parent / "recommendations.json"
ACTUAL_TRADES_PATH = Path(__file__).parent / "actual_trades.json"
QUEUE_PATH = Path(__file__).parent / "obsidian_queue.jsonl"

# On GitHub Actions there is no local Jarbis vault to write into — queue the
# event instead so obsidian_sync.py can replay it into the real vault later.
IS_CI = bool(os.environ.get("GITHUB_ACTIONS"))


def _enqueue(event):
    with QUEUE_PATH.open("a") as f:
        f.write(json.dumps(event) + "\n")

# Standard (Template A) committee payload filenames look like
# 2026-07-06_1305_NVDA_standard.md — the only kind tied to one ticker.
TICKER_PAYLOAD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}_([A-Z]{1,6})_standard\.md$")
WEEK_FILE_RE = re.compile(r"^(\d{4})-W(\d{2})\.md$")


def _base():
    vault = os.environ.get("OBSIDIAN_VAULT")
    if not vault and SECRETS_PATH.exists():
        vault = json.loads(SECRETS_PATH.read_text()).get("obsidian_vault")
    if not vault:
        vault = json.loads(CONFIG_PATH.read_text()).get("obsidian_vault")  # legacy fallback
    if not vault:
        return None
    base = Path(vault) / "Claude-Code" / "Stock Monitor"
    (base / "Pings").mkdir(parents=True, exist_ok=True)
    (base / "Weeks").mkdir(parents=True, exist_ok=True)
    (base / "Months").mkdir(parents=True, exist_ok=True)
    (base / "Committee Payloads").mkdir(parents=True, exist_ok=True)
    (base / "Tickers").mkdir(parents=True, exist_ok=True)
    return base


def _load_verdicts():
    """Committee-verdict-kind recommendations only — see _load_recommendations
    for the full ledger (also holds buy_alert/sell_signal entries)."""
    recs = json.loads(RECOMMENDATIONS_PATH.read_text()) if RECOMMENDATIONS_PATH.exists() else []
    return [r for r in recs if r.get("kind", "committee_verdict") == "committee_verdict"]


def _load_recommendations():
    return json.loads(RECOMMENDATIONS_PATH.read_text()) if RECOMMENDATIONS_PATH.exists() else []


def _load_actual_trades():
    return json.loads(ACTUAL_TRADES_PATH.read_text()) if ACTUAL_TRADES_PATH.exists() else []


def _ticker_from_filename(name):
    m = TICKER_PAYLOAD_RE.match(name)
    return m.group(1) if m else None


def _week_id(d):
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _month_id(d):
    return d.strftime("%Y-%m")


def log_ping(kind, text, when=None):
    """Append a timestamped ping to today's daily note. kind: BUY / PAYLOAD / PULSE / CLOSE / INFO.

    `when` (a Pacific-time datetime) lets replayed CI events file under the
    day/week/month they actually happened on, not the day they were synced.
    """
    when = when or datetime.now(PACIFIC)
    if IS_CI:
        _enqueue({"type": "ping", "kind": kind, "text": text,
                  "ts": when.strftime("%Y-%m-%d %H:%M")})
        return
    try:
        base = _base()
        if base is None:
            return
        d = when.date()
        day = d.strftime("%Y-%m-%d")
        note = base / "Pings" / f"{day}.md"
        if not note.exists():
            week_id, month_id = _week_id(d), _month_id(d)
            note.write_text(f"""---
title: "Stock Monitor Pings — {day}"
date: {day}
type: code
folder: "Claude-Code"
tags: [ai-archive, stock-monitor, pings]
---

# [[Stock Monitor Pings — {day}]]

Part of [[Weeks/{week_id}|Week {d.isocalendar()[1]}, {d.year}]] ·
[[Months/{month_id}|{d.strftime('%B %Y')}]] · [[Stock Monitor Hub]].

## Pings

""")
        with note.open("a") as f:
            f.write(f"- **{when:%H:%M}** `{kind}` — {text}\n")
        _sync_hierarchy(d)
    except Exception:
        pass  # never let vault issues break monitoring


def _sync_hierarchy(day_date):
    """Refresh the week note, month note, and hub for this date so the
    day -> week -> month -> hub link chain stays current."""
    update_week_page(day_date)
    update_month_page(day_date)
    write_hub(day_date)


def update_week_page(day_date):
    """(Re)write the ISO-week rollup: every day note that week + any weekly
    review/backtest payloads dated within it."""
    try:
        base = _base()
        if base is None:
            return
        monday = day_date - timedelta(days=day_date.weekday())
        week_id, month_id = _week_id(day_date), _month_id(monday)
        week_dates = [monday + timedelta(days=i) for i in range(7)]

        day_links = [f"  - [[Pings/{dt:%Y-%m-%d}|{dt:%A} {dt:%Y-%m-%d}]]"
                     for dt in week_dates if (base / "Pings" / f"{dt:%Y-%m-%d}.md").exists()]
        day_block = "\n".join(day_links) or "  - (no days logged yet)"

        payloads_dir = base / "Committee Payloads"
        review_links = [f"  - [[{p.stem}]]" for dt in week_dates
                        for suffix in ("WEEKLY_review", "WEEKLY_BACKTEST")
                        for p in [payloads_dir / f"{dt:%Y-%m-%d}_{suffix}.md"] if p.exists()]
        review_block = "\n".join(review_links) or "  - none yet"

        (base / "Weeks" / f"{week_id}.md").write_text(f"""---
title: "Week {monday.isocalendar()[1]}, {monday.year} — Stock Monitor"
date: {monday:%Y-%m-%d}
type: code
folder: "Claude-Code"
tags: [ai-archive, stock-monitor, week]
---

# [[{week_id}]]

Part of [[Months/{month_id}|{monday.strftime('%B %Y')}]] · [[Stock Monitor Hub]].

## Days
{day_block}

## Weekly review / backtest payloads
{review_block}
""")
    except Exception:
        pass


def update_month_page(day_date):
    """(Re)write the month rollup: every ISO-week note whose Monday (or that
    week's Sunday) falls within this month."""
    try:
        base = _base()
        if base is None:
            return
        month_id = _month_id(day_date)
        matches = []
        for p in (base / "Weeks").glob("*.md"):
            m = WEEK_FILE_RE.match(p.name)
            if not m:
                continue
            y, w = int(m.group(1)), int(m.group(2))
            monday = datetime.strptime(f"{y}-W{w:02d}-1", "%G-W%V-%u").date()
            if monday.strftime("%Y-%m") == month_id or (monday + timedelta(days=6)).strftime("%Y-%m") == month_id:
                matches.append((monday, p.stem))
        matches.sort()
        week_block = "\n".join(f"  - [[Weeks/{stem}|{stem}]]" for _, stem in matches) \
            or "  - (no weeks logged yet)"

        (base / "Months" / f"{month_id}.md").write_text(f"""---
title: "{day_date.strftime('%B %Y')} — Stock Monitor"
date: {day_date:%Y-%m}-01
type: code
folder: "Claude-Code"
tags: [ai-archive, stock-monitor, month]
---

# [[{month_id}]]

Part of [[Stock Monitor Hub]].

## Weeks
{week_block}
""")
    except Exception:
        pass


PAYLOAD_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_(\d{4}))?")


def _payload_when(filename):
    """Payload filenames are prefixed YYYY-MM-DD_HHMM_... — use that as the
    true event time instead of 'now', so catch-up replays after the Mac
    was off file under the day (and time) the analysis actually happened."""
    m = PAYLOAD_DATE_RE.match(filename)
    if m:
        try:
            date_part = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            hhmm = m.group(2) or "0000"
            return datetime.combine(date_part, datetime.strptime(hhmm, "%H%M").time(), tzinfo=PACIFIC)
        except ValueError:
            pass
    return datetime.now(PACIFIC)


def _payload_day(filename):
    return _payload_when(filename).date()


def mirror_payload(payload_path):
    """Copy a committee payload into the vault with frontmatter prepended."""
    if IS_CI:
        try:
            rel = str(Path(payload_path).resolve().relative_to(Path(__file__).parent.resolve()))
        except ValueError:
            rel = str(payload_path)
        _enqueue({"type": "mirror_payload", "path": rel})
        return
    try:
        base = _base()
        if base is None:
            return
        src = Path(payload_path)
        dest = base / "Committee Payloads" / src.name
        body = src.read_text()
        day = _payload_day(src.name).strftime("%Y-%m-%d")
        dest.write_text(f"""---
title: "{src.stem}"
date: {day}
type: code
folder: "Claude-Code"
tags: [ai-archive, stock-monitor, committee-payload]
status: awaiting-verdict
---

> [!tip] Paste everything below the divider into the Claude Pro committee session,
> then log the verdict: `./venv/bin/python verdict.py add TICKER RATING`

Logged same day in [[Pings/{day}|today's ping log]].

---

{body}""")
        log_ping("PAYLOAD", f"[[{src.stem}]] mirrored to vault", when=_payload_when(src.name))
        ticker = _ticker_from_filename(src.name)
        if ticker:
            update_ticker_page(ticker)
    except Exception:
        pass


def update_ticker_page(ticker):
    """(Re)write the per-ticker rollup — every committee payload + recorded verdict."""
    try:
        base = _base()
        if base is None:
            return
        payloads_dir = base / "Committee Payloads"
        payload_links = sorted((p.stem for p in payloads_dir.glob(f"*_{ticker}_standard.md")), reverse=True)
        verdicts = [v for v in _load_verdicts() if v["ticker"] == ticker]
        verdict_lines = "\n".join(
            f"  - {v['date']}: **{v['rating']}** @ ${v['price_at_verdict']:,.2f}"
            + (f" (entry ${v['suggested_entry']:,.2f})" if v.get("suggested_entry") else "")
            + (f" — {v['note']}" if v.get("note") else "")
            for v in verdicts
        ) or "  - No verdicts recorded yet."
        payload_lines = "\n".join(f"  - [[{s}]]" for s in payload_links) or "  - No committee payloads yet."
        (base / "Tickers" / f"{ticker}.md").write_text(f"""---
title: "{ticker} — Stock Monitor History"
date: {datetime.now():%Y-%m-%d}
type: code
folder: "Claude-Code"
tags: [ai-archive, stock-monitor, ticker, {ticker.lower()}]
---

# [[{ticker}]]

Rollup of every committee payload and recorded verdict for **{ticker}** in the
[[Stock Monitor Hub|stock-monitor]] pipeline.

## Verdict history
{verdict_lines}

## Committee payloads (newest first)
{payload_lines}
""")
    except Exception:
        pass


def record_verdict(ticker, rating, price, entry, note, date):
    """Backlink a recorded verdict into its Committee Payload note, then refresh the ticker rollup."""
    try:
        base = _base()
        if base is None:
            return
        payloads_dir = base / "Committee Payloads"
        candidates = sorted(payloads_dir.glob(f"*_{ticker}_standard.md"), reverse=True)
        for p in candidates:
            text = p.read_text()
            if "status: awaiting-verdict" in text:
                text = text.replace("status: awaiting-verdict", "status: verdict-recorded", 1)
                text += (f"\n---\n## Verdict recorded — {date}\n"
                         f"- **Rating:** {rating}\n"
                         f"- **Price at verdict:** ${price:,.2f}\n"
                         + (f"- **Suggested entry:** ${entry:,.2f}\n" if entry else "")
                         + (f"- **Note:** {note}\n" if note else "")
                         + f"- Full history: [[{ticker}]]\n")
                p.write_text(text)
                break
        update_ticker_page(ticker)
    except Exception:
        pass


def log_recommendation(kind, ticker, detail, price, date=None):
    """Append a 'what the system said to do' entry to the running
    Recommendations Log — committee verdicts (verdict.py), real BUY alerts
    (monitor.py), and sell signals (sell_check.py). Deliberately separate
    from log_actual_trade: this is what was RECOMMENDED, not what happened."""
    if IS_CI:
        _enqueue({"type": "recommendation", "kind": kind, "ticker": ticker,
                  "detail": detail, "price": price, "date": date or datetime.now(PACIFIC).strftime("%Y-%m-%d")})
        return
    try:
        base = _base()
        if base is None:
            return
        path = base / "Recommendations Log.md"
        d = date or datetime.now(PACIFIC).strftime("%Y-%m-%d")
        if not path.exists():
            path.write_text("""---
title: "Recommendations Log"
type: code
folder: "Claude-Code"
tags: [ai-archive, stock-monitor, recommendations]
---

# [[Recommendations Log]]

Every "the system said to do X" event — committee verdicts, real BUY alerts,
and sell signals. NOT what you actually did — see [[Actual Trades Log]] for
that. Compare the two with `performance.py`.

| Date | Ticker | Kind | Detail | Price |
|---|---|---|---|---|
""")
        with path.open("a") as f:
            f.write(f"| {d} | [[{ticker}]] | {kind} | {detail} | ${price:,.2f} |\n")
    except Exception:
        pass  # never let vault issues break monitoring


def log_actual_trade(action, ticker, amount, price, shares, date=None, note=""):
    """Append a 'what I actually did' entry to the running Actual Trades
    Log — real buys/sells logged via the Discord buy-log bot. Deliberately
    separate from log_recommendation: this is ground truth, not a suggestion."""
    if IS_CI:
        _enqueue({"type": "actual_trade", "action": action, "ticker": ticker, "amount": amount,
                  "price": price, "shares": shares, "note": note,
                  "date": date or datetime.now(PACIFIC).strftime("%Y-%m-%d")})
        return
    try:
        base = _base()
        if base is None:
            return
        path = base / "Actual Trades Log.md"
        d = date or datetime.now(PACIFIC).strftime("%Y-%m-%d")
        if not path.exists():
            path.write_text("""---
title: "Actual Trades Log"
type: code
folder: "Claude-Code"
tags: [ai-archive, stock-monitor, actual-trades]
---

# [[Actual Trades Log]]

Every real trade you've actually made, logged via the Discord buy-log bot
(`Bought`/`Sold $X of TICKER at $Y`). NOT recommendations — see
[[Recommendations Log]] for what the system suggested. Compare the two
with `performance.py`.

| Date | Ticker | Action | Amount | Price | Shares | Note |
|---|---|---|---|---|---|---|
""")
        with path.open("a") as f:
            f.write(f"| {d} | [[{ticker}]] | {action} | ${amount:,.2f} | ${price:,.2f} | {shares:.4f} | {note} |\n")
    except Exception:
        pass  # never let vault issues break monitoring


def write_hub(day_date=None):
    """(Re)write the hub/index note, including a jump-off point to the
    current day/week/month notes."""
    try:
        base = _base()
        if base is None:
            return
        d = day_date or datetime.now().date()
        week_id, month_id = _week_id(d), _month_id(d)
        (base / "Stock Monitor Hub.md").write_text(f"""---
title: "Stock Monitor Hub"
date: {datetime.now():%Y-%m-%d}
type: code
folder: "Claude-Code"
tags: [ai-archive, stock-monitor, hub]
---

# [[Stock Monitor Hub]]

Command center for the local stock-monitor daemon (`~/Claude/stock-monitor`).
Part of the broader [[Claude AI Master Index]].

## Current period
- Today: [[Pings/{d:%Y-%m-%d}|{d:%A} {d:%Y-%m-%d}]]
- This week: [[Weeks/{week_id}|Week {d.isocalendar()[1]}, {d.year}]]
- This month: [[Months/{month_id}|{d.strftime('%B %Y')}]]

## Related
- [[Claude AI Master Index]]
- Sibling folders: [[Claude-Chats]] · [[Claude-Cowork]]

## Session Notes
- **Pings** — daily alert logs land in `Pings/` (one note per trading day). Each
  day note links up to its `Weeks/` note, which links up to its `Months/` note,
  which links up to this Hub — browse day-by-day, week-by-week, or month-by-month.
- **Committee Payloads** — mirrored here from `committee_prompts/`; paste into
  Claude Pro, then record the verdict with `verdict.py add TICKER RATING`
- **Tickers** — one rollup note per ticker (`Tickers/TICKER.md`) linking every
  committee payload and recorded verdict for that name, so you can browse a
  ticker's full history instead of hunting through daily pings. Recording a
  verdict also backlinks it into the original payload note (status flips from
  `awaiting-verdict` to `verdict-recorded`).
- **Dashboard** — `~/Claude/stock-monitor/dashboard.html` (auto-refreshing scoreboard)
- **Schedule** — monitor every 15 min, pulse hourly, close 13:35 PT, weekly review Fri,
  weekly backtest Sat
- The system recommends only; it never executes trades.
""")
    except Exception:
        pass


if __name__ == "__main__":
    write_hub()
    log_ping("INFO", "Obsidian bridge initialized")
    print(f"Vault bridge ready: {_base()}")
