"""Watchlist monitor — scores each ticker and sends Discord alerts above threshold.

Run once:            ./venv/bin/python monitor.py
Run without alerts:  ./venv/bin/python monitor.py --dry-run
"""
import json
import sys
import time
from pathlib import Path

import yfinance as yf

from notify import load_config, send_alert, send_message
import committee
import factors

STATE_PATH = Path(__file__).parent / "alert_state.json"


def rsi(closes, period=14):
    deltas = closes.diff().dropna()
    gains = deltas.clip(lower=0).rolling(period).mean()
    losses = (-deltas.clip(upper=0)).rolling(period).mean()
    rs = gains / losses.replace(0, 1e-9)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def score_ticker(ticker):
    """Simple momentum/trend score 0-100. Expand with fundamentals later."""
    hist = yf.Ticker(ticker).history(period="6mo")
    if len(hist) < 64:  # deepest lookback below is iloc[-63]
        return None
    close = hist["Close"]
    price = float(close.iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1])
    high3m = float(close.iloc[-63:].max())
    ret1m = price / float(close.iloc[-21]) - 1
    ret3m = price / float(close.iloc[-63]) - 1
    r = rsi(close)
    vol_ratio = float(hist["Volume"].iloc[-5:].mean() / hist["Volume"].iloc[-60:].mean())

    score = 0
    score += 20 if price > sma50 else 0
    score += 15 if sma20 > sma50 else 0
    score += min(20, max(0, ret3m * 100))          # up to 20 pts for 3-mo return
    score += min(15, max(0, ret1m * 150))          # up to 15 pts for 1-mo return
    score += 15 if price >= high3m * 0.97 else 0   # near 3-month high
    score += 10 if 45 <= r <= 70 else 0            # healthy RSI, not overbought
    score += 5 if vol_ratio > 1.1 else 0           # volume confirmation
    score = round(min(100, score))

    return {
        "ticker": ticker,
        "price": price,
        "score": score,
        "details": {
            "RSI(14)": f"{r:.0f}",
            "1-mo return": f"{ret1m:+.1%}",
            "3-mo return": f"{ret3m:+.1%}",
            "vs 50-day SMA": f"{price / sma50 - 1:+.1%}",
            "Near 3-mo high": "yes" if price >= high3m * 0.97 else "no",
            "Volume trend": f"{vol_ratio:.2f}x",
        },
    }


def load_state():
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def main():
    dry_run = "--dry-run" in sys.argv
    if not dry_run and "--force" not in sys.argv and not committee.market_open_today():
        print("Market closed today (holiday/weekend) — skipping run. Use --force to override.")
        return

    # Log rotation: keep monitor.log under ~1 MB
    log = Path(__file__).parent / "monitor.log"
    if log.exists() and log.stat().st_size > 1_000_000:
        log.write_text("\n".join(log.read_text().splitlines()[-500:]) + "\n")

    cfg = load_config()
    state = load_state()
    ledger = committee.load_ledger()
    now = time.time()
    cooldown = cfg.get("cooldown_hours", 24) * 3600
    payloads = []
    evaluations = {}  # ticker -> (cur, prev); triggers checked after the loop so rank shifts are visible
    buy_queue = []    # BUY alerts deferred until factor ranks exist

    print(f"{'TICKER':<8}{'PRICE':>10}{'SCORE':>7}  ACTION")
    for ticker in cfg["watchlist"]:
        try:
            result = score_ticker(ticker)
        except Exception as e:
            print(f"{ticker:<8}  error: {e}")
            continue
        if result is None:
            print(f"{ticker:<8}  insufficient data")
            continue
        score = result["score"]
        action = "BUY" if score >= cfg["alert_threshold"] else "WATCH" if score >= 60 else "HOLD"
        print(f"{ticker:<8}{result['price']:>10,.2f}{score:>7}  {action}")

        # Committee noise gate: compute proxy scores, diff vs ledger, emit payload on breach
        try:
            cur = committee.gather(ticker, score)
            try:
                cur["factors"] = factors.compute(ticker)
            except Exception as e:
                print(f"         factors error: {e}")
            evaluations[ticker] = (cur, ledger.get(ticker))
            if not dry_run:  # dry runs must not consume triggers or pollute history
                committee.append_history(ticker, cur)
        except Exception as e:
            print(f"         committee error: {e}")

        if action == "BUY" and not dry_run:
            if now - state.get(ticker, 0) < cooldown:
                print(f"         (alert suppressed — within cooldown)")
            else:
                buy_queue.append((ticker, score, result))

    # Cross-sectional Magic Formula ranks over the whole watchlist
    factors.rank_universe({t: cur["factors"] for t, (cur, _) in evaluations.items()
                           if "factors" in cur})

    # BUY alerts fire post-ranking so each carries a factor-conviction verdict
    for ticker, score, result in buy_queue:
        f = evaluations.get(ticker, ({}, None))[0].get("factors", {})
        conv, tier = factors.conviction(f) if f else (None, "UNRATED")
        details = dict(result["details"])
        details["Factor conviction"] = f"{tier}" + (f" ({conv}/100)" if conv is not None else "")
        if f.get("magic_rank"):
            details["Magic Formula"] = f"#{f['magic_rank']}/{f['magic_universe']}"
        if f.get("f_score") is not None:
            details["F-Score"] = f"{f['f_score']}/9"
        details["Next step"] = ("Paste this ticker's payload into Claude Pro for a committee verdict "
                                "before acting" if tier in ("HIGH", "MEDIUM")
                                else "Momentum-only signal; factors weak — treat as watch, not buy")
        try:
            send_alert(ticker, score, "BUY", result["price"], details)
            state[ticker] = now
            print(f"{ticker}: → Discord BUY alert sent (conviction {tier})")
        except Exception as e:
            print(f"{ticker}: Discord alert failed (continuing): {e}")

    save_state(state)

    # Trigger pass: per-ticker deltas plus cross-sectional top-N rank shifts
    rank_reasons = committee.check_rank_triggers(
        ledger, {t: cur["overall"] for t, (cur, _) in evaluations.items()})
    for ticker, (cur, prev) in evaluations.items():
        reasons = committee.check_triggers(prev, cur)
        if ticker in rank_reasons:
            reasons.append(rank_reasons[ticker])
        if reasons:
            if dry_run:
                print(f"{ticker}: would trigger payload — {'; '.join(reasons)}")
                continue  # leave ledger untouched so the real run still fires
            path = committee.write_payload(ticker, cur, prev, reasons)
            payloads.append((ticker, path, reasons))
            print(f"{ticker}: committee payload {path.name} — {'; '.join(reasons)}")
        if dry_run:
            continue
        ledger[ticker] = {"overall": cur["overall"], "timing": cur["timing"],
                          "confidence": cur["confidence"], "rating": cur["rating"],
                          "days_to_earnings": cur["days_to_earnings"], "sector": cur["sector"],
                          "date": time.strftime("%Y-%m-%d %H:%M")}
    if not dry_run:
        committee.save_ledger(ledger)
        try:
            import dashboard
            dashboard.render()
        except Exception as e:
            print(f"dashboard render failed: {e}")

    # Housekeeping: prune payload files older than 14 days
    if committee.PROMPTS_DIR.exists():
        cutoff = now - 14 * 86400
        for f in committee.PROMPTS_DIR.glob("*.md"):
            if f.stat().st_mtime < cutoff:
                f.unlink()

    if payloads and not dry_run:
        lines = [f"📋 **{len(payloads)} committee payload(s) ready** — a thesis-relevant change was detected:"]
        lines += [f"• **{t}** — {'; '.join(r)}" for t, _, r in payloads]
        lines += ["**→ Do this:** open the matching note in Obsidian (`Stock Monitor/Committee Payloads`), "
                  "paste it into your Claude Pro committee session, then log the verdict: "
                  "`verdict.py add TICKER RATING`. No trade action until the committee rules."]
        try:
            send_message("\n".join(lines))
        except Exception as e:
            print(f"Discord payload notice failed: {e}")


if __name__ == "__main__":
    main()
    import notify
    if notify.had_failures():
        print(f"{len(notify.FAILURES)} Discord post(s) failed this run — failing job so CI surfaces it.")
        sys.exit(1)
