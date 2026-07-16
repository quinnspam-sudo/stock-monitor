"""Paper-trading executor — turns the system's signals into real (paper) orders.

This is the "robot" the rest of stock-monitor already assumes: the BUY alert
prescribes a mechanical equal-size buy, sell_check prescribes mechanical exits,
and actual_trades.json records "what actually happened". Until now a human typed
those into Discord (`Bought $20 of NVDA`). This executor removes that lag by
placing the orders on an Alpaca **paper** account and writing the identical
actual_trades.json records — so performance.py, sell_check.py, and the weekly
review all pick them up with zero other changes.

Scope of the current trial (Quinn, 2026-07-13): **paper only**, fully automatic
(no per-trade approval — the point is a clean 100%-adherence track record to
compare against the out-of-sample test), running until **2026-08-13**. Guardrails
below do the oversight; a kill switch halts everything instantly.

What it does each run (scheduled every 15 min during market hours):
  BUY  — execute today's fresh buy_alert signals (signals.json) that aren't
         already executed, subject to guardrails.
  SELL — apply the SAME frozen exit rules as sell_check.py (imported constants,
         no duplicate thresholds) to the live paper positions, and close any
         that trigger.
  BUY CALL  — execute today's fresh call_conviction / etf_call_conviction
         signals (written by options_engine.py) as 1-contract paper option
         buys, capped by config.execution.option_premium_usd_cap. Recorded to
         option_trades.json — a SEPARATE ledger from actual_trades.json so
         options can never contaminate performance.py/sell_check's equity math.
  SELL CALL — closes an option position at +/-option_profit_target_pct /
         option_stop_loss_pct on premium, or force-closes on/after expiry day
         regardless of P/L (assignment/pin-risk safety net for an unattended
         account).
  RECONCILE — compare Alpaca's positions against actual_trades.json and report
         any drift.

Requires options trading enabled on the Alpaca PAPER account (an account-level
setting, not a code flag) — same ALPACA_API_KEY/ALPACA_SECRET_KEY as stocks.

Nothing here can touch real money: see broker.py (paper hard-wired). It never
changes the frozen trading RULES (EVALUATION_PROTOCOL.md) — it only executes
them.

Run: ./venv/bin/python execute.py [--dry-run] [--force]
  --dry-run : compute intended orders and print them, place NOTHING
  --force   : ignore the market-hours gate (for off-hours testing)
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import broker
import notify
import sell_check as sc
from performance import compute_open_positions

BASE = Path(__file__).parent
CONFIG = BASE / "config.json"
SIGNALS = BASE / "signals.json"
TRADES = BASE / "actual_trades.json"
OPTION_TRADES = BASE / "option_trades.json"    # separate ledger — options never touch the
                                                # frozen stock pipeline (performance.py/sell_check)
EXECUTED = BASE / "executed_orders.json"      # dedup ledger of orders placed
STATE = BASE / "execution_state.json"          # per-(ticker,kind) sell + per-name buy cooldowns, last_run

OPTION_KINDS = ("call_conviction", "etf_call_conviction")  # written by options_engine.py

DEFAULTS = {
    "enabled": True,
    "mode": "paper",              # paper only; "live" is intentionally unsupported here
    "trial_end": "2026-08-13",    # stop opening new positions after this date
    "kill_switch": False,         # set true to halt ALL execution immediately
    "market_hours_only": True,
    "max_open_positions": 25,     # never hold more than this many names at once
    "max_position_usd": None,     # per-order size; None -> config.buy_amount_usd
    "per_name_max_usd": None,     # optional total-$ ceiling per name; None -> unlimited
    "buy_cooldown_hours": 24,     # min hours between repeat buys of the SAME name
    "daily_deploy_cap_usd": 200,  # max NEW dollars deployed per calendar day
    "sell_cooldown_hours": 24,    # mirrors sell_check's per-(ticker,kind) cooldown
    "option_premium_usd_cap": 300,   # skip a call idea if 1 contract (premium x100) costs more
    "option_profit_target_pct": 0.50,  # close a call position at +50% premium gain
    "option_stop_loss_pct": -0.50,     # close a call position at -50% premium loss
}


def _coid(signal_key):
    """Deterministic Alpaca client_order_id for a signal — same signal, same id,
    every time. Alpaca enforces client_order_id uniqueness, so even if the dedup
    ledger is lost or a run crashes between submit and persist, resubmitting this
    signal recovers the original order instead of placing a second one
    (broker._submit). 43 chars, under Alpaca's 48-char limit."""
    return "sm-" + hashlib.sha1(signal_key.encode()).hexdigest()


def _persist_executed(executed, dry):
    """Write the dedup ledger NOW, not at end-of-run — shrinks the crash window
    in which an order exists at Alpaca but not in executed_orders.json to the
    single submit call (which the deterministic client_order_id covers anyway)."""
    if not dry:
        EXECUTED.write_text(json.dumps(executed, indent=2))


def _load(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _cfg():
    cfg = json.loads(CONFIG.read_text())
    ex = dict(DEFAULTS)
    ex.update(cfg.get("execution", {}))
    size = ex["max_position_usd"] or cfg.get("buy_amount_usd") or 20
    ex["max_position_usd"] = size
    # per_name_max_usd stays as configured — None means no total ceiling per name
    # (repeat buys are gated by buy_cooldown_hours, not a market-value cap).
    # Out-of-band kill switch: STOCKMON_KILL_SWITCH is fed from a GitHub Actions
    # repo *variable* (Settings → Secrets and variables → Actions → Variables,
    # or `gh variable set STOCKMON_KILL_SWITCH --body true`). Unlike
    # config.execution.kill_switch it needs no git commit to flip, so it works
    # even if pushes are failing or the repo state is suspect.
    if os.environ.get("STOCKMON_KILL_SWITCH", "").strip().lower() in ("1", "true", "yes", "on"):
        ex["kill_switch"] = True
    return cfg, ex


_SPY_CACHE = {}


def _spy_price():
    """SPY's price right now — clocked at each fill so every paper trade carries
    the exact benchmark it must be measured against. Cached per process so a run
    with several fills stamps them all against one consistent SPY quote."""
    if "p" in _SPY_CACHE:
        return _SPY_CACHE["p"]
    p = None
    try:
        import yfinance as yf
        p = float(yf.Ticker("SPY").history(period="1d")["Close"].iloc[-1])
    except Exception:
        pass
    _SPY_CACHE["p"] = p
    return p


def _record_trade(action, ticker, fill, note, spy=None):
    """Append to actual_trades.json in the EXACT schema the Discord buy-log bot
    writes (buy_intake.py) so every downstream consumer treats a paper fill
    identically to a hand-logged trade — plus `spy_at_trade`, SPY's price at the
    moment of the fill, so the SPY benchmark is measured from the same instant as
    the trade (not from the day's close). This is what makes the vs-SPY
    comparison exact rather than approximate."""
    trades = _load(TRADES, [])
    amount = round(fill["shares"] * fill["price"], 2)
    rec = {"date": datetime.now().strftime("%Y-%m-%d"), "ticker": ticker,
           "action": action, "amount": amount, "price": fill["price"],
           "shares": fill["shares"], "note": note}
    if spy is not None:
        rec["spy_at_trade"] = round(spy, 4)
    trades.append(rec)
    TRADES.write_text(json.dumps(trades, indent=2))
    try:
        import obsidian
        obsidian.log_actual_trade(action, ticker, amount, fill["price"], fill["shares"],
                                  note=note)
    except Exception:
        pass


def _today_deployed(trades, today):
    return sum(t["amount"] for t in trades
               if t.get("action") == "BUY" and t.get("date") == today)


def buy_pass(bk, cfg, ex, executed, state, dry, log):
    """Execute today's fresh buy_alert signals under the guardrails."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if today > ex["trial_end"]:
        log.append(f"trial ended {ex['trial_end']} — no new positions opened")
        return []
    sigs = _load(SIGNALS, [])
    done_keys = {e["signal_key"] for e in executed}
    fresh = [s for s in sigs if s.get("kind") == "buy_alert" and s.get("date") == today
             and f"{s['ticker']}:{s.get('ts', s['date'])}" not in done_keys]
    if not fresh:
        return []

    positions = bk.positions()
    trades = _load(TRADES, [])
    deployed = _today_deployed(trades, today)
    acct = bk.account()
    size = ex["max_position_usd"]
    buy_cooldown = ex["buy_cooldown_hours"] * 3600
    spy = _spy_price()
    filled = []

    # A legitimate buy_alert only ever names a config.watchlist ticker (monitor.py
    # scores nothing else). signals.json is a tracked file this unattended executor
    # trusts, so anything writing to it — a merged PR, the cron PAT, direct repo
    # access — could otherwise inject an arbitrary ticker and have it bought. The
    # watchlist gate makes that class of state-poisoning a no-op regardless of the
    # dollar caps (which are None by design for the trial). Not a substitute for
    # protecting write access — a defense-in-depth backstop.
    allowed = set(cfg.get("watchlist", []))

    # max_open_positions and daily_deploy_cap_usd are None (unlimited) per Quinn's
    # config — the paper trial executes EVERY signal for a clean 100%-adherence
    # record. Repeat buys of the SAME name are allowed (no total ceiling unless
    # per_name_max_usd is set), but gated by buy_cooldown_hours so a single name
    # can add at most once per cooldown window. Other guards: kill switch, the
    # optional per-name ceiling, and paper buying power.
    for s in fresh:
        t = s["ticker"]
        key = f"{t}:{s.get('ts', s['date'])}"
        reason = None
        if t not in allowed:
            reason = "ticker not in config.watchlist — rejected (possible signals.json poisoning)"
        elif ex["kill_switch"]:
            reason = "kill switch on"
        elif ex["max_open_positions"] and len(positions) >= ex["max_open_positions"] and t not in positions:
            reason = f"max_open_positions {ex['max_open_positions']} reached"
        elif ex["per_name_max_usd"] and positions.get(t, {}).get("market_value", 0) >= ex["per_name_max_usd"]:
            reason = f"already at per-name ceiling ${ex['per_name_max_usd']}"
        elif now.timestamp() - state.get(f"buy:{t}", 0) < buy_cooldown:
            reason = f"buy cooldown {ex['buy_cooldown_hours']}h not elapsed for {t}"
        elif ex["daily_deploy_cap_usd"] and deployed + size > ex["daily_deploy_cap_usd"]:
            reason = f"daily deploy cap ${ex['daily_deploy_cap_usd']} would be exceeded"
        elif acct["buying_power"] < size:
            reason = f"insufficient paper buying power (${acct['buying_power']:.0f})"
        if reason:
            log.append(f"SKIP BUY {t}: {reason}")
            continue

        if dry:
            log.append(f"[dry] BUY {t} ~${size} (signal {s.get('detail','')})")
            executed.append({"signal_key": key, "ticker": t, "action": "BUY",
                             "dry": True, "when": now.isoformat(timespec='minutes')})
            deployed += size
            state[f"buy:{t}"] = now.timestamp()  # start the per-name cooldown
            continue

        fill = bk.buy_notional(t, size, client_order_id=_coid(key))
        if fill.get("filled"):
            note = f"Paper auto-exec BUY ${size:.2f} on buy_alert ({s.get('detail','')})"
            _record_trade("BUY", t, fill, note, spy)
            deployed += fill["shares"] * fill["price"]
            prev = positions.get(t, {}).get("market_value", 0)
            positions[t] = {"market_value": prev + fill["shares"] * fill["price"]}
            state[f"buy:{t}"] = now.timestamp()  # start the per-name cooldown
            filled.append((t, fill))
            log.append(f"BUY {t}: {fill['shares']:.4f} @ ${fill['price']:.2f}")
        else:
            log.append(f"BUY {t}: not filled ({fill.get('status')}) — will retry next run")
        # record the signal as handled either way so a stuck/rejected order
        # doesn't get resubmitted every 15 minutes; a pending fill reconciles
        # via the reconcile pass, not by re-buying.
        executed.append({"signal_key": key, "ticker": t, "action": "BUY",
                         "order_id": fill.get("order_id"), "filled": fill.get("filled", False),
                         "when": datetime.now().isoformat(timespec='minutes')})
        _persist_executed(executed, dry)
    return filled


def sell_pass(bk, ex, state, dry, log):
    """Apply the frozen sell_check exit rules to live paper positions.

    Uses sell_check's own constants and helpers (imported, not re-tuned) so the
    executor can never drift from the frozen exit rules. The decision tree
    mirrors sell_check.main()'s; both read the same STOP_LOSS_PCT / TRAIL_STOP_PCT
    / DISASTER_PCT / REBALANCE_DAYS."""
    positions = bk.positions()
    if not positions:
        return []
    now = datetime.now()
    cooldown = ex["sell_cooldown_hours"] * 3600
    healthy = sc.market_is_healthy()
    log.append(f"market {'HEALTHY (stops armed)' if healthy else 'WEAK (disaster floor only)'}")
    spy = _spy_price()
    sold = []

    # held_since / avg_cost come from OUR ledger (average-cost basis), matching
    # sell_check; Alpaca's avg_entry_price would ignore prior partial sells.
    ledger_pos = compute_open_positions()

    for t, p in positions.items():
        lp = ledger_pos.get(t, {})
        entry = lp.get("avg_cost") or p["avg_cost"]
        held_since = lp.get("held_since")
        try:
            import yfinance as yf
            price = float(yf.Ticker(t).history(period="1d")["Close"].iloc[-1])
        except Exception:
            continue
        pct = price / entry - 1
        alerts = []
        if pct <= sc.DISASTER_PCT:
            alerts.append(("DISASTER_STOP", f"down {pct:+.1%} vs ${entry:.2f} (-30% floor)"))
        elif not healthy:
            pass  # only the disaster floor is armed in a weak tape
        elif pct <= sc.STOP_LOSS_PCT:
            alerts.append(("STOP_LOSS", f"down {pct:+.1%} vs ${entry:.2f}, SPY>50d"))
        elif held_since:
            peak = sc.peak_close_since(t, held_since)
            if peak:
                peak = max(peak, entry)
                off = price / peak - 1
                if off <= sc.TRAIL_STOP_PCT:
                    alerts.append(("TRAIL_STOP", f"{off:+.1%} off peak ${peak:.2f}"))
        if held_since:
            try:
                days = (now - datetime.strptime(held_since, "%Y-%m-%d")).days
                if days >= sc.REBALANCE_DAYS:
                    alerts.append(("REBALANCE_DUE", f"held {days}d (>= {sc.REBALANCE_DAYS})"))
            except ValueError:
                pass

        for kind, reason in alerts:
            k = f"{t}:{kind}"
            if now.timestamp() - state.get(k, 0) < cooldown:
                continue
            if dry:
                log.append(f"[dry] SELL {t} ({kind}: {reason})")
                state[k] = now.timestamp()
                continue
            fill = bk.close(t)
            if fill.get("filled"):
                _record_trade("SELL", t, fill, f"Paper auto-exec {kind}: {reason}", spy)
                state[k] = now.timestamp()
                sold.append((t, kind, fill))
                log.append(f"SELL {t}: {kind} — {fill['shares']:.4f} @ ${fill['price']:.2f}")
                import obsidian
                obsidian.log_recommendation("sell_signal", t, f"{kind} (paper-exec): {reason}", price)
            else:
                log.append(f"SELL {t}: {kind} not filled ({fill.get('status')})")
            break  # one exit per name per run
    return sold


def _occ_symbol(ticker, expiry, strike):
    """Build the OCC/Alpaca option symbol, e.g. QQQ + 2026-09-18 + 690.0 call
    -> 'QQQ260918C00690000'. Calls only — this system never shorts or buys puts."""
    d = datetime.strptime(expiry, "%Y-%m-%d").strftime("%y%m%d")
    return f"{ticker}{d}C{int(round(strike * 1000)):08d}"


def _record_option_trade(action, ticker, occ_symbol, expiry, strike, fill, note, spy=None):
    """Append to option_trades.json — deliberately NOT actual_trades.json. Mixing
    OCC symbols into the stock ledger would corrupt performance.py/sell_check,
    which assume every ticker there is an equity. contracts x100 = notional."""
    trades = _load(OPTION_TRADES, [])
    amount = round(fill["shares"] * fill["price"] * 100, 2)
    rec = {"date": datetime.now().strftime("%Y-%m-%d"), "ticker": ticker,
           "occ_symbol": occ_symbol, "expiry": expiry, "strike": strike, "right": "C",
           "action": action, "contracts": fill["shares"], "premium": fill["price"],
           "amount": amount, "note": note}
    if spy is not None:
        rec["spy_at_trade"] = round(spy, 4)
    trades.append(rec)
    OPTION_TRADES.write_text(json.dumps(trades, indent=2))
    try:
        import obsidian
        obsidian.log_actual_trade(action, f"{ticker} {expiry} ${strike:g}C", amount,
                                  fill["price"], fill["shares"], note=note)
    except Exception:
        pass


def buy_options_pass(bk, cfg, ex, executed, dry, log):
    """Execute call_conviction / etf_call_conviction signals (written by
    options_engine.py) under the same discipline as stock buys: 1 contract
    per idea, capped by option_premium_usd_cap, no re-quote — the scan-time
    mid is only used for the cap check; the actual fill is a live market
    order, so a slightly stale mid never mis-prices the trade.

    Unlike the stock side's today-only buy_alert window, this looks back 2
    calendar days, not just today: options_engine.py's single daily scan
    fires at 12:45 PT and execute.py's last run of the day is 12:50 PT — a
    5-minute gap that a slow scan can miss entirely, which silently dropped
    every conviction-call idea before this was widened (Quinn, 2026-07-15)."""
    today = datetime.now().strftime("%Y-%m-%d")
    if today > ex["trial_end"]:
        return []
    cutoff = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    sigs = _load(SIGNALS, [])
    done_keys = {e["signal_key"] for e in executed}
    fresh = [s for s in sigs if s.get("kind") in OPTION_KINDS and s.get("date", "") >= cutoff
             and f"{s['ticker']}:{s['kind']}:{s.get('ts', s['date'])}" not in done_keys]
    if not fresh:
        return []

    acct = bk.account()
    positions = bk.positions()
    spy = _spy_price()
    filled = []

    # Conviction-call ideas only ever name a watchlist (call_conviction) or
    # etf_watchlist (etf_call_conviction) ticker — same signals.json-poisoning
    # backstop as buy_pass. See the note there.
    allowed = set(cfg.get("watchlist", [])) | set(cfg.get("etf_watchlist", []))

    for s in fresh:
        t = s["ticker"]
        c = s.get("contract") or {}
        key = f"{t}:{s['kind']}:{s.get('ts', s['date'])}"
        expiry, strike, premium = c.get("expiry"), c.get("strike"), c.get("mid")
        reason = None
        if t not in allowed:
            reason = "ticker not in watchlist/etf_watchlist — rejected (possible signals.json poisoning)"
        elif ex["kill_switch"]:
            reason = "kill switch on"
        elif not (expiry and strike and premium):
            reason = "signal missing contract expiry/strike/premium"
        else:
            occ = _occ_symbol(t, expiry, strike)
            cost = premium * 100
            if occ in positions:
                reason = "already holding this exact contract"
            elif cost > ex["option_premium_usd_cap"]:
                reason = f"premium ${cost:.0f}/contract exceeds cap ${ex['option_premium_usd_cap']}"
            elif acct["buying_power"] < cost:
                reason = f"insufficient paper buying power (${acct['buying_power']:.0f})"
        if reason:
            log.append(f"SKIP CALL {t}: {reason}")
            continue

        if dry:
            log.append(f"[dry] BUY CALL {t} {expiry} ${strike:g}C ~${premium*100:.0f} "
                       f"(signal {s.get('detail','')})")
            executed.append({"signal_key": key, "ticker": t, "action": "BUY_CALL",
                             "dry": True, "when": datetime.now().isoformat(timespec='minutes')})
            continue

        try:
            fill = bk.buy_option(occ, qty=1, client_order_id=_coid(key))
        except Exception as e:
            # Alpaca rejects the whole submit_order call (e.g. options trading
            # not enabled on the account) rather than returning a rejected-order
            # status — without this catch that exception would propagate out of
            # main() and crash the run before stock buys/sells even got their
            # state persisted. Record it as a non-fill and keep going.
            log.append(f"SKIP CALL {t}: order rejected ({e})")
            executed.append({"signal_key": key, "ticker": t, "action": "BUY_CALL",
                             "filled": False, "error": str(e),
                             "when": datetime.now().isoformat(timespec='minutes')})
            _persist_executed(executed, dry)
            continue
        if fill.get("filled"):
            note = f"Paper auto-exec CALL BUY on {s['kind']} ({s.get('detail','')})"
            _record_option_trade("BUY", t, occ, expiry, strike, fill, note, spy)
            positions[occ] = {"market_value": fill["shares"] * fill["price"] * 100}
            filled.append((t, occ, fill))
            log.append(f"BUY CALL {t} {expiry} ${strike:g}C: {fill['shares']:.0f} contract(s) "
                      f"@ ${fill['price']:.2f}")
        else:
            log.append(f"BUY CALL {t}: not filled ({fill.get('status')}) — will retry next run")
        executed.append({"signal_key": key, "ticker": t, "action": "BUY_CALL",
                         "order_id": fill.get("order_id"), "filled": fill.get("filled", False),
                         "when": datetime.now().isoformat(timespec='minutes')})
        _persist_executed(executed, dry)
    return filled


def _open_option_lots():
    """FIFO-open option contracts still outstanding, keyed by occ_symbol, from
    our own ledger — mirrors compute_open_positions() but for options."""
    trades = _load(OPTION_TRADES, [])
    open_lots = {}
    for t in sorted(trades, key=lambda x: x["date"]):
        occ = t["occ_symbol"]
        if t["action"] == "BUY":
            open_lots[occ] = {"ticker": t["ticker"], "expiry": t["expiry"], "strike": t["strike"],
                              "premium": t["premium"], "contracts": t["contracts"]}
        else:
            open_lots.pop(occ, None)
    return open_lots


def sell_options_pass(bk, ex, state, dry, log):
    """Close option positions on a simple mechanical rule (Quinn, 2026-07-15):
    +/- option_profit_target_pct / option_stop_loss_pct on premium. Plus a hard
    safety net independent of that choice — force-close on/after expiry day
    regardless of P/L, since an unattended account should never risk assignment
    or letting a contract expire worthless by inaction."""
    lots = _open_option_lots()
    if not lots:
        return []
    positions = bk.positions()
    today = datetime.now().strftime("%Y-%m-%d")
    spy = _spy_price()
    sold = []

    for occ, lot in lots.items():
        p = positions.get(occ)
        if p is None:
            continue  # already closed on Alpaca (assignment/expiry) — ledger will drift; reconcile reports it
        cost = lot["premium"] * lot["contracts"] * 100
        pct = (p["market_value"] / cost - 1) if cost else 0
        kind, reason = None, None
        if today >= lot["expiry"]:
            kind, reason = "EXPIRY_SAFETY", f"on/after expiry {lot['expiry']} — force-closing"
        elif pct >= ex["option_profit_target_pct"]:
            kind, reason = "PROFIT_TARGET", f"premium {pct:+.0%} >= target {ex['option_profit_target_pct']:+.0%}"
        elif pct <= ex["option_stop_loss_pct"]:
            kind, reason = "STOP_LOSS", f"premium {pct:+.0%} <= stop {ex['option_stop_loss_pct']:+.0%}"
        if not kind:
            continue

        if dry:
            log.append(f"[dry] SELL CALL {occ} ({kind}: {reason})")
            continue
        try:
            fill = bk.close(occ)
        except Exception as e:
            log.append(f"SKIP CALL CLOSE {occ}: order rejected ({e}) — will retry next run")
            continue
        if fill.get("filled"):
            note = f"Paper auto-exec {kind}: {reason}"
            _record_option_trade("SELL", lot["ticker"], occ, lot["expiry"], lot["strike"],
                                 fill, note, spy)
            sold.append((lot["ticker"], occ, kind, fill))
            log.append(f"SELL CALL {lot['ticker']} {occ}: {kind} — {fill['shares']:.0f} "
                      f"contract(s) @ ${fill['price']:.2f}")
        else:
            log.append(f"SELL CALL {occ}: {kind} not filled ({fill.get('status')})")
    return sold


def flatten_pass(bk, ex, state, dry, log):
    """On/after trial_end, liquidate ALL paper positions once for a clean final
    tally, then stay flat. Idempotent via state['flattened'] so it happens
    exactly once even though the workflow keeps firing until its card is
    disabled."""
    positions = bk.positions()
    spy = _spy_price()
    sold = []
    option_lots = _open_option_lots()
    for t in list(positions):
        if dry:
            log.append(f"[dry] FLATTEN {t}")
            continue
        fill = bk.close(t)
        if not fill.get("filled"):
            continue
        if t in option_lots:
            lot = option_lots[t]
            _record_option_trade("SELL", lot["ticker"], t, lot["expiry"], lot["strike"], fill,
                                 "Paper trial end (2026-08-13) — auto-flatten", spy)
            log.append(f"FLATTEN CALL {lot['ticker']} {t}: {fill['shares']:.0f} contract(s) "
                      f"@ ${fill['price']:.2f}")
        else:
            _record_trade("SELL", t, fill, "Paper trial end (2026-08-13) — auto-flatten", spy)
            log.append(f"FLATTEN {t}: {fill['shares']:.4f} @ ${fill['price']:.2f}")
        sold.append((t, "TRIAL_END", fill))
    if not dry:
        state["flattened"] = datetime.now().strftime("%Y-%m-%d")
    return sold


def _build_lots(trades):
    """FIFO lot-matching: each BUY opens a lot; each SELL closes the oldest open
    lot(s) of that ticker. This is what makes repeated round-trips in the same
    name pair correctly — the first sell closes the first buy, not the last. The
    executor sells whole positions, so a sell closes lots in FIFO order until its
    shares are exhausted. Returns a flat list of lots, each carrying its own
    entry AND (if closed) its own matched exit + SPY prices at both ends."""
    trades = sorted(trades, key=lambda t: t["date"])  # stable → intraday order kept
    open_lots, lots = {}, []
    for t in trades:
        tk, spy = t["ticker"], t.get("spy_at_trade")
        if t["action"] == "BUY":
            lot = {"ticker": tk, "cost": t["amount"], "shares": t["shares"],
                   "buy_px": t["price"], "spy_buy": spy, "buy_date": t["date"],
                   "sell_px": None, "spy_sell": None, "sell_date": None, "open": True}
            open_lots.setdefault(tk, []).append(lot); lots.append(lot)
        else:  # SELL — close oldest open lots first (FIFO)
            rem = t["shares"]
            for lot in open_lots.get(tk, []):
                if not lot["open"]:
                    continue
                lot.update(sell_px=t["price"], spy_sell=spy, sell_date=t["date"], open=False)
                rem -= lot["shares"]
                if rem <= 1e-9:
                    break
            open_lots[tk] = [l for l in open_lots.get(tk, []) if l["open"]]
    return lots


def report():
    """Paper book vs a MATCHED dollar-cost SPY benchmark. Every $10 the algo puts
    into a stock, $10 goes into SPY at the SAME instant (spy_at_trade); the SPY
    leg closes when the stock's lot does (FIFO-matched). At any moment both routes
    have identical cost-basis capital deployed — the value gap is the alpha.
    Prints the current head-to-head PLUS a daily equity curve of both routes."""
    import yfinance as yf
    trades = _load(TRADES, [])
    lots = [l for l in _build_lots(trades) if l["spy_buy"]]
    if not lots:
        print("No paper trades (with SPY stamp) yet."); return
    spy_now = _spy_price()
    tickers = sorted({l["ticker"] for l in lots})
    cur = {}
    for tk in tickers:
        try:
            cur[tk] = float(yf.Ticker(tk).history(period="1d")["Close"].iloc[-1])
        except Exception:
            cur[tk] = None

    # ── current head-to-head (per lot, aggregated by ticker) ──
    inv = paper_val = spy_val = 0.0
    per_tk = {}
    for l in lots:
        if l["open"]:
            exit_px, spy_exit, tag = cur.get(l["ticker"]), spy_now, "open"
        else:
            exit_px, spy_exit, tag = l["sell_px"], l["spy_sell"] or spy_now, "closed"
        if not exit_px or not spy_exit:
            continue
        pv = l["cost"] * exit_px / l["buy_px"]
        sv = l["cost"] * spy_exit / l["spy_buy"]
        inv += l["cost"]; paper_val += pv; spy_val += sv
        a = per_tk.setdefault(l["ticker"], {"inv": 0, "pv": 0, "sv": 0, "tags": set()})
        a["inv"] += l["cost"]; a["pv"] += pv; a["sv"] += sv; a["tags"].add(tag)

    print(f"\nPAPER BOOK vs MATCHED-$ SPY   (SPY now ${spy_now:.2f})\n" + "-" * 62)
    for tk in sorted(per_tk):
        a = per_tk[tk]
        sr, pr = a["pv"] / a["inv"] - 1, a["sv"] / a["inv"] - 1
        print(f"  {tk:6} {'/'.join(sorted(a['tags'])):12}  stock {sr:+.2%}   spy {pr:+.2%}   "
              f"alpha {sr - pr:+.2%}")
    if inv:
        print("-" * 62)
        print(f"  invested ${inv:.2f} | paper ${paper_val:.2f} ({paper_val/inv-1:+.2%}) | "
              f"SPY-matched ${spy_val:.2f} ({spy_val/inv-1:+.2%})")
        print(f"  TOTAL ALPHA vs SPY: {(paper_val-spy_val)/inv:+.2%}  (${paper_val-spy_val:+.2f})")

    # ── daily equity curve: both routes, same cash flows, marked to each day's close ──
    start = min(l["buy_date"] for l in lots)
    try:
        hist = yf.download(tickers + ["SPY"], start=start, auto_adjust=True,
                           progress=False, group_by="column")["Close"]
        if hasattr(hist, "to_frame"):  # single ticker → Series
            hist = hist.to_frame()
        days = [d.strftime("%Y-%m-%d") for d in hist.index]
        closes = {tk: {d.strftime("%Y-%m-%d"): (float(hist[tk][d]) if tk in hist and hist[tk][d] == hist[tk][d] else None)
                       for d in hist.index} for tk in tickers + ["SPY"]}
    except Exception as e:
        print(f"\n(equity curve unavailable: {e})"); return

    print(f"\nDAILY EQUITY CURVE — matched cash in both routes\n"
          f"  {'date':10} {'invested':>10} {'algo':>10} {'SPY':>10} {'alpha$':>9} {'alpha%':>8}")
    for d in days:
        spd = closes["SPY"].get(d)
        if not spd:
            continue
        inv_d = algo_d = spy_d = 0.0
        for l in lots:
            if l["buy_date"] > d:
                continue
            inv_d += l["cost"]
            if l["sell_date"] and l["sell_date"] <= d:      # realized → frozen as cash
                algo_d += l["cost"] * l["sell_px"] / l["buy_px"]
                spy_d += l["cost"] * l["spy_sell"] / l["spy_buy"]
            else:                                            # open → mark to day's close
                sc = closes.get(l["ticker"], {}).get(d)
                if not sc:
                    continue
                algo_d += l["cost"] * sc / l["buy_px"]
                spy_d += l["cost"] * spd / l["spy_buy"]
        if inv_d:
            print(f"  {d:10} {inv_d:>10.2f} {algo_d:>10.2f} {spy_d:>10.2f} "
                  f"{algo_d-spy_d:>+9.2f} {(algo_d-spy_d)/inv_d:>+7.2%}")


def reconcile(bk, log):
    """Report drift between the broker's paper positions and our ledger — a
    silent divergence (a fill we missed, a manual paper trade) would corrupt the
    track record, so surface it."""
    broker_pos = bk.positions()
    ledger_pos = compute_open_positions()  # equities (actual_trades.json)
    option_lots = _open_option_lots()      # options live in their own ledger
    ledger_qty = {t: p["shares"] for t, p in ledger_pos.items()}
    ledger_qty.update({occ: lot["contracts"] for occ, lot in option_lots.items()})

    only_broker = set(broker_pos) - set(ledger_qty)
    only_ledger = set(ledger_qty) - set(broker_pos)
    if only_broker:
        log.append(f"RECONCILE: on Alpaca but not in ledger: {', '.join(sorted(only_broker))}")
    if only_ledger:
        log.append(f"RECONCILE: in ledger but not on Alpaca: {', '.join(sorted(only_ledger))}")
    # symbol match isn't enough — a missed partial fill or manual paper trade
    # leaves the symbol present on both sides with the wrong size, silently
    # corrupting the track record. Compare quantities too (0.1% tolerance for
    # fractional-share rounding).
    for sym in set(broker_pos) & set(ledger_qty):
        b, l = broker_pos[sym]["shares"], ledger_qty[sym]
        if l and abs(b - l) > 0.001 * max(abs(b), abs(l)):
            log.append(f"RECONCILE: {sym} quantity drift — Alpaca {b:g} vs ledger {l:g}")


def main():
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    if "--report" in sys.argv:
        report()
        return
    cfg, ex = _cfg()

    if not ex["enabled"]:
        print("execution disabled (config.execution.enabled = false)")
        return
    if ex["kill_switch"]:
        notify.send_message("🛑 **PAPER EXECUTOR — KILL SWITCH ON.** No orders placed.",
                            kind="EXECUTE")
        print("kill switch on — halting")
        return
    if ex["mode"] != "paper":
        print(f"execution mode '{ex['mode']}' unsupported by this module (paper only) — halting")
        return

    bk = broker.connect()
    if bk is None:
        api, sec = broker._keys()
        if api and sec:
            # Keys ARE configured, so this scheduled run was expected to trade —
            # a connection/SDK failure must fail the workflow (red run + GitHub
            # email), not silently no-op like the unconfigured case below.
            notify.send_message("⚠️ **PAPER EXECUTOR** — Alpaca keys are set but the broker "
                                "connection failed this run; no orders were checked or placed. "
                                "See the Actions log.", kind="EXECUTE")
            sys.exit(1)
        return  # no keys at all = intentionally unconfigured, clean no-op

    acct = bk.account()
    if acct["trading_blocked"]:
        notify.send_message("⚠️ **PAPER EXECUTOR** — Alpaca reports trading_blocked; skipping run.",
                            kind="EXECUTE")
        return
    if ex["market_hours_only"] and not force and not bk.market_open():
        print("market closed — nothing to do")
        return

    executed = _load(EXECUTED, [])
    state = _load(STATE, {})
    log = []

    # On/after the trial end date, flatten the book once and stop trading —
    # no new buys, no rule-based sells, just a clean liquidation for the tally.
    today = datetime.now().strftime("%Y-%m-%d")
    trial_over = today >= ex["trial_end"]
    if trial_over:
        bought = []
        sold = [] if state.get("flattened") else flatten_pass(bk, ex, state, dry, log)
        if state.get("flattened") and not sold:
            log.append(f"trial ended {ex['trial_end']} — book already flat, idle")
        bought_calls = []
        sold_calls = []
    else:
        bought = buy_pass(bk, cfg, ex, executed, state, dry, log)
        sold = sell_pass(bk, ex, state, dry, log)
        bought_calls = buy_options_pass(bk, cfg, ex, executed, dry, log)
        sold_calls = sell_options_pass(bk, ex, state, dry, log)
    reconcile(bk, log)

    if not dry:
        EXECUTED.write_text(json.dumps(executed, indent=2))
        state["last_run"] = datetime.now().isoformat(timespec="minutes")
        STATE.write_text(json.dumps(state, indent=2))

    # Announce only when something happened (or a guardrail blocked something) —
    # a quiet run stays quiet, same discipline as the rest of the system.
    flattened_now = any(k == "TRIAL_END" for _, k, _ in sold)
    notable = (bought or sold or bought_calls or sold_calls
              or [l for l in log if l.startswith(("SKIP", "RECONCILE"))])
    if notable and not dry:
        acct = bk.account()
        header = ("🏁 **PAPER TRIAL COMPLETE (2026-08-13)** — flattened the book. "
                  if flattened_now else "🤖 **PAPER EXECUTOR** — ")
        lines = [f"{header}equity ${acct['equity']:,.0f}, "
                 f"cash ${acct['cash']:,.0f} (Alpaca paper)"]
        if bought:
            lines.append("**Bought:** " + ", ".join(f"{t} ${f['shares']*f['price']:.0f}" for t, f in bought))
        if bought_calls:
            lines.append("**Bought calls:** " + ", ".join(
                f"{t} ${f['shares']*f['price']*100:.0f}" for t, _, f in bought_calls))
        if sold:
            lines.append("**Sold:** " + ", ".join(f"{t} ({k})" for t, k, _ in sold))
        if sold_calls:
            lines.append("**Sold calls:** " + ", ".join(
                f"{t} ({k})" for t, _, k, _ in sold_calls))
        skips = [l for l in log if l.startswith(("SKIP", "RECONCILE"))]
        if skips:
            lines.append("\n".join(skips))
        if flattened_now:
            lines.append("_Trial over — run `execute.py --report` for the vs-SPY tally, "
                         "then disable the execute cron card. Positions are flat._")
        else:
            lines.append("_Paper trial → 2026-08-13. Kill switch: config.execution.kill_switch. "
                         "Frozen trading rules unchanged — this only executes them._")
        notify.send_message("\n".join(lines), kind="EXECUTE")

    print("\n".join(log) or "nothing to do")
    import os
    if not dry and (bought or sold or bought_calls or sold_calls) and os.environ.get("GITHUB_ACTIONS") != "true":
        try:
            import git_sync
            files = ["actual_trades.json", "executed_orders.json", "execution_state.json"]
            if bought_calls or sold_calls:
                files.append("option_trades.json")
            git_sync.commit_and_push(
                files, f"paper-exec: +{len(bought) + len(bought_calls)} / -{len(sold) + len(sold_calls)}")
        except Exception as e:
            print(f"push skipped: {e}")


if __name__ == "__main__":
    main()
    if notify.had_failures():
        sys.exit(1)
