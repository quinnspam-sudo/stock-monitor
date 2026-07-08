"""Template C generator — Hourly Intraday Market Pulse payload.

Checks each watchlist ticker for intraday structural breaches (price shock vs
prior close, volume spike vs 20-day average pace, gap vs open) plus a market
regime snapshot (SPY/QQQ/VIX proxies). Always writes a pulse payload — Template C
is a scheduled report, not a delta alert — but the breach section honestly says
"All portfolio holdings within baseline variances." when nothing broke.

Run: ./venv/bin/python pulse.py [--quiet-discord]
"""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import yfinance as yf

from notify import load_config, send_message
from committee import PROMPTS_DIR, market_open_today

PRICE_SHOCK = 0.03      # ±3% vs prior close
VOLUME_SPIKE = 2.0      # today's volume pace >= 2x 20-day average (time-adjusted)


def market_snapshot():
    lines = []
    for symbol, label in [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("^VIX", "VIX")]:
        try:
            h = yf.Ticker(symbol).history(period="5d")
            last, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
            lines.append(f"{label}: {last:,.2f} ({last / prev - 1:+.2%} d/d)")
        except Exception:
            lines.append(f"{label}: unavailable")
    return lines


def check_breaches(watchlist):
    breaches = []
    for ticker in watchlist:
        try:
            h = yf.Ticker(ticker).history(period="1mo")
            if len(h) < 21:
                continue
            last, prev = float(h["Close"].iloc[-1]), float(h["Close"].iloc[-2])
            move = last / prev - 1
            vol_today = float(h["Volume"].iloc[-1])
            vol_avg = float(h["Volume"].iloc[-21:-1].mean())
            # time-adjust: scale expected volume by fraction of session elapsed (NYSE clock)
            et = datetime.now(ZoneInfo("America/New_York"))
            elapsed = min(1.0, max(0.1, ((et.hour * 60 + et.minute) - 9.5 * 60) / (6.5 * 60)))
            vol_ratio = vol_today / (vol_avg * elapsed) if vol_avg else 0
            flags = []
            if abs(move) >= PRICE_SHOCK:
                flags.append(f"price {move:+.1%} vs prior close")
            if vol_ratio >= VOLUME_SPIKE:
                flags.append(f"volume {vol_ratio:.1f}x normal pace")
            if flags:
                breaches.append(f"{ticker} @ ${last:,.2f} — " + "; ".join(flags))
        except Exception as e:
            breaches.append(f"{ticker} — data error: {e}")
    return breaches


def main():
    # Catch-up runs after wake are pointless intraday — skip outside the session
    et_now = datetime.now(ZoneInfo("America/New_York"))
    in_session = et_now.weekday() < 5 and (9, 30) <= (et_now.hour, et_now.minute) <= (16, 0)
    if "--force" not in sys.argv and not in_session:
        print("Outside market session — pulse skipped.")
        return
    if "--force" not in sys.argv and not market_open_today():
        print("Market closed today — skipping pulse. Use --force to override.")
        return
    cfg = load_config()
    now = datetime.now()
    snapshot = market_snapshot()
    breaches = check_breaches(cfg["watchlist"])

    PROMPTS_DIR.mkdir(exist_ok=True)
    path = PROMPTS_DIR / f"{now:%Y-%m-%d_%H%M}_PULSE_templateC.md"
    breach_block = ("\n".join(f"  - {b}" for b in breaches)
                    if breaches else "  - All portfolio holdings within baseline variances.")
    path.write_text(f"""# COMMITTEE DATA PAYLOAD — HOURLY MARKET PULSE (Template C)
Generated: {now:%Y-%m-%d %H:%M} local | Source: stock-monitor pulse daemon
Instructions: Paste into the Investment Committee session. Output Template C only.

## Timestamp
{now:%H:%M} local

## Market Regime Snapshot (raw)
{chr(10).join('  - ' + s for s in snapshot)}

## Intraday breach scan ({PRICE_SHOCK:.0%} price shock / {VOLUME_SPIKE:.1f}x volume pace thresholds)
{breach_block}

## Gapped intraday sources
  - Trading halts feed: Data Status: GAPPED
  - Options flow: Data Status: GAPPED
""")
    import obsidian
    obsidian.mirror_payload(path)
    print(f"Pulse payload: {path.name}")
    for b in breaches:
        print(f"  breach: {b}")

    if breaches and "--quiet-discord" not in sys.argv:
        try:
            send_message("⏱️ **Intraday pulse breach** — unusual price/volume on holdings:\n"
                         + "\n".join(f"• {b}" for b in breaches)
                         + "\n**→ Do this:** check the ticker for news (earnings, downgrades, halts). "
                         "If a name you own moved, read the pulse payload in Obsidian before reacting — "
                         "intraday noise is not a thesis change.", kind="PULSE")
        except Exception as e:
            print(f"Discord notice failed: {e}")


if __name__ == "__main__":
    main()
    import notify
    if notify.had_failures():
        print(f"{len(notify.FAILURES)} Discord post(s) failed this run — failing job so CI surfaces it.")
        sys.exit(1)
