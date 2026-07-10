"""Discord trade-log intake — reads a channel via a Discord Bot (polling
Discord's REST API, not a persistent gateway connection, to stay consistent
with this system's scheduled/ephemeral architecture) and turns messages like

    Bought $20 of NVDA at $374
    Sold $20 of NVDA at $400
    Bought 20 dollars of NVDA at a stock price of 374

into entries in actual_trades.json — the "what did I actually do" ledger,
deliberately separate from recommendations.json ("what did the system say
to do"). sell_check.py's stop-loss/take-profit/rebalance checks and
performance.py's comparisons both read this file.

Ticker resolution is deliberately strict: the message must contain the
actual ticker symbol, not a company name (Quinn's call — a misheard company
name silently recording the wrong stock is worse than requiring the ticker).
The bot replies in-channel with exactly what it parsed (or a format-help
message if it looks like an attempted log entry but didn't parse) so a
misparse is caught immediately, not discovered later.

Run: ./venv/bin/python buy_intake.py
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
import yfinance as yf

from notify import load_config
import git_sync

STATE_PATH = Path(__file__).parent / "discord_intake_state.json"
TRADES_PATH = Path(__file__).parent / "actual_trades.json"
API_BASE = "https://discord.com/api/v10"

TRADE_RE = re.compile(
    r"(bought|sold)\s+\$?([\d,]+(?:\.\d+)?)\s*(?:dollars?)?\s+(?:of|worth\s+of)\s+"
    r"([A-Za-z]{1,5})\s+at\s+(?:a\s+stock\s+price\s+of\s+)?\$?([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Committee-verdict intake (2026-07-09): lets Quinn log verdicts from his
# phone instead of verdict.py on the Mac. Same channel, same poll.
#   Verdict AAPL Buy
#   Verdict AAPL Strong Buy entry 305 — margin expansion thesis
#   Verdict TECK Pass
VERDICT_RE = re.compile(
    r"^verdict\s+([A-Za-z]{1,5})\s+(strong\s+buy|buy|hold|avoid|sell|pass)"
    r"(?:\s+entry\s+\$?([\d,]+(?:\.\d+)?))?"
    r"(?:\s*[—–-]+\s*(.+))?\s*$",
    re.IGNORECASE,
)

VERDICT_FORMAT_HELP = (
    "Couldn't parse that as a committee verdict. Format:\n"
    "`Verdict <TICKER> <Strong Buy|Buy|Hold|Avoid|Sell|Pass> [entry <price>] [— note]`\n"
    "e.g. `Verdict AAPL Buy entry 305 — margin expansion thesis`"
)

FORMAT_HELP = (
    "Couldn't parse that as a trade-log entry. Format:\n"
    "`Bought $<amount> of <TICKER> at $<price>` or `Sold $<amount> of <TICKER> at $<price>`\n"
    "e.g. `Bought $20 of NVDA at $374` — needs the actual ticker symbol, not a company name."
)


def load_state():
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {"last_message_id": None}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def load_trades():
    return json.loads(TRADES_PATH.read_text()) if TRADES_PATH.exists() else []


def save_trades(trades):
    TRADES_PATH.write_text(json.dumps(trades, indent=2))


def _headers():
    cfg = load_config()
    token = cfg.get("discord_bot_token")
    if not token:
        raise RuntimeError("Set discord_bot_token in secrets.json first.")
    return {"Authorization": f"Bot {token}"}


def fetch_new_messages(channel_id, after_id):
    params = {"limit": 100}
    if after_id:
        params["after"] = after_id
    resp = requests.get(f"{API_BASE}/channels/{channel_id}/messages", headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    # Discord always returns newest-first regardless of the after/before filter used
    return list(reversed(resp.json()))


def reply(channel_id, content, in_reply_to=None):
    body = {"content": content[:2000]}
    if in_reply_to:
        body["message_reference"] = {"message_id": in_reply_to}
    resp = requests.post(f"{API_BASE}/channels/{channel_id}/messages", headers=_headers(), json=body, timeout=15)
    resp.raise_for_status()


def react(channel_id, message_id, emoji):
    from urllib.parse import quote
    url = f"{API_BASE}/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji)}/@me"
    resp = requests.put(url, headers=_headers(), timeout=15)
    resp.raise_for_status()


def parse_trade(text):
    """Returns (action, amount, ticker, price) or None if it doesn't match."""
    m = TRADE_RE.search(text)
    if not m:
        return None
    action = "BUY" if m.group(1).lower() == "bought" else "SELL"
    amount = float(m.group(2).replace(",", ""))
    ticker = m.group(3).upper()
    price = float(m.group(4).replace(",", ""))
    return action, amount, ticker, price


RECOMMENDATIONS_PATH = Path(__file__).parent / "recommendations.json"


def record_verdict(ticker, rating, entry, note):
    """Append a committee verdict to recommendations.json — the exact same
    shape verdict.py writes, so weekly review and signal_tracker see it."""
    price = float(yf.Ticker(ticker).history(period="5d")["Close"].iloc[-1])
    recs = json.loads(RECOMMENDATIONS_PATH.read_text()) if RECOMMENDATIONS_PATH.exists() else []
    date = datetime.now().strftime("%Y-%m-%d")
    recs.append({"date": date, "ticker": ticker, "kind": "committee_verdict",
                 "rating": rating, "price_at_verdict": round(price, 2),
                 "suggested_entry": entry, "note": note})
    RECOMMENDATIONS_PATH.write_text(json.dumps(recs, indent=2))
    try:
        import obsidian
        obsidian.record_verdict(ticker, rating, price, entry, note, date)
    except Exception as e:
        print(f"Obsidian verdict mirror failed (continuing): {e}")
    return price, date


def validate_ticker(ticker):
    try:
        h = yf.Ticker(ticker).history(period="5d")
        return not h.empty
    except Exception:
        return False


def main():
    cfg = load_config()
    channel_id = cfg.get("discord_buy_log_channel_id")
    if not channel_id:
        print("discord_buy_log_channel_id not set — nothing to poll.")
        return

    state = load_state()
    try:
        messages = fetch_new_messages(channel_id, state.get("last_message_id"))
    except Exception as e:
        print(f"Failed to fetch messages: {e}")
        return

    if not messages:
        print("No new messages.")
        return

    trades = load_trades()
    changed = False

    for msg in messages:
        state["last_message_id"] = msg["id"]  # advance regardless of outcome — never reprocess
        if msg.get("author", {}).get("bot"):
            continue  # ignore the bot's own replies
        text = msg.get("content", "")

        # Committee verdicts: any message starting with "verdict" is an attempt
        if text.lower().lstrip().startswith("verdict"):
            vm = VERDICT_RE.match(text.strip())
            if not vm:
                try:
                    reply(channel_id, VERDICT_FORMAT_HELP, in_reply_to=msg["id"])
                    react(channel_id, msg["id"], "❌")
                except Exception as e:
                    print(f"Failed to reply with verdict format help: {e}")
                continue
            vt = vm.group(1).upper()
            rating = " ".join(w.capitalize() for w in vm.group(2).split())
            entry = float(vm.group(3).replace(",", "")) if vm.group(3) else None
            note = vm.group(4)
            if not validate_ticker(vt):
                try:
                    reply(channel_id, f"❌ `{vt}` doesn't look like a real ticker — double-check and resend.",
                          in_reply_to=msg["id"])
                except Exception as e:
                    print(f"Failed to reply with ticker-invalid notice: {e}")
                continue
            try:
                price, date = record_verdict(vt, rating, entry, note)
            except Exception as e:
                print(f"Failed to record verdict for {vt}: {e}")
                continue
            changed = True
            try:
                reply(channel_id, f"✅ Verdict recorded: **{vt} {rating}** @ ${price:,.2f} on {date}"
                                  + (f", suggested entry ${entry:,.2f}" if entry else "")
                                  + (f" — {note}" if note else "")
                                  + ". Tracked by the weekly review and the machine-vs-committee comparison.",
                      in_reply_to=msg["id"])
                react(channel_id, msg["id"], "✅")
            except Exception as e:
                print(f"Failed to reply with verdict confirmation: {e}")
            print(f"Recorded verdict: {vt} {rating}")
            continue

        if "bought" not in text.lower() and "sold" not in text.lower():
            continue  # not an attempted trade-log entry — ignore silently, don't spam replies to chat

        parsed = parse_trade(text)
        if not parsed:
            try:
                reply(channel_id, FORMAT_HELP, in_reply_to=msg["id"])
                react(channel_id, msg["id"], "❌")
            except Exception as e:
                print(f"Failed to reply with format help: {e}")
            continue

        action, amount, ticker, price = parsed
        if not validate_ticker(ticker):
            try:
                reply(channel_id, f"❌ `{ticker}` doesn't look like a real ticker — double-check and resend.",
                      in_reply_to=msg["id"])
            except Exception as e:
                print(f"Failed to reply with ticker-invalid notice: {e}")
            continue

        shares = amount / price
        date = datetime.now().strftime("%Y-%m-%d")
        note = f"Logged via Discord: {action} ${amount:,.2f} @ ${price:,.2f} (~{shares:.4f} shares)"
        trades.append({
            "date": date, "ticker": ticker, "action": action,
            "amount": amount, "price": price, "shares": shares, "note": note,
        })
        changed = True
        verb = "Bought" if action == "BUY" else "Sold"
        try:
            reply(channel_id, f"✅ Recorded: **{verb} {ticker}** — ${amount:,.2f} @ ${price:,.2f} "
                              f"(~{shares:.4f} shares) on {date}. Now tracked by sell_check.py "
                              f"(if it's an open position) and performance.py's actual-trades view.",
                  in_reply_to=msg["id"])
            react(channel_id, msg["id"], "✅")
        except Exception as e:
            print(f"Failed to reply with confirmation: {e}")
        try:
            import obsidian
            obsidian.log_actual_trade(action, ticker, amount, price, shares, date=date, note=note)
        except Exception as e:
            print(f"Obsidian mirror failed (continuing): {e}")
        print(f"Recorded: {action} {ticker} ${amount:,.2f} @ ${price:,.2f}")

    save_state(state)
    if changed:
        save_trades(trades)
        git_sync.commit_and_push(["actual_trades.json", "discord_intake_state.json",
                                  "recommendations.json"],
                                  "buy_intake: record Discord-logged trade(s)/verdict(s)")
    else:
        git_sync.commit_and_push(["discord_intake_state.json"], "buy_intake: advance message cursor")


if __name__ == "__main__":
    main()
