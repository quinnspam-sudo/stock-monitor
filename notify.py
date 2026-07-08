"""Discord notification module — posts alerts via webhook."""
import json
import os
import requests
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
SECRETS_PATH = Path(__file__).parent / "secrets.json"

GREEN = 0x2ECC71
YELLOW = 0xF1C40F
GREY = 0x95A5A6

# Populated whenever a Discord post fails. Callers often catch send_alert/
# send_message exceptions per-item so one bad ticker doesn't abort a whole
# run — but that means failures can go completely unnoticed run after run
# (e.g. a revoked webhook). Scripts check had_failures() at exit and fail
# the process so CI shows red and GitHub's default failure email fires,
# even though the alerting channel itself is what broke.
FAILURES = []


def had_failures():
    return bool(FAILURES)


def load_config():
    """Merge config.json with secrets.json (gitignored) and env var overrides.

    Two channels, two webhooks:
      - discord_webhook_url          — BUY-only channel (send_alert's target)
      - discord_updates_webhook_url  — everything else: pulse/close/ipo/weekly/
        backtest/payload-ready notices (send_message's target)
    Each resolves env var > secrets.json > legacy config.json key, same
    precedence as before. If discord_updates_webhook_url isn't set, updates
    fall back to the BUY webhook (single-channel setups keep working).
    """
    cfg = json.loads(CONFIG_PATH.read_text())
    if SECRETS_PATH.exists():
        cfg.update(json.loads(SECRETS_PATH.read_text()))
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        cfg["discord_webhook_url"] = os.environ["DISCORD_WEBHOOK_URL"]
    if os.environ.get("DISCORD_UPDATES_WEBHOOK_URL"):
        cfg["discord_updates_webhook_url"] = os.environ["DISCORD_UPDATES_WEBHOOK_URL"]
    cfg.setdefault("discord_updates_webhook_url", cfg.get("discord_webhook_url"))
    return cfg


def send_alert(ticker, score, action, price, details, webhook_url=None):
    """Post a formatted alert embed to the Discord channel."""
    cfg = load_config()
    url = webhook_url or cfg["discord_webhook_url"]
    if "PASTE_YOUR" in url:
        raise RuntimeError(
            "Set discord_webhook_url in config.json first. "
            "Discord: Server Settings > Integrations > Webhooks > New Webhook > Copy URL"
        )
    color = GREEN if action == "BUY" else YELLOW if action == "WATCH" else GREY
    import obsidian
    obsidian.log_ping(action, f"**{ticker}** score {score}/100 at ${price:,.2f} — "
                      + "; ".join(f"{k}: {v}" for k, v in details.items()))
    embed = {
        "title": f"{action} ALERT — {ticker}",
        "description": f"**Score: {score}/100** at ${price:,.2f}",
        "color": color,
        "fields": [{"name": k, "value": str(v), "inline": True} for k, v in details.items()],
        "footer": {"text": "stock-monitor · not financial advice · verify before trading"},
    }
    try:
        # "content": "@here" alongside the embed — a mention bypasses a
        # channel's "Only @Mentions" notification setting, which otherwise
        # silently suppresses pings for every alert without ever failing or
        # showing up as an error (confirmed live: alerts were posting fine,
        # Quinn just never got notified because the channel wasn't set to
        # "All Messages"). This makes real notification delivery not depend
        # on every device having Discord settings configured correctly.
        resp = requests.post(url, json={"content": "@here", "embeds": [embed]}, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        FAILURES.append(f"send_alert({ticker}): {e}")
        raise


def send_message(text, webhook_url=None, kind="INFO", mention=False):
    """Post a plain text message — always targets the updates channel (see
    load_config), which is meant to be checked at leisure, not pinged.
    Only send_alert's BUY channel pings via @here. Pass mention=True to
    override for a specific updates message that's unusually urgent."""
    import obsidian
    obsidian.log_ping(kind, text.replace("\n", " · "))
    if mention:
        text = "@here " + text
    cfg = load_config()
    # Discord hard limit is 2000 chars — send in chunks on line boundaries
    if len(text) > 1900:
        chunk, chunks = "", []
        for line in text.split("\n"):
            if len(chunk) + len(line) > 1900:
                chunks.append(chunk)
                chunk = ""
            chunk += line + "\n"
        chunks.append(chunk)
        for c in chunks:
            send_message_raw(c, webhook_url)
        return
    send_message_raw(text, webhook_url)


def send_message_raw(text, webhook_url=None):
    cfg = load_config()
    url = webhook_url or cfg["discord_updates_webhook_url"]
    if "PASTE_YOUR" in url:
        raise RuntimeError("Set discord_webhook_url in config.json first.")
    try:
        resp = requests.post(url, json={"content": text[:2000]}, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        FAILURES.append(f"send_message: {e}")
        raise


if __name__ == "__main__":
    send_message("✅ stock-monitor webhook test — Discord notifications are working.")
    print("Test message sent.")
