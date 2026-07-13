"""Watchlist discovery engine — draws in new names on a rigorous-but-optimistic bar.

Discovery answers a DIFFERENT, deliberately more optimistic question than the
monitor does. The monitor asks "should we buy this *right now*?" — and gates on
live timing, market regime, and a consensus supermajority (consensus.py). This
engine asks "is this a name worth *watching*?" — a name can be a great watchlist
candidate while today's tape or entry timing would (correctly) block a BUY. So
discovery keeps the RIGOROUS quality floors (real fundamentals, no structural
veto, a genuine conviction tier) but drops the timing/regime gates that are the
monitor's job. That separation is the whole design: promising names get in; the
monitor still decides, unchanged, when — or whether — any of them ever alert.

FROZEN-RULES BOUNDARY (EVALUATION_PROTOCOL.md, frozen until 2026-10-13): this
engine only curates watchlist *membership*. It never reads, sets, or influences
entry/exit thresholds. Adding a name cannot change how or when the frozen
trading rules fire on it — it only makes the monitor start watching it.

What it does each run:
  1. SOURCE new candidates from free, dynamic feeds — Yahoo predefined screens
     (growth/undervalued/most-active) plus sector top-companies for
     under-represented themes — seeded by grow_watchlist.POOL as a curated
     fallback. Deduped against the watchlist, ETFs, prior adds/prunes, and
     recently-rejected names (a re-look cooldown, so we don't re-score the same
     rejects every week).
  2. SCORE each with the EXACT monitor pipeline (score_ticker → committee.gather
     → factors.compute → conviction → consensus.evaluate) — no parallel math.
  3. ADMIT on the rigorous-but-optimistic gate (qualifies()). Calibrated to a
     natural handful per run, NOT a quota (per Quinn's standing directive: a
     quality bar, no caps — a generous per-run safety ceiling only trips as a
     circuit breaker and is logged, never silent).
  4. DIVERSIFY: rank admitted names by quality + an under-representation bonus,
     so a tech-heavy book (flagged 100% correlated-tech) fills its thin themes
     first.
  5. PRUNE structurally-dead names (confirmation-gated) by reading
     watchlist_health.json — names that can never alert (no price / UNRATED
     fundamentals, e.g. BESIY/DSCSY) get removed once seen dead N runs running.

Everything is logged (discover_log.json), announced to the #updates Discord
channel (never the BUY channel — discovery is not a buy signal), and reversible
via `watchlist.py remove`. State (reject cooldowns, prune counters, source
cursor) lives in discover_state.json.

Run:
  ./venv/bin/python discover.py            # full run: source, add, prune, push, announce
  ./venv/bin/python discover.py --dry-run  # score + rank + print, mutate NOTHING (propose mode)
  ./venv/bin/python discover.py --no-prune # add only, skip the prune pass
  ./venv/bin/python discover.py --report   # print the last run's summary and exit
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

import yfinance as yf

import committee
import consensus
import factors
import monitor
import notify

BASE = Path(__file__).parent
CONFIG = BASE / "config.json"
LOG = BASE / "discover_log.json"
STATE = BASE / "discover_state.json"
HEALTH = BASE / "watchlist_health.json"

# Tunable defaults — overridden by the "discovery" block in config.json if
# present. These are NOT the frozen trading rules; discovery thresholds are new
# and may be calibrated freely (recalibrate deliberately if the add rate drifts,
# same discipline as consensus.SUPERMAJORITY).
DEFAULTS = {
    # Yahoo predefined screens — the "fairly optimistic" net (growth + value +
    # liquidity), all forward-leaning cross-sections.
    "screens": ["growth_technology_stocks", "undervalued_growth_stocks",
                "aggressive_small_caps", "undervalued_large_caps", "most_actives"],
    # Yahoo sector keys pulled for diversification — deliberately the non-tech
    # sectors a tech-heavy book is thin on. The gate still decides admission;
    # this only widens the net beyond the tech-tilted screens above.
    "diversify_sectors": ["healthcare", "financial-services", "consumer-defensive",
                          "energy", "utilities", "basic-materials", "real-estate",
                          "industrials", "consumer-cyclical", "communication-services"],
    "screen_count": 40,       # names pulled per predefined screen
    "sector_top_n": 15,       # top companies pulled per diversify sector
    "eval_budget": 120,       # max candidates SCORED per run (yfinance politeness / efficiency)
    "min_overall": 60,        # rigorous floor: proxy overall (/110) must clear the midpoint
    "min_confidence": 45,     # rigorous floor: enough real data present (monitor caps confidence at 70)
    "near_buy_margin": 12,    # optimistic: blended score within this of alert_threshold counts as "near-buyable"
    "growth_floor": 0.10,     # optimistic: MEDIUM-tier names need >=10% rev/eps growth to promise
    "hypergrowth": 0.20,      # optimistic: >=20% growth admits even a merely-solid overall
    "reject_cooldown_days": 30,   # don't re-score a rejected name for this long
    "prune_confirmations": 2,     # remove a dead name only after it's flagged dead this many runs running
    "per_run_add_cap": 25,        # circuit breaker (logged if hit), NOT a quota
    "sleep": 0.4,             # seconds between candidate fetches — be polite to Yahoo
}

# yfinance sector / industry text → the watchlist's existing thematic category.
# Keeps the config's categories meaningful so diversification is measurable and
# added names land in a real theme instead of a growing "Uncategorized" bucket.
SECTOR_TO_CATEGORY = {
    "Technology": "Software & AI Applications",
    "Communication Services": "Media & Telecom",
    "Healthcare": "Healthcare & Biotech",
    "Financial Services": "Financials & Alt Managers",
    "Industrials": "Heavy Industry & Machinery",
    "Energy": "Energy & LNG",
    "Utilities": "Power & Grid",
    "Basic Materials": "Critical Minerals & Rare Earths",
    "Consumer Cyclical": "Consumer & Travel",
    "Consumer Defensive": "Quality Compounders",
    "Real Estate": "Quality Compounders",
}
# Industry keyword → category, checked first (more specific than the broad
# sector map above). First substring match wins.
INDUSTRY_HINTS = [
    ("semiconductor equipment", "Semiconductor Equipment"),
    ("semiconductor", "Semiconductors & EDA"),
    ("aerospace", "Defense & Aerospace"),
    ("defense", "Defense & Aerospace"),
    ("security", "Cybersecurity"),
    ("bank", "Financials & Alt Managers"),
    ("capital markets", "Financials & Alt Managers"),
    ("insurance", "Financials & Alt Managers"),
    ("gold", "Gold & Precious Metals"),
    ("oil", "Energy & LNG"),
    ("gas", "Energy & LNG"),
    ("uranium", "Power & Grid"),
    ("solar", "Power & Grid"),
    ("utilit", "Power & Grid"),
    ("biotech", "Healthcare & Biotech"),
    ("drug", "Healthcare & Biotech"),
    ("medical", "Healthcare & Biotech"),
    ("software", "Software & AI Applications"),
    ("internet", "Software & AI Applications"),
    ("aut", "Automation & Robotics"),
    ("robot", "Automation & Robotics"),
]


# ── small IO helpers ─────────────────────────────────────────────────────────
def _load(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _cfg_discovery(cfg):
    d = dict(DEFAULTS)
    d.update(cfg.get("discovery", {}))
    return d


# ── sourcing ─────────────────────────────────────────────────────────────────
def _valid_symbol(sym):
    # equities only; skip class shares/warrants/foreign suffixes that clutter
    # screens and rarely resolve fundamentals cleanly
    return bool(sym) and sym.isupper() and "." not in sym and "-" not in sym \
        and 1 <= len(sym) <= 5


def source_candidates(dc, exclude):
    """Return {ticker: hint_category|None}, deduped against `exclude`.

    Order matters — the eval budget is spent top-down, so the most
    diversification-relevant feeds (sector top-companies) come before the broad
    curated seed pool."""
    cands = {}

    def add(sym, hint):
        if _valid_symbol(sym) and sym not in exclude and sym not in cands:
            cands[sym] = hint

    # 1. Yahoo predefined screens (dynamic — genuinely NEW names each week)
    for name in dc["screens"]:
        try:
            r = yf.screen(name, count=dc["screen_count"])
            for q in (r.get("quotes", []) if isinstance(r, dict) else []):
                if q.get("quoteType") == "EQUITY":
                    add(q.get("symbol"), None)
        except Exception as e:
            print(f"  screen {name}: {e}")

    # 2. Sector top-companies for under-represented themes (diversification)
    for sector in dc["diversify_sectors"]:
        try:
            df = yf.Sector(sector).top_companies
            if df is None:
                continue
            hint = SECTOR_TO_CATEGORY.get(_sector_title(sector))
            for sym in list(df.index)[:dc["sector_top_n"]]:
                add(str(sym), hint)
        except Exception as e:
            print(f"  sector {sector}: {e}")

    # 3. Curated seed fallback — reuse grow_watchlist.POOL (don't duplicate it)
    try:
        import grow_watchlist
        for cat, names in grow_watchlist.POOL.items():
            for sym in names:
                add(sym, cat)
    except Exception as e:
        print(f"  pool seed: {e}")

    return cands


def _sector_title(key):
    return key.replace("-", " ").title()


# ── categorisation & diversification ─────────────────────────────────────────
def current_exposure(cfg):
    return {cat: len(names) for cat, names in cfg.get("categories", {}).items()}


def category_for(cur, hint, cfg):
    """Assign an added name to an existing thematic category."""
    cats = cfg.get("categories", {})
    if hint and hint in cats:
        return hint
    industry = (cur.get("industry") or "").lower()
    for kw, cat in INDUSTRY_HINTS:
        if kw in industry:
            return cat
    sector = cur.get("sector") or ""
    return SECTOR_TO_CATEGORY.get(sector, "Uncategorized")


def diversification_bonus(cat, exposure):
    """+points for thin themes, - for over-represented ones. Ordering only —
    never gates admission (the quality bar does that)."""
    if not exposure:
        return 0
    sizes = sorted(exposure.values())
    size = exposure.get(cat, 0)
    q1, q3 = sizes[len(sizes) // 4], sizes[(len(sizes) * 3) // 4]
    if size <= q1:
        return 8
    if size <= median(sizes):
        return 4
    if size >= q3:
        return -4
    return 0


# ── scoring & the gate ───────────────────────────────────────────────────────
def evaluate_candidate(ticker):
    """Run the identical monitor evaluation pipeline. Returns None if the name
    has no usable price history (score_ticker's own None)."""
    result = monitor.score_ticker(ticker)
    if result is None:
        return None
    momentum = result["score"]
    cur = committee.gather(ticker, momentum)
    try:
        cur["factors"] = factors.compute(ticker)
    except Exception:
        cur["factors"] = {}
    conv = tier = None
    if cur.get("factors"):
        conv, tier = factors.conviction(cur["factors"])
    blend = round(momentum * 0.55 + conv * 0.45) if conv is not None else momentum
    fmap = dict(cur.get("factors") or {})
    if conv is not None:
        fmap["_conviction"] = (conv, tier)
    try:
        cons = consensus.evaluate(momentum, fmap, cur.get("earnings_gate"))
    except Exception:
        cons = None
    return {"ticker": ticker, "cur": cur, "price": result["price"],
            "momentum": momentum, "conv": conv,
            "tier": (tier.split()[0] if tier else "UNRATED"),
            "blend": blend, "consensus": cons}


def _growth(cur):
    f = cur.get("fields", {})
    vals = [f.get("revenueGrowth"), f.get("earningsGrowth")]
    vals = [v for v in vals if isinstance(v, (int, float))]
    return max(vals) if vals else None


def qualifies(ev, dc, alert_threshold):
    """The rigorous-but-optimistic gate. Returns (ok, promise_reason, why_not)."""
    cur = ev["cur"]
    overall = cur["overall"]
    confidence = cur["confidence"]

    # ── RIGOROUS floors (all must hold) ──
    if ev["tier"] == "UNRATED":
        return False, None, "UNRATED (no factor conviction — cannot ever alert)"
    if confidence < dc["min_confidence"]:
        return False, None, f"confidence {confidence} < {dc['min_confidence']} (too little real data)"
    if overall < dc["min_overall"]:
        return False, None, f"overall {overall} < {dc['min_overall']}"
    # structural vetoes only — the REGIME veto is the monitor's job to enforce
    # at buy time, not a reason to refuse to watch a name (that's the optimism)
    struct_vetoes = [v for v in (ev["consensus"] or {}).get("vetoes", [])
                     if not v.startswith("hostile market regime")]
    if struct_vetoes:
        return False, None, "veto: " + "; ".join(struct_vetoes)

    # ── OPTIMISTIC promise (any one admits) ──
    g = _growth(cur)
    if ev["tier"] == "HIGH":
        return True, "HIGH conviction tier", None
    if ev["tier"] == "MEDIUM" and g is not None and g >= dc["growth_floor"]:
        return True, f"MEDIUM tier + {g:+.0%} growth", None
    if ev["blend"] >= alert_threshold - dc["near_buy_margin"]:
        return True, f"near-buyable (blend {ev['blend']} vs {alert_threshold})", None
    if g is not None and g >= dc["hypergrowth"] and overall >= 65:
        return True, f"hyper-growth {g:+.0%} + overall {overall}", None
    return False, None, f"solid but no promise trigger (tier {ev['tier']}, blend {ev['blend']}, growth {g})"


# ── prune (confirmation-gated, reads watchlist_health.json) ──────────────────
def prune_pass(cfg, state, dc, dry_run):
    """Remove names that can never alert, confirmed across multiple runs.

    Reads the health report the weekly `watchlist_health.py --deep` already
    produces — no duplicate 420-name scan here. A name must be flagged dead
    `prune_confirmations` runs running before removal; anything that recovers
    resets its counter."""
    health = _load(HEALTH, {})
    dead_now = set(health.get("no_price") or []) | set(health.get("unrated_no_fundamentals") or [])
    counters = state.setdefault("unratable", {})
    on_list = set(cfg["watchlist"])

    pruned = []
    # bump / reset counters against the fresh report
    for t in list(counters):
        if t not in dead_now or t not in on_list:
            counters.pop(t, None)  # recovered or already gone
    for t in dead_now:
        if t in on_list:
            counters[t] = counters.get(t, 0) + 1

    ready = sorted(t for t, n in counters.items() if n >= dc["prune_confirmations"])
    for t in ready:
        if dry_run:
            pruned.append({"ticker": t, "confirmations": counters[t], "dry": True})
            continue
        cfg["watchlist"].remove(t)
        for names in cfg.get("categories", {}).values():
            if t in names:
                names.remove(t)
        cfg["categories"] = {k: v for k, v in cfg.get("categories", {}).items() if v}
        ledger = committee.load_ledger()
        if ledger.pop(t, None):
            committee.save_ledger(ledger)
        counters.pop(t, None)
        pruned.append({"ticker": t, "confirmations": dc["prune_confirmations"]})
        print(f"  - pruned {t} (dead {dc['prune_confirmations']} runs running)")
    return pruned


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    dry_run = "--dry-run" in sys.argv
    do_prune = "--no-prune" not in sys.argv
    if "--report" in sys.argv:
        log = _load(LOG, {"runs": []})
        print(json.dumps(log["runs"][-1] if log["runs"] else {}, indent=2))
        return

    cfg = json.loads(CONFIG.read_text())
    dc = _cfg_discovery(cfg)
    state = _load(STATE, {})
    log = _load(LOG, {"runs": []})
    alert_threshold = cfg.get("alert_threshold", 76)
    now = datetime.now()

    # exclusion set: on the book, ETFs, already tried, and rejects still cooling
    prior_added = {c["ticker"] for run in log["runs"] for c in run.get("added", [])}
    prior_pruned = {p["ticker"] for run in log["runs"] for p in run.get("pruned", [])}
    rejects = state.setdefault("rejected", {})
    cooling = {t for t, r in rejects.items()
               if r.get("until") and r["until"] > now.isoformat()}
    exclude = set(cfg["watchlist"]) | set(cfg.get("etf_watchlist", [])) \
        | prior_added | prior_pruned | cooling

    cands = source_candidates(dc, exclude)
    print(f"sourced {len(cands)} new candidates (excluded {len(exclude)}); "
          f"eval budget {dc['eval_budget']}")

    exposure = current_exposure(cfg)
    added, rejected, errors, budget_hit = [], [], [], False
    ledger = committee.load_ledger()

    for i, (ticker, hint) in enumerate(cands.items()):
        if i >= dc["eval_budget"]:
            budget_hit = True
            break
        try:
            ev = evaluate_candidate(ticker)
        except Exception as e:
            errors.append(ticker)
            print(f"  {ticker}: error {e}")
            time.sleep(dc["sleep"])
            continue
        if ev is None:
            rejects[ticker] = {"until": (now + timedelta(days=dc["reject_cooldown_days"])).isoformat(),
                               "reason": "no price history"}
            time.sleep(dc["sleep"])
            continue

        ok, promise, why_not = qualifies(ev, dc, alert_threshold)
        if not ok:
            rejects[ticker] = {"until": (now + timedelta(days=dc["reject_cooldown_days"])).isoformat(),
                               "reason": why_not}
            rejected.append({"ticker": ticker, "overall": ev["cur"]["overall"],
                             "tier": ev["tier"], "blend": ev["blend"], "why": why_not})
            time.sleep(dc["sleep"])
            continue

        cat = category_for(ev["cur"], hint, cfg)
        rank = ev["blend"] + diversification_bonus(cat, exposure)
        added.append({"ticker": ticker, "category": cat, "overall": ev["cur"]["overall"],
                      "rating": ev["cur"]["rating"], "tier": ev["tier"],
                      "blend": ev["blend"], "rank": rank, "promise": promise,
                      "price": round(ev["price"], 2), "_ev": ev})
        rejects.pop(ticker, None)
        time.sleep(dc["sleep"])

    # rank by quality + diversification, apply the (logged) circuit breaker
    added.sort(key=lambda a: -a["rank"])
    if len(added) > dc["per_run_add_cap"]:
        print(f"  ⚠ {len(added)} qualified — circuit breaker clips to "
              f"{dc['per_run_add_cap']} (calibrate the gate if this recurs)")
        added = added[:dc["per_run_add_cap"]]

    # commit adds to config + ledger (unless dry run)
    if not dry_run:
        for a in added:
            ev = a.pop("_ev")
            cfg["watchlist"].append(a["ticker"])
            cfg.setdefault("categories", {}).setdefault(a["category"], []).append(a["ticker"])
            ledger[a["ticker"]] = {
                "overall": ev["cur"]["overall"], "timing": ev["momentum"],
                "confidence": ev["cur"]["confidence"], "rating": ev["cur"]["rating"],
                "days_to_earnings": ev["cur"].get("days_to_earnings"),
                "sector": ev["cur"].get("sector"),
                "date": now.strftime("%Y-%m-%d %H:%M")}
            try:
                committee.append_history(a["ticker"], ev["cur"])
            except Exception:
                pass
            print(f"  + {a['ticker']:<6} {ev['cur']['overall']}/110 {ev['cur']['rating']} "
                  f"[{a['tier']}] {a['category']} — {a['promise']}")
        committee.save_ledger(ledger)
    else:
        for a in added:
            a.pop("_ev", None)
            print(f"  + {a['ticker']:<6} {a['overall']}/110 {a['rating']} [{a['tier']}] "
                  f"{a['category']} — {a['promise']}  (dry-run)")

    pruned = prune_pass(cfg, state, dc, dry_run) if do_prune else []

    # persist config + state + log
    if not dry_run:
        CONFIG.write_text(json.dumps(cfg, indent=2))
        state["last_run"] = now.isoformat(timespec="minutes")
        STATE.write_text(json.dumps(state, indent=2))
    run_rec = {"when": now.isoformat(timespec="minutes"), "dry_run": dry_run,
               "sourced": len(cands), "evaluated": min(len(cands), dc["eval_budget"]),
               "added": [{k: v for k, v in a.items() if k != "_ev"} for a in added],
               "pruned": pruned, "rejected_count": len(rejected),
               "near_misses": sorted(rejected, key=lambda r: -r["blend"])[:5],
               "errors": errors, "budget_hit": budget_hit,
               "watchlist_size": len(cfg["watchlist"])}
    if not dry_run:
        log["runs"].append(run_rec)
        LOG.write_text(json.dumps(log, indent=2))
        _announce(run_rec)
        _push(added, pruned)

    print(f"\n{'DRY RUN — ' if dry_run else ''}added {len(added)}, pruned {len(pruned)}, "
          f"rejected {len(rejected)}; watchlist now {len(cfg['watchlist'])}")


def report_lines(n_runs=4):
    """Compact summary for the weekly payload (consumed by weekly.py)."""
    log = _load(LOG, {"runs": []})
    runs = [r for r in log["runs"] if not r.get("dry_run")][-n_runs:]
    if not runs:
        return ["  - Discovery: no runs recorded yet."]
    lines = [f"  - Discovery (last {len(runs)} runs):"]
    for r in runs:
        adds = ", ".join(f"{a['ticker']}[{a.get('tier','?')}]" for a in r.get("added", [])) or "—"
        prunes = ", ".join(p["ticker"] for p in r.get("pruned", [])) or "—"
        lines.append(f"    - {r['when'][:10]}: +{len(r.get('added',[]))} ({adds}); "
                     f"pruned {prunes}; watchlist {r.get('watchlist_size','?')}")
    return lines


def _announce(run):
    added, pruned = run["added"], run["pruned"]
    if not added and not pruned and not run["near_misses"]:
        return  # nothing worth a message this run
    lines = [f"🔭 **WATCHLIST DISCOVERY** — sourced {run['sourced']}, "
             f"evaluated {run['evaluated']}, watchlist now {run['watchlist_size']}"]
    if added:
        lines.append(f"**Added {len(added)}** (rigorous-but-optimistic gate):")
        for a in added:
            lines.append(f"  • {a['ticker']} {a['overall']}/110 {a['rating']} "
                         f"[{a['tier']}] — {a['category']} — {a['promise']}")
    if pruned:
        lines.append(f"**Pruned {len(pruned)}** (dead, can never alert): "
                     + ", ".join(p["ticker"] for p in pruned))
    if run["near_misses"]:
        lines.append("Near-misses: " + ", ".join(
            f"{m['ticker']} ({m['tier']}, blend {m['blend']})" for m in run["near_misses"]))
    if run["budget_hit"]:
        lines.append("_(eval budget reached — more candidates queued for next run)_")
    lines.append("_Discovery adds to the watchlist only; the frozen trading "
                 "rules decide if/when any of these ever alert. Reverse with "
                 "`watchlist.py remove TICKER`._")
    notify.send_message("\n".join(lines), kind="DISCOVERY")


def _push(added, pruned):
    # In CI the workflow's own "Commit updated state" step pushes everything
    # with git add -A; self-pushing there just races it. Self-push only matters
    # for local/manual runs, same as watchlist.py.
    import os
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return
    if not (added or pruned):
        return
    try:
        import git_sync
        git_sync.commit_and_push(
            ["config.json", "scores.json", "discover_log.json",
             "discover_state.json", "history.json"],
            f"discover: +{len(added)} / -{len(pruned)} watchlist names")
    except Exception as e:
        print(f"  push skipped: {e}")


if __name__ == "__main__":
    main()
    if notify.had_failures():
        sys.exit(1)
