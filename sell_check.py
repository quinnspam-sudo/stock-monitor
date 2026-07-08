"""Sell/exit alert methodologies — checks REAL open positions (from
actual_trades.json, the Discord buy-log ledger) against three explicit,
mechanical sell rules that come paired with their buy-side methodologies
in the literature:

  - CANSLIM (O'Neil) stop-loss: cut every loss at -7% to -8% from entry,
    no exceptions — arguably O'Neil's most famous rule, more so than his
    buy criteria. Also flags +20-25% gains as a take-profit consideration
    ("sell into strength" for a normal, non-explosive mover).
  - Darvas box breakdown: price breaks below its trailing 20-day low on
    above-average volume — the sell-side mirror of the 52-week breakout
    buy signal in factors.py's breakout_score.
  - Magic Formula (Greenblatt) annual rebalance: a position held >=365
    days is due for mechanical rotation regardless of current conviction,
    per Greenblatt's tax-driven (short-term loss / long-term gain) annual
    hold discipline.

Deliberately NOT symmetric with every buy-side methodology: Buffett-style
quality gates have no formal price-based sell rule at all (a qualitative
"is the business permanently impaired" judgment isn't something this
script can check), and insider selling isn't used as a mirrored signal
since the literature treats it as far noisier than insider buying.

Checks actual_trades.json's open positions (average-cost-basis accounting
via performance.compute_open_positions) — NOT recommendations.json. A
stop-loss only makes sense against a real position with a real entry price;
checking it against a committee verdict or a BUY alert (a recommendation,
not a confirmed action) was the original design's conflation, fixed here.
Every firing is itself logged as a "sell_signal" recommendation, alongside
the Discord alert.

Run: ./venv/bin/python sell_check.py [--force] [--quiet-discord]
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yfinance as yf

from notify import send_sell_alert
from committee import market_open_today
from performance import compute_open_positions

STATE_PATH = Path(__file__).parent / "sell_alert_state.json"
STOP_LOSS_PCT = -0.07
TAKE_PROFIT_PCT = 0.20
REBALANCE_DAYS = 365
COOLDOWN_HOURS = 24


def load_state():
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def box_breakdown(ticker):
    """Darvas-style: did price break below its trailing 20-day low (prior
    to today) on above-average volume? Returns (broke, low_20d, vol_ratio)."""
    try:
        hist = yf.Ticker(ticker).history(period="3mo")
        if len(hist) < 25:
            return False, None, None
        close = hist["Close"]
        price = float(close.iloc[-1])
        low_20d = float(close.iloc[-21:-1].min())
        vol_ratio = (float(hist["Volume"].iloc[-5:].mean() / hist["Volume"].iloc[-60:].mean())
                     if len(hist) >= 60 else None)
        broke = price < low_20d and (vol_ratio is None or vol_ratio > 1.1)
        return broke, low_20d, vol_ratio
    except Exception:
        return False, None, None


def main():
    if "--force" not in sys.argv and not market_open_today():
        print("Market closed today — skipping sell check. Use --force to override.")
        return

    positions = compute_open_positions()
    state = load_state()
    now = datetime.now()
    cooldown = COOLDOWN_HOURS * 3600
    checked = 0

    if not positions:
        print("No open positions in actual_trades.json — nothing to check. "
              "Log a buy via the Discord buy-log bot to start tracking one.")
        return

    for ticker, pos in positions.items():
        entry = pos["avg_cost"]
        if not entry:
            continue
        try:
            price = float(yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1])
        except Exception as e:
            print(f"{ticker}: price fetch failed: {e}")
            continue
        checked += 1
        pct_move = price / entry - 1

        alerts = []
        if pct_move <= STOP_LOSS_PCT:
            alerts.append(("STOP_LOSS", f"down {pct_move:+.1%} from avg cost ${entry:,.2f} — "
                            "CANSLIM rule: cut every loss at -7% to -8%, no exceptions."))
        elif pct_move >= TAKE_PROFIT_PCT:
            alerts.append(("TAKE_PROFIT", f"up {pct_move:+.1%} from avg cost ${entry:,.2f} — "
                            "CANSLIM rule: take profits at +20-25% unless the stock shows "
                            "explosive characteristics justifying a longer hold."))

        broke, low_20d, vol_ratio = box_breakdown(ticker)
        if broke:
            alerts.append(("BOX_BREAKDOWN", f"broke below its trailing 20-day low (${low_20d:,.2f})"
                            + (f" on {vol_ratio:.2f}x average volume" if vol_ratio else "")
                            + " — Darvas box breakdown, the sell-side mirror of a breakout."))

        if pos["held_since"]:
            try:
                held_date = datetime.strptime(pos["held_since"], "%Y-%m-%d")
                days_held = (now - held_date).days
                if days_held >= REBALANCE_DAYS:
                    alerts.append(("REBALANCE_DUE", f"held {days_held} days (>= {REBALANCE_DAYS}) — "
                                    "Magic Formula rule: mechanical annual rebalance regardless of "
                                    "current conviction (Greenblatt's tax-driven hold discipline)."))
            except ValueError:
                pass

        for kind, reason in alerts:
            key = f"{ticker}:{kind}"
            if now.timestamp() - state.get(key, 0) < cooldown:
                print(f"{ticker}: {kind} suppressed — within cooldown")
                continue
            if "--quiet-discord" in sys.argv:
                print(f"{ticker}: would send {kind} — {reason}")
                continue
            try:
                send_sell_alert(ticker, kind, price, entry, pct_move, reason)
                state[key] = now.timestamp()
                print(f"{ticker}: → Discord SELL alert sent ({kind})")
                import obsidian
                obsidian.log_recommendation("sell_signal", ticker, f"{kind}: {reason}", price)
            except Exception as e:
                print(f"{ticker}: Discord sell alert failed (continuing): {e}")

    save_state(state)
    print(f"Checked {checked}/{len(positions)} open position(s).")


if __name__ == "__main__":
    main()
    import notify
    if notify.had_failures():
        print(f"{len(notify.FAILURES)} Discord post(s) failed this run — failing job so CI surfaces it.")
        sys.exit(1)
