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


def load_config():
    """Merge config.json with secrets.json (gitignored) and env var overrides.

    Webhook URL resolution order: DISCORD_WEBHOOK_URL env var > secrets.json >
    legacy discord_webhook_url in config.json (for back-compat with older setups).
    """
    cfg = json.loads(CONFIG_PATH.read_text())
    if SECRETS_PATH.exists():
        cfg.update(json.loads(SECRETS_PATH.read_text()))
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        cfg["discord_webhook_url"] = os.environ["DISCORD_WEBHOOK_URL"]
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
    resp = requests.post(url, json={"embeds": [embed]}, timeout=15)
    resp.raise_for_status()


def send_message(text, webhook_url=None, kind="INFO"):
    """Post a plain text message (used for daily summaries / test)."""
    import obsidian
    obsidian.log_ping(kind, text.replace("\n", " · "))
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
    url = webhook_url or cfg["discord_webhook_url"]
    if "PASTE_YOUR" in url:
        raise RuntimeError("Set discord_webhook_url in config.json first.")
    resp = requests.post(url, json={"content": text[:2000]}, timeout=15)
    resp.raise_for_status()


if __name__ == "__main__":
    send_message("✅ stock-monitor webhook test — Discord notifications are working.")
    print("Test message sent.")
