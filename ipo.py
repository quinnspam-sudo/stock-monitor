"""EDGAR IPO scanner — Template B pipeline feeder.

Polls SEC EDGAR's daily form index (official, free, no key) for new IPO-relevant
filings: S-1 / S-1/A (registration) and 424B4 (final pricing prospectus).
New filings are deduped via ipo_seen.json and consolidated into one daily
Template B payload in committee_prompts/ with direct EDGAR links, then pinged
to Discord and mirrored to Obsidian.

Run: ./venv/bin/python ipo.py [--days 3] [--quiet-discord]
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

from notify import send_message
from committee import PROMPTS_DIR

SEEN_PATH = Path(__file__).parent / "ipo_seen.json"
LOCKUP_PATH = Path(__file__).parent / "ipo_lockups.json"
LOCKUP_DAYS = 180  # typical insider/VC lock-up (Field & Hanka 2001)
HEADERS = {"User-Agent": "stock-monitor personal research [account-email-redacted]"}
FORMS = {"S-1": "S-1 registration (new IPO intent)",
         "S-1/A": "S-1 amendment (terms/pricing update)",
         "424B4": "Final pricing prospectus (IPO imminent/priced)"}


def fetch_day(day):
    """Parse one day's EDGAR form index. Returns list of (form, company, cik, url)."""
    qtr = (day.month - 1) // 3 + 1
    url = f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{qtr}/form.{day:%Y%m%d}.idx"
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code in (403, 404):  # SEC returns 403 for nonexistent days (weekends/holidays)
        return []
    r.raise_for_status()
    out = []
    for line in r.text.splitlines():
        parts = line.split()
        if not parts or parts[0] not in FORMS:
            continue
        # fixed-width-ish: FORM  COMPANY...  CIK  DATE  PATH
        form = parts[0]
        path = parts[-1]
        cik = parts[-3]
        company = " ".join(parts[1:-3])
        out.append((form, company, cik, f"https://www.sec.gov/Archives/{path}"))
    return out


def main():
    days_back = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 3
    seen = set(json.loads(SEEN_PATH.read_text())) if SEEN_PATH.exists() else set()
    now = datetime.now()

    fresh = []
    for i in range(days_back):
        day = now - timedelta(days=i)
        try:
            for form, company, cik, url in fetch_day(day):
                key = f"{form}|{cik}|{url}"
                if key not in seen:
                    seen.add(key)
                    fresh.append((day.strftime("%Y-%m-%d"), form, company, cik, url))
        except Exception as e:
            print(f"{day:%Y-%m-%d}: index fetch failed: {e}")

    if not fresh:
        print("No new IPO-relevant filings.")
        SEEN_PATH.write_text(json.dumps(sorted(seen)))
        return

    pricings = [f for f in fresh if f[1] == "424B4"]
    registrations = [f for f in fresh if f[1] != "424B4"]

    # Triage: demote likely SPACs/blank-check shells so real operating companies stand out
    import re
    shell_rx = re.compile(r"acquisition\s+(corp|co|company|corporation)|blank\s*check|\bSPAC\b", re.I)
    shells = [f for f in registrations + pricings if shell_rx.search(f[2])]
    registrations = [f for f in registrations if not shell_rx.search(f[2])]
    pricings = [f for f in pricings if not shell_rx.search(f[2])]

    # Lock-up calendar: record each pricing's ~180-day expiry; surface upcoming ones
    lockups = json.loads(LOCKUP_PATH.read_text()) if LOCKUP_PATH.exists() else {}
    for d, form, co, cik, url in pricings:
        expiry = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=LOCKUP_DAYS)).strftime("%Y-%m-%d")
        lockups[cik] = {"company": co, "priced": d, "lockup_expiry": expiry}
    upcoming = sorted(
        (v for v in lockups.values()
         if 0 <= (datetime.strptime(v["lockup_expiry"], "%Y-%m-%d") - now).days <= 14),
        key=lambda v: v["lockup_expiry"])
    LOCKUP_PATH.write_text(json.dumps(lockups, indent=2))

    def block(items):
        return "\n".join(
            f"  - [{d}] {FORMS[form]}: **{co}** (CIK {cik})\n    {url}"
            for d, form, co, cik, url in items) or "  - none"

    PROMPTS_DIR.mkdir(exist_ok=True)
    path = PROMPTS_DIR / f"{now:%Y-%m-%d}_IPO_templateB.md"
    path.write_text(f"""# COMMITTEE DATA PAYLOAD — EDGAR IPO SCAN (Template B triage)
Generated: {now:%Y-%m-%d %H:%M} local | Source: SEC EDGAR daily form index
Instructions: Paste into the Investment Committee session. Triage the list below:
ignore shells/SPACs/micro-caps, and for any credible upcoming IPO produce a
Template B evaluation using the linked S-1. Financial details are inside the
filings (links provided) — treat unread filings as Data Status: GAPPED.

## IPO evaluation rulebook (empirical; committee must apply)
- Value on FORWARD/comparable multiples (EV/NTM revenue for unprofitable growth,
  peer P/E for profitable firms), never trailing earnings. SaaS: check Rule of 40.
- Do NOT recommend buying at the open: first-day pops (19.0% avg 1980-2025, Ritter)
  accrue to allocated institutions, not open-market buyers.
- Default stance: WAIT for 2-4 quarters of reported earnings AND the ~180-day
  lock-up expiration before applying normal screens. Lock-up expiry itself shows a
  -1.5% three-day abnormal return and +40% permanent volume (Field & Hanka 2001),
  worse for VC-backed names — treat it as an entry-window signal, not a risk only.
- Red flags for long-run underperformance: short operating history, price-to-sales
  > 40 at offer, low institutional ownership, high volatility (Ritter 1991).

## New final pricing prospectuses (424B4 — IPO imminent or priced)
{block(pricings)}

## New S-1 registrations & amendments
{block(registrations)}

## Lock-up expirations within 14 days (entry-window watch, Field & Hanka)
{chr(10).join(f"  - {v['company']} — priced {v['priced']}, est. lock-up expiry {v['lockup_expiry']}" for v in upcoming) or "  - none tracked in window"}

## Likely SPACs / blank-check shells (auto-demoted; ignore unless you disagree)
{block(shells) if shells else "  - none detected"}

## Gapped sources
  - Roadshow transcripts: Data Status: GAPPED
  - Underwriter allocations / grey-market indications: Data Status: GAPPED
  - Actual lock-up terms (assumed {LOCKUP_DAYS}d; verify in prospectus): Data Status: GAPPED
""")
    SEEN_PATH.write_text(json.dumps(sorted(seen)))

    import obsidian
    obsidian.mirror_payload(path)
    print(f"IPO payload: {path.name} — {len(pricings)} pricings, {len(registrations)} registrations")

    if "--quiet-discord" not in sys.argv:
        try:
            head = f"🛎️ **EDGAR IPO scan** — {len(pricings)} pricing(s), {len(registrations)} new/amended S-1(s). Payload `{path.name}` ready."
            if pricings:
                head += "\nPricings: " + ", ".join(co for _, _, co, _, _ in pricings[:10])
            if upcoming:
                head += "\nLock-up expiries ≤14d: " + ", ".join(v["company"] for v in upcoming[:5])
            head += ("\n**→ Do this:** never buy an IPO at the open. If a name interests you, paste the "
                     "payload into Claude Pro for Template B triage; the default verdict is WAIT for "
                     "2-4 quarters + lock-up expiry. Lock-up expiries are potential entry windows.")
            send_message(head, kind="IPO")
        except Exception as e:
            print(f"Discord notice failed: {e}")


if __name__ == "__main__":
    main()
    import notify
    if notify.had_failures():
        print(f"{len(notify.FAILURES)} Discord post(s) failed this run — failing job so CI surfaces it.")
        sys.exit(1)
