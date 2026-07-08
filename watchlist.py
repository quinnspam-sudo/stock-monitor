"""Watchlist management CLI.

    ./venv/bin/python watchlist.py list
    ./venv/bin/python watchlist.py add PLTR
    ./venv/bin/python watchlist.py remove TSLA
"""
import json
import sys

import yfinance as yf

from notify import CONFIG_PATH
from committee import load_ledger, save_ledger


def main():
    cfg = json.loads(CONFIG_PATH.read_text())
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        ledger = load_ledger()
        for t in cfg["watchlist"]:
            entry = ledger.get(t, {})
            score = f"{entry['overall']}/110 ({entry.get('rating', '?')})" if entry else "not yet scored"
            print(f"{t:<8}{score}")
        return

    ticker = sys.argv[2].upper()
    if cmd == "add":
        if ticker in cfg["watchlist"]:
            print(f"{ticker} already on watchlist.")
            return
        # validate the ticker resolves before committing it
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            print(f"{ticker} returned no data — not added.")
            return
        cfg["watchlist"].append(ticker)
        cfg.setdefault("categories", {}).setdefault("Uncategorized", []).append(ticker)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        print(f"Added {ticker} (last close ${float(hist['Close'].iloc[-1]):,.2f}) — "
              "filed under 'Uncategorized' in config.json's categories map (move it "
              "into a real theme by hand if you like). "
              "Next monitor run will generate its initial committee payload.")
    elif cmd == "remove":
        if ticker not in cfg["watchlist"]:
            print(f"{ticker} not on watchlist.")
            return
        cfg["watchlist"].remove(ticker)
        for names in cfg.get("categories", {}).values():
            if ticker in names:
                names.remove(ticker)
        cfg["categories"] = {k: v for k, v in cfg.get("categories", {}).items() if v}
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        ledger = load_ledger()
        if ledger.pop(ticker, None):
            save_ledger(ledger)
        print(f"Removed {ticker} from watchlist, categories, and ledger.")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
