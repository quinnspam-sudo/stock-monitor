"""Sell/exit alert methodologies — checks REAL open positions (from
actual_trades.json, the Discord buy-log ledger) against three explicit,
mechanical sell rules (tuned by the 2026-07-13 exit-rule replay over 6m/1y/5y
windows — committee_prompts/2026-07-13_EXIT_RULES_BACKTEST.md):

  - Wide stop-loss: position down -15% from average cost — but ONLY while
    SPY is above its own 50-day SMA. A stock down 15% while the market is
    healthy is an idiosyncratic problem: cut it. A stock down 15% because
    the whole market is down usually recovers with it; selling then is
    sell-low/rebuy-high churn (market-conditioning the stops this way was
    the best exit tested in every window: +9.9pts vs SPY over 6m, +13.6
    over 1y, vs +3.5/+6.1 unconditioned).
  - Trailing stop: close 25% below the position's peak close since entry,
    same market-health condition. Lets winners run (all of the buy
    signal's alpha came from a few +150-250% trends) while forcing an
    exit when a big win rolls over in an otherwise-healthy tape. Replaces
    the Darvas 20-day-low breakdown and the +20% take-profit sell, both
    of which tested worse than holding SPY.
  - Disaster floor: -30% from average cost, UNconditional — the bound on
    "hold because everything is falling" in a deep bear market (a 2008
    scenario is outside the tested sample; this is the insurance).
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
STOP_LOSS_PCT = -0.15
TRAIL_STOP_PCT = -0.25
DISASTER_PCT = -0.30
REBALANCE_DAYS = 365
COOLDOWN_HOURS = 24


def load_state():
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def market_is_healthy():
    """SPY above its 50-day SMA. Stops only fire in a healthy tape (see
    module docstring); the -30% disaster floor ignores this. Fails SAFE:
    if SPY data can't be fetched, treat the market as healthy so the
    stops stay armed rather than silently suspended."""
    try:
        spy = yf.Ticker("SPY").history(period="4mo")["Close"]
        if len(spy) < 50:
            return True
        return float(spy.iloc[-1]) > float(spy.rolling(50).mean().iloc[-1])
    except Exception:
        return True


def peak_close_since(ticker, held_since):
    """Highest close since the position was opened (for the trailing stop).
    Returns None if history can't be fetched."""
    try:
        hist = yf.Ticker(ticker).history(start=held_since)
        if hist.empty:
            return None
        return float(hist["Close"].max())
    except Exception:
        return None


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

    market_healthy = market_is_healthy()
    print(f"Market health: SPY {'above' if market_healthy else 'BELOW'} its 50d SMA — "
          f"{'stops armed' if market_healthy else 'stops suspended, disaster floor only'}")

    for ticker, pos in positions.items():
        entry = pos["avg_cost"]
        if not entry:
            continue
        try:
            recent = yf.Ticker(ticker).history(period="5d")["Close"]
            price = float(recent.iloc[-1])
        except Exception as e:
            print(f"{ticker}: price fetch failed: {e}")
            continue
        # Data-sanity guard: everything rides on one free data source, and a
        # bad print would fire a false stop. If the last close is >25% below
        # the prior close, require the NEXT run to confirm it (sell checks are
        # hourly — a real crash re-fires within the hour; a data glitch won't).
        if len(recent) >= 2 and price < float(recent.iloc[-2]) * 0.75:
            key = f"{ticker}:SUSPECT"
            if now.timestamp() - state.get(key, 0) > 2 * 3600:
                state[key] = now.timestamp()
                print(f"{ticker}: price ${price:,.2f} is >25% below prior close "
                      f"(${float(recent.iloc[-2]):,.2f}) — suspect data point, "
                      "deferring stop evaluation to next run for confirmation")
                continue
            print(f"{ticker}: >25% gap CONFIRMED on consecutive runs — evaluating stops")
        checked += 1
        pct_move = price / entry - 1

        alerts = []
        if pct_move <= DISASTER_PCT:
            alerts.append(("DISASTER_STOP", f"down {pct_move:+.1%} from avg cost ${entry:,.2f} — "
                            "-30% unconditional floor: fires regardless of market health. "
                            "No thesis survives this; cut it."))
        elif not market_healthy:
            print(f"{ticker}: stops suspended — SPY below its 50d SMA "
                  f"(market-wide drawdown; only the -30% disaster floor is armed)")
        elif pct_move <= STOP_LOSS_PCT:
            alerts.append(("STOP_LOSS", f"down {pct_move:+.1%} from avg cost ${entry:,.2f} "
                            "while SPY is above its 50d SMA — the market is fine and this "
                            "stock isn't: idiosyncratic weakness, cut at -15%."))
        elif pos["held_since"]:
            peak = peak_close_since(ticker, pos["held_since"])
            if peak and entry:
                peak = max(peak, entry)
                off_peak = price / peak - 1
                if off_peak <= TRAIL_STOP_PCT:
                    alerts.append(("TRAIL_STOP", f"down {off_peak:+.1%} from its peak close "
                                    f"(${peak:,.2f}) since entry, in a healthy market — 25% "
                                    "trailing stop: the winner has rolled over."))

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
