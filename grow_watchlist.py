"""Grow the watchlist toward 300 tickers, pruning the weakest as we go.

Cycle: add 10 theme-fitting candidates (scored with the same proxy model the
monitor uses), then remove the lowest-overall ticker in the combined list
(10% of the batch). Net +9/cycle. Note: literally removing 10% of the TOTAL
each cycle converges to 90 tickers forever, so the batch interpretation is
what makes the 300 target reachable.

Run:  ./venv/bin/python grow_watchlist.py
Resumable — config.json/scores.json are saved after every cycle; grow_log.json
records every add/prune with scores.
"""
import json
import time
from datetime import datetime
from pathlib import Path

import committee
import monitor

BASE = Path(__file__).parent
CONFIG = BASE / "config.json"
LOG = BASE / "grow_log.json"
TARGET = 300
BATCH = 10

# Candidate pool by category — same themes as the existing watchlist.
# Order within a category is rough conviction order; cycles interleave
# categories so no theme floods a single batch.
POOL = {
    "AI Infrastructure": [
        "CRWV", "NBIS", "EQIX", "DLR", "HPE", "CLS", "JBL", "FLEX", "PSTG",
        "NTAP", "WDC", "STX", "GDS", "APLD", "IREN", "WULF", "CORZ", "SANM",
        "PLXS", "BHE", "TTMI",
    ],
    "Semiconductors & EDA": [
        "LRCX", "QCOM", "ARM", "SNPS", "CDNS", "TXN", "ADI", "NXPI", "MPWR",
        "MCHP", "ON", "GFS", "INTC", "SWKS", "QRVO", "ALGM", "SITM", "POWI",
        "AMKR", "MTSI", "SMTC", "VICR",
    ],
    "Semiconductor Equipment": [
        "TOELY", "ASMIY", "BESIY", "ONTO", "CAMT", "NVMI", "MKSI", "ACLS",
        "FORM", "UCTT", "ICHR", "VECO", "AEHR", "DSCSY",
    ],
    "Networking & Optics": [
        "APH", "TEL", "COHR", "LITE", "CRDO", "FN", "GLW", "CSCO", "CIEN",
        "AAOI", "LFUS",
    ],
    "Software & AI Applications": [
        "NOW", "CRM", "SNOW", "DDOG", "MDB", "INTU", "ADBE", "TEM", "APP",
        "DUOL", "UBER", "SHOP", "MELI", "NFLX", "BKNG",
    ],
    "Power & Grid": [
        "PWR", "EME", "HUBB", "NVT", "FIX", "IESC", "MYRG", "AGX", "SMR",
        "OKLO", "BWXT", "LEU", "UEC", "NXE", "DNN", "GNRC", "BE", "FSLR",
        "NRG", "PEG", "SO", "DUK", "D", "XEL", "EXC",
    ],
    "Defense & Aerospace": [
        "GE", "HWM", "TDG", "HEI", "AXON", "LHX", "HII", "TXT", "CW", "TDY",
        "LDOS", "CACI", "SAIC", "MRCY", "DRS", "ESLT", "RNMBY", "ERJ", "ACHR",
        "JOBY",
    ],
    "Healthcare & Biotech": [
        "REGN", "VRTX", "ABBV", "AMGN", "GILD", "MRK", "BSX", "SYK", "MDT",
        "DXCM", "PODD", "TMO", "DHR", "ILMN", "NTRA", "EXAS", "GEHC", "HIMS",
        "CRSP", "ALNY", "ZTS", "IDXX", "WST", "RMD", "EW", "HOLX", "TMDX",
        "GKOS", "PEN", "A",
    ],
    "Automation & Robotics": [
        "EMR", "HON", "PH", "ITW", "DOV", "AME", "ROP", "IR", "CGNX", "ZBRA",
        "TRMB", "NDSN", "RRX", "GGG", "LECO", "KEYS", "NOVT", "XYL", "SIEGY",
        "YASKY", "OMRNY", "KIGRY",
    ],
    "Critical Minerals & Rare Earths": [
        "ALB", "SQM", "SCCO", "TECK", "VALE", "RIO", "BHP", "LYSDY", "ERO",
        "HBM", "MTRN", "ATI", "CRS", "AA",
    ],
    "Cybersecurity": [
        "CYBR", "OKTA", "S", "TENB", "QLYS", "VRNS", "GEN", "AKAM", "SAIL",
        "RBRK",
    ],
    "Space Economy": [
        "BKSY", "RDW", "GSAT", "SATS", "VSAT", "GILT",
    ],
    "Quality Compounders": [
        "MA", "MSCI", "SPGI", "MCO", "BLK", "AXP", "GS", "SCHW", "ICE", "CME",
        "NDAQ", "LIN", "TT", "SHW", "CTAS", "FAST", "WM", "RSG", "URI", "HD",
        "TJX", "ORLY", "AZO", "WMT", "PG", "BRK-B", "GOOG", "MS", "BX", "KKR",
        "APO", "ARES", "BR", "PAYX", "ADP", "VRSK", "FICO", "CPRT", "ODFL",
        "GWW", "WSO", "POOL", "ROL", "EFX", "TRU", "FI", "PGR", "CB", "AON",
        "MMC", "AJG", "ECL", "APD", "PNR", "AOS", "EXPD", "CHRW",
    ],
    "Software & Data (extended)": [
        "TEAM", "WDAY", "HUBS", "VEEV", "TYL", "PTC",
        "ANSS", "CFLT", "ESTC", "GTLB", "DT", "BRZE", "IOT", "GWRE", "MANH",
        "PCOR", "TOST", "SPOT", "RBLX", "TTD", "PINS", "DASH", "ABNB", "COIN",
        "HOOD", "SOFI", "NU", "PYPL", "ADSK", "TWLO", "DOCN",
    ],
}


def interleaved(pool, exclude):
    """Round-robin across categories so each batch mixes themes."""
    iters = {k: iter(v) for k, v in pool.items()}
    out = []
    while iters:
        for k in list(iters):
            for t in iters[k]:
                if t not in exclude:
                    out.append((t, k))
                    break
            else:
                del iters[k]
    return out


def score_candidate(ticker):
    """Same proxy model the monitor runs: timing/100 + overall/110."""
    timing = monitor.score_ticker(ticker)
    if timing is None:
        return None
    cur = committee.gather(ticker, timing["score"])
    return cur


def main():
    cfg = json.loads(CONFIG.read_text())
    ledger = committee.load_ledger()
    log = json.loads(LOG.read_text()) if LOG.exists() else {"cycles": []}
    done = {c["ticker"] for cyc in log["cycles"] for c in cyc["added"]}
    done |= {t for cyc in log["cycles"] for t in cyc.get("failed", [])}

    queue = interleaved(POOL, set(cfg["watchlist"]) | done)
    print(f"start: {len(cfg['watchlist'])} tickers, {len(queue)} candidates queued")

    while len(cfg["watchlist"]) < TARGET:
        added, failed = [], []
        while len(added) < BATCH and queue:
            t, cat = queue.pop(0)
            try:
                cur = score_candidate(t)
            except Exception as e:
                print(f"  {t}: error {e}")
                cur = None
            if cur is None:
                failed.append(t)
                continue
            entry = {"overall": cur["overall"], "timing": cur["timing"],
                     "confidence": cur["confidence"], "rating": cur["rating"],
                     "days_to_earnings": cur["days_to_earnings"],
                     "sector": cur["sector"],
                     "date": time.strftime("%Y-%m-%d %H:%M")}
            ledger[t] = entry
            cfg["watchlist"].append(t)
            cfg["categories"].setdefault(cat, []).append(t)
            added.append({"ticker": t, "category": cat,
                          "overall": cur["overall"], "rating": cur["rating"]})
            print(f"  + {t:<6} {cur['overall']}/110 {cur['rating']} ({cat})")
            time.sleep(1)  # be polite to yahoo
        if not added:
            print("candidate pool exhausted before target — add more names to POOL")
            break

        # prune the single lowest-overall ticker (10% of the batch) from the
        # combined list; unscored incumbents are exempt (no evidence yet)
        scored = [(t, ledger[t]["overall"]) for t in cfg["watchlist"]
                  if t in ledger and "overall" in ledger[t]]
        victim, vscore = min(scored, key=lambda kv: kv[1])
        cfg["watchlist"].remove(victim)
        for members in cfg["categories"].values():
            if victim in members:
                members.remove(victim)
        ledger.pop(victim, None)
        print(f"  - {victim} pruned ({vscore}/110) → {len(cfg['watchlist'])} tickers")

        log["cycles"].append({"when": datetime.now().isoformat(timespec='minutes'),
                              "added": added, "failed": failed,
                              "pruned": {"ticker": victim, "overall": vscore},
                              "size": len(cfg["watchlist"])})
        CONFIG.write_text(json.dumps(cfg, indent=2))
        committee.save_ledger(ledger)
        LOG.write_text(json.dumps(log, indent=2))

    print(f"done: {len(cfg['watchlist'])} tickers")


if __name__ == "__main__":
    main()
