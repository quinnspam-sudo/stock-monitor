"""Watchlist monitor — scores each ticker and sends Discord alerts above threshold.

Run once:            ./venv/bin/python monitor.py
Run without alerts:  ./venv/bin/python monitor.py --dry-run
"""
import json
import sys
import time
import zlib
from pathlib import Path

import yfinance as yf

from notify import load_config, send_alert, send_message
import alert_stats
import committee
import consensus
import earnings_gate
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
    print(alert_stats.summary(now))  # measurement only — never feeds back into thresholds
    cooldown = cfg.get("cooldown_hours", 24) * 3600
    payloads = []
    evaluations = {}  # ticker -> (cur, prev); triggers checked after the loop so rank shifts are visible
    buy_queue = []    # BUY alerts deferred until factor ranks exist

    # Sharding: above ~100 tickers a full sweep would take 15+ min of CI per
    # run (~3 s/ticker), burning the free Actions tier. Each 15-min slot scores
    # one quarter of the list (stable crc32 assignment → full coverage every
    # hour) plus the current top-30 by ledger overall, so the names most likely
    # to alert keep true 15-min cadence. --full overrides (weekly/backtests).
    run_list = cfg["watchlist"]
    if len(run_list) > 100 and "--full" not in sys.argv:
        slot = int(time.time() // 900) % 4
        top = sorted((t for t in run_list if "overall" in ledger.get(t, {})),
                     key=lambda t: -ledger[t]["overall"])[:30]
        shard = [t for t in run_list
                 if zlib.crc32(t.encode()) % 4 == slot or t in top]
        print(f"sharded run: slot {slot}, {len(shard)}/{len(run_list)} tickers")
        run_list = shard

    print(f"{'TICKER':<8}{'PRICE':>10}{'SCORE':>7}  ACTION")
    for ticker in run_list:
        try:
            result = score_ticker(ticker)
        except Exception as e:
            print(f"{ticker:<8}  error: {e}")
            continue
        if result is None:
            print(f"{ticker:<8}  insufficient data")
            continue
        momentum_score = result["score"]

        # Committee noise gate + factor screen — computed BEFORE the buy/watch/
        # hold decision now (used to just confirm a decision already made on
        # momentum alone). This is what makes the new methodologies a real
        # entry-filter input, not just a downstream confirmation gate.
        cur = None
        try:
            cur = committee.gather(ticker, momentum_score)
            try:
                cur["factors"] = factors.compute(ticker)
            except Exception as e:
                print(f"         factors error: {e}")
            evaluations[ticker] = (cur, ledger.get(ticker))
            if not dry_run:  # dry runs must not consume triggers or pollute history
                committee.append_history(ticker, cur)
        except Exception as e:
            print(f"         committee error: {e}")

        # Blended score: 55% momentum (the timing/entry signal) + 45% factor
        # conviction (the 11-methodology confirmation blend) — factors weighted
        # slightly above momentum so a stock can't coast to BUY on price action
        # alone; weak factor support pulls the blended score down even before
        # the downstream conviction-tier gate (below) gets a chance to
        # downgrade it. Falls back to pure momentum only if factors are
        # entirely gapped (UNRATED), same as before this change.
        conv = tier = None
        if cur and cur.get("factors"):
            conv, tier = factors.conviction(cur["factors"])
        score = round(momentum_score * 0.55 + conv * 0.45) if conv is not None else momentum_score
        if cur is not None:  # persist what actually gates alerts, for the dashboard
            cur["blend"] = score
            cur["conviction"] = conv
            cur["tier"] = tier
            # Supermajority consensus vote (local math only — regime is cached)
            fmap = dict(cur.get("factors") or {})
            if conv is not None:
                fmap["_conviction"] = (conv, tier)
            try:
                cur["consensus"] = consensus.evaluate(momentum_score, fmap,
                                                      cur.get("earnings_gate"))
            except Exception as e:
                cur["consensus"] = None
                print(f"         consensus error: {e}")
        action = "BUY" if score >= cfg["alert_threshold"] else "WATCH" if score >= 60 else "HOLD"
        breakdown = f"(momentum {momentum_score}, factors {conv} {tier})" if conv is not None else "(factors GAPPED)"
        print(f"{ticker:<8}{result['price']:>10,.2f}{score:>7}  {action}  {breakdown}")

        if action == "BUY" and not dry_run:
            if now - state.get(ticker, 0) < cooldown:
                print(f"         (alert suppressed — within cooldown)")
            else:
                buy_queue.append((ticker, score, result))

    # Cross-sectional Magic Formula ranks over the whole watchlist
    factors.rank_universe({t: cur["factors"] for t, (cur, _) in evaluations.items()
                           if "factors" in cur})

    # BUY alerts fire post-ranking so each carries a factor-conviction verdict.
    # Hitting the momentum threshold only earns a spot in this queue — reaching
    # the actual BUY channel additionally requires HIGH/MEDIUM factor
    # conviction (the 10-methodology blend in factors.conviction()). This is
    # the whole point of having more methodologies: they're a real gate, not
    # just a label stapled onto the same alert. LOW/UNRATED gets downgraded to
    # a quiet updates-channel note instead of a pinged BUY alert.
    for ticker, score, result in sorted(buy_queue, key=lambda x: -x[1]):
        cur_eval = evaluations.get(ticker, ({}, None))[0]
        f = cur_eval.get("factors", {})
        conv, tier = factors.conviction(f) if f else (None, "UNRATED")
        state[ticker] = now  # cooldown applies regardless of outcome — don't re-evaluate every run either way
        # Earnings gate at the fixed strict bar: earnings within 10 business
        # days, positivity >=70 with >=3 signals, beat streak >=3/4. This is a
        # calibrated quality bar — the weekly alert count is whatever it is.
        gate = cur_eval.get("earnings_gate") or {}
        if not gate.get("actionable"):
            why = "; ".join(gate.get("reasons") or ["earnings gate data unavailable this run"])
            note = (f"⛔ **{ticker}** hit the BUY threshold (score {score}/100 at "
                    f"${result['price']:,.2f}, conviction {tier}) but the earnings gate is "
                    f"closed — {why}. Policy: actionable BUYs require earnings within "
                    f"{earnings_gate.WINDOW_BDAYS} business days AND a strict Earnings "
                    "Positivity pass. Logged as thesis-only, not a BUY alert.")
            try:
                send_message(note, kind="EARNINGS_GATE")
                print(f"{ticker}: BUY suppressed — earnings gate closed ({why}) — updates channel only")
            except Exception as e:
                print(f"{ticker}: Discord notice failed (continuing): {e}")
            continue
        # Supermajority consensus: >=75% of computable systems bullish, no hard
        # vetoes, friendly market regime. The last gate before an alert — this
        # is deliberately hard to pass; long silences are expected.
        cons = cur_eval.get("consensus") or {}
        if not cons.get("pass"):
            note = (f"🗳️ **{ticker}** cleared the earnings gate but FAILED the consensus vote "
                    f"(score {score}/100 at ${result['price']:,.2f}, conviction {tier}) — "
                    f"{cons.get('detail', 'consensus unavailable')}. High-conviction policy: "
                    "no BUY alert without supermajority agreement. Logged as thesis-only.")
            try:
                send_message(note, kind="CONSENSUS_VETO")
                print(f"{ticker}: BUY suppressed — consensus failed — updates channel only")
            except Exception as e:
                print(f"{ticker}: Discord notice failed (continuing): {e}")
            continue
        if tier in ("HIGH", "MEDIUM"):
            details = dict(result["details"])
            details["Factor conviction"] = f"{tier}" + (f" ({conv}/100)" if conv is not None else "")
            details["Earnings gate"] = (f"OPEN — earnings in {gate.get('bdays_to_earnings')} business day(s), "
                                        f"positivity {gate.get('positivity')}/100, "
                                        f"beat streak {gate.get('beats')}/{gate.get('beats_n')}")
            if f.get("magic_rank"):
                details["Magic Formula"] = f"#{f['magic_rank']}/{f['magic_universe']}"
            if f.get("f_score") is not None:
                details["F-Score"] = f"{f['f_score']}/9"
            details["Next step"] = "Paste this ticker's payload into Claude Pro for a committee verdict before acting"
            idea = cur_eval.get("call_idea")
            if idea and idea.get("contract"):
                import options_engine
                details["Call idea"] = options_engine.describe(idea)
            try:
                send_alert(ticker, score, "BUY", result["price"], details)
                print(f"{ticker}: → Discord BUY alert sent (conviction {tier})")
                alert_stats.record_alert(now)
                import obsidian
                obsidian.log_recommendation("buy_alert", ticker,
                                            f"score {score}/100, conviction {tier}", result["price"])
                import signal_tracker
                signal_tracker.record("buy_alert", ticker, result["price"],
                                      f"score {score}/100, conviction {tier}")
                if idea and idea.get("actionable"):
                    c = idea["contract"]
                    import options_engine
                    import notify
                    # Call ideas are buy signals — BUY channel, with ping.
                    send_message(
                        f"📞 **CALL IDEA — {ticker}** (options engine conviction on a "
                        "consensus-passed BUY — the strongest combined signal)\n"
                        f"{options_engine.describe(idea)}\n"
                        f"Max loss = 100% of premium (${c['mid'] * 100:,.0f}/contract). "
                        "Committee verdict before acting.", kind="CALL_IDEA", mention=True,
                        webhook_url=notify.load_config()["discord_webhook_url"])
                    obsidian.log_recommendation(
                        "call_idea", ticker,
                        f"{c['expiry']} ${c['strike']:g}C mid ${c['mid']:.2f} "
                        f"(Δ{c['delta']:.2f}, call score {idea['score']}/100)", c["mid"])
                    signal_tracker.record(
                        "call_idea", ticker, result["price"],
                        f"call score {idea['score']}/100",
                        contract={k: c.get(k) for k in ("expiry", "strike", "mid", "delta")})
                    print(f"{ticker}: → CALL idea announced: {c['expiry']} ${c['strike']:g}C")
            except Exception as e:
                print(f"{ticker}: Discord alert failed (continuing): {e}")
        else:
            note = (f"📉 **{ticker}** hit the momentum BUY threshold (score {score}/100 at "
                    f"${result['price']:,.2f}) but factor conviction is **{tier}**"
                    + (f" ({conv}/100)" if conv is not None else " (insufficient factor data)")
                    + " — downgraded to watch-only, not sent as a BUY alert. Momentum without "
                    "factor confirmation is the weakest signal; see the committee payload "
                    "(if one triggered) for the full factor breakdown.")
            try:
                send_message(note, kind="WATCH_DOWNGRADE")
                print(f"{ticker}: momentum BUY downgraded to watch (conviction {tier}) — updates channel only")
            except Exception as e:
                print(f"{ticker}: Discord notice failed (continuing): {e}")

    save_state(state)

    # Trigger pass: per-ticker deltas plus cross-sectional top-N rank shifts
    rank_reasons = committee.check_rank_triggers(
        ledger, {t: cur["overall"] for t, (cur, _) in evaluations.items()})
    digest = []  # triggers not worth a full payload — one summary line each
    for ticker, (cur, prev) in evaluations.items():
        reasons = committee.check_triggers(prev, cur)
        if ticker in rank_reasons:
            reasons.append(rank_reasons[ticker])
        if reasons:
            worthy = committee.payload_worthy(prev, cur, reasons)
            if dry_run:
                verb = "would trigger payload" if worthy else "would digest (no live decision)"
                print(f"{ticker}: {verb} — {'; '.join(reasons)}")
                continue  # leave ledger untouched so the real run still fires
            if worthy:
                path = committee.write_payload(ticker, cur, prev, reasons)
                payloads.append((ticker, path, reasons))
                print(f"{ticker}: committee payload {path.name} — {'; '.join(reasons)}")
            else:
                digest.append(f"**{ticker}** ({cur['rating']}): {'; '.join(reasons)}")
                print(f"{ticker}: trigger digested, no payload (no earnings ≤10 bdays, "
                      f"no exit-side move) — {'; '.join(reasons)}")
        if dry_run:
            continue
        ledger[ticker] = {"overall": cur["overall"], "timing": cur["timing"],
                          "confidence": cur["confidence"], "rating": cur["rating"],
                          "days_to_earnings": cur["days_to_earnings"], "sector": cur["sector"],
                          "blend": cur.get("blend"), "conviction": cur.get("conviction"),
                          "tier": cur.get("tier"),
                          "earnings_gate": {k: (cur.get("earnings_gate") or {}).get(k)
                                            for k in ("bdays_to_earnings", "positivity", "beats",
                                                      "beats_n", "in_window", "positivity_pass",
                                                      "actionable", "reasons")}
                          if cur.get("earnings_gate") else None,
                          "date": time.strftime("%Y-%m-%d %H:%M")}
    if digest and not dry_run:
        note = ("🗞 **Committee digest** — triggers fired outside the earnings window; "
                "no payloads written (nothing actionable to decide yet):\n"
                + "\n".join(f"- {d}" for d in digest))
        try:
            send_message(note, kind="COMMITTEE_DIGEST")
            print(f"digest: {len(digest)} suppressed trigger(s) → updates channel")
        except Exception as e:
            print(f"digest Discord notice failed (continuing): {e}")

    if not dry_run:
        committee.save_ledger(ledger)
        try:
            import dashboard
            dashboard.render()
        except Exception as e:
            print(f"dashboard render failed: {e}")
        try:
            import ecosystem
            ecosystem.render()
        except Exception as e:
            print(f"ecosystem render failed: {e}")

    # Housekeeping: prune payload files older than 14 days — but never one
    # still referenced by an unreplayed obsidian_queue.jsonl mirror_payload
    # event. If the Mac has been off longer than the prune window, deleting
    # (and committing the deletion of) that file would silently drop the
    # payload from Obsidian forever once obsidian_sync.py finally catches up
    # and finds it missing.
    if committee.PROMPTS_DIR.exists():
        queue_path = Path(__file__).parent / "obsidian_queue.jsonl"
        referenced = set()
        if queue_path.exists():
            for line in queue_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("type") == "mirror_payload":
                        referenced.add(event["path"])
                except Exception:
                    pass
        cutoff = now - 14 * 86400
        for f in committee.PROMPTS_DIR.glob("*.md"):
            rel = str(f.relative_to(Path(__file__).parent))
            if f.stat().st_mtime < cutoff and rel not in referenced:
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
