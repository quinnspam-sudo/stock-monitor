"""Discord buy-log intake — reads a channel via a Discord Bot (polling
Discord's REST API, not a persistent gateway connection, to stay consistent
with this system's scheduled/ephemeral architecture) and turns messages like

    Bought $20 of NVDA at $374
    Bought 20 dollars of NVDA at a stock price of 374

into recorded verdicts, same as `verdict.py add` would, so a Discord-logged
buy is automatically visible to sell_check.py's stop-loss/take-profit/
rebalance checks, weekly.py's review, and verdict.py review — no separate
tracking system.

Ticker resolution is deliberately strict: the message must contain the
actual ticker symbol, not a company name (Quinn's call — a misheard company
name silently recording the wrong stock is worse than requiring the ticker).
The bot replies in-channel with exactly what it parsed (or a format-help
message if it looks like an attempted log entry but didn't parse) so a
misparse is caught immediately, not discovered later in a payload.

Run: ./venv/bin/python buy_intake.py
"""
import json
import re
import sys
from pathlib import Path

import requests
import yfinance as yf

from notify import load_config
import git_sync
from verdict import load as load_verdicts, save as save_verdicts

STATE_PATH = Path(__file__).parent / "discord_intake_state.json"
API_BASE = "https://discord.com/api/v10"

BUY_RE = re.compile(
    r"bought\s+\$?([\d,]+(?:\.\d+)?)\s*(?:dollars?)?\s+(?:of|worth\s+of)\s+"
    r"([A-Za-z]{1,5})\s+at\s+(?:a\s+stock\s+price\s+of\s+)?\$?([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)

FORMAT_HELP = (
    "Couldn't parse that as a buy-log entry. Format:\n"
    "`Bought $<amount> of <TICKER> at $<price>`\n"
    "e.g. `Bought $20 of NVDA at $374` — needs the actual ticker symbol, not a company name."
)


def load_state():
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {"last_message_id": None}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


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


def parse_buy(text):
    """Returns (amount, ticker, price) or None if it doesn't match the format."""
    m = BUY_RE.search(text)
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    ticker = m.group(2).upper()
    price = float(m.group(3).replace(",", ""))
    return amount, ticker, price


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

    verdicts = load_verdicts()
    changed = False

    for msg in messages:
        state["last_message_id"] = msg["id"]  # advance regardless of outcome — never reprocess
        if msg.get("author", {}).get("bot"):
            continue  # ignore the bot's own replies
        text = msg.get("content", "")
        if "bought" not in text.lower():
            continue  # not an attempted buy-log entry — ignore silently, don't spam replies to chat

        parsed = parse_buy(text)
        if not parsed:
            try:
                reply(channel_id, FORMAT_HELP, in_reply_to=msg["id"])
                react(channel_id, msg["id"], "❌")  # ❌
            except Exception as e:
                print(f"Failed to reply with format help: {e}")
            continue

        amount, ticker, price = parsed
        if not validate_ticker(ticker):
            try:
                reply(channel_id, f"❌ `{ticker}` doesn't look like a real ticker — double-check and resend.",
                      in_reply_to=msg["id"])
            except Exception as e:
                print(f"Failed to reply with ticker-invalid notice: {e}")
            continue

        shares = amount / price
        from datetime import datetime
        date = datetime.now().strftime("%Y-%m-%d")
        verdicts.append({
            "date": date, "ticker": ticker, "rating": "Buy (self-reported via Discord)",
            "price_at_verdict": price, "suggested_entry": price,
            "note": f"Logged via Discord buy-log: ${amount:,.2f} @ ${price:,.2f} (~{shares:.4f} shares)",
        })
        changed = True
        try:
            reply(channel_id, f"✅ Recorded: **{ticker}** — ${amount:,.2f} @ ${price:,.2f} "
                              f"(~{shares:.4f} shares) on {date}. Now tracked by sell_check.py "
                              f"(stop-loss/take-profit/rebalance) and weekly.py's review.",
                  in_reply_to=msg["id"])
            react(channel_id, msg["id"], "✅")
        except Exception as e:
            print(f"Failed to reply with confirmation: {e}")
        print(f"Recorded: {ticker} ${amount:,.2f} @ ${price:,.2f}")

    save_state(state)
    if changed:
        save_verdicts(verdicts)
        git_sync.commit_and_push(["verdicts.json", "discord_intake_state.json"],
                                  "buy_intake: record Discord-logged buy(s)")
    else:
        git_sync.commit_and_push(["discord_intake_state.json"], "buy_intake: advance message cursor")


if __name__ == "__main__":
    main()
