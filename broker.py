"""Alpaca brokerage connector — PAPER trading only (for now).

Thin wrapper over alpaca-py so the executor (execute.py) never touches the SDK
directly. Everything here is deliberately conservative:

  - **paper=True is hard-wired.** There is no code path in this file that can
    reach a live-money account. Going live later is a deliberate, separate
    change (a live client + live keys + an explicit config opt-in), not a flag
    someone flips by accident.
  - Credentials come from the environment (ALPACA_API_KEY / ALPACA_SECRET_KEY —
    GitHub Actions secrets) with a secrets.json fallback for local runs. Keys
    are never logged.
  - Missing library or missing keys degrade gracefully: connect() returns None
    with a clear message instead of crashing the caller. The rest of the
    stock-monitor system must never break because the broker is unconfigured.

Fractional dollar-notional market orders require time-in-force DAY and only fill
during regular market hours — which is exactly when the executor is scheduled to
run, so that constraint costs nothing here.
"""
import json
import os
import time
from pathlib import Path

SECRETS_PATH = Path(__file__).parent / "secrets.json"
PAPER_BASE = "https://paper-api.alpaca.markets"


def _keys():
    api = os.environ.get("ALPACA_API_KEY")
    sec = os.environ.get("ALPACA_SECRET_KEY")
    if (not api or not sec) and SECRETS_PATH.exists():
        try:
            s = json.loads(SECRETS_PATH.read_text())
            api = api or s.get("alpaca_api_key")
            sec = sec or s.get("alpaca_secret_key")
        except Exception:
            pass
    return api, sec


class Broker:
    """Wraps a paper TradingClient. Construct via broker.connect()."""

    def __init__(self, client):
        self._c = client  # an alpaca TradingClient (paper)

    # ── read ──
    def account(self):
        a = self._c.get_account()
        return {"cash": float(a.cash), "equity": float(a.equity),
                "buying_power": float(a.buying_power),
                "status": str(a.status), "trading_blocked": bool(a.trading_blocked)}

    def positions(self):
        """{'AAPL': {'shares': float, 'avg_cost': float, 'market_value': float,
        'unrealized_pl': float}} for every open paper position."""
        out = {}
        for p in self._c.get_all_positions():
            out[p.symbol] = {"shares": float(p.qty), "avg_cost": float(p.avg_entry_price),
                             "market_value": float(p.market_value),
                             "unrealized_pl": float(p.unrealized_pl)}
        return out

    def market_open(self):
        try:
            return bool(self._c.get_clock().is_open)
        except Exception:
            return False

    # ── write (paper) ──
    def buy_notional(self, symbol, usd, poll_s=12):
        """Submit a DAY market BUY for `usd` dollars (fractional). Polls briefly
        for the fill and returns {'filled': bool, 'shares', 'price', 'order_id'}.
        A market order in regular hours fills in well under a second; if it
        hasn't filled by poll_s the caller records it as pending and reconciles
        on the next run rather than double-submitting."""
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        req = MarketOrderRequest(symbol=symbol, notional=round(usd, 2),
                                 side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
        order = self._c.submit_order(req)
        return self._await_fill(order.id, poll_s)

    def buy_option(self, occ_symbol, qty=1, poll_s=12):
        """Submit a DAY market BUY for `qty` option contracts (OCC symbol, e.g.
        'QQQ260918C00690000'). Options don't support notional orders — always
        whole contracts. Same fill-dict shape as buy_notional; 'shares' here
        means contracts, 'price' is premium per contract (not x100)."""
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        req = MarketOrderRequest(symbol=occ_symbol, qty=qty,
                                 side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
        order = self._c.submit_order(req)
        return self._await_fill(order.id, poll_s)

    def close(self, symbol, poll_s=12):
        """Liquidate the ENTIRE paper position in `symbol` at market. Returns
        the same fill dict shape as buy_notional (shares/price of the close)."""
        order = self._c.close_position(symbol)
        return self._await_fill(order.id, poll_s)

    def _await_fill(self, order_id, poll_s):
        deadline = poll_s
        waited = 0.0
        while waited < deadline:
            o = self._c.get_order_by_id(order_id)
            status = str(o.status)
            if o.filled_at and o.filled_avg_price and o.filled_qty:
                return {"filled": True, "order_id": str(order_id),
                        "shares": float(o.filled_qty), "price": float(o.filled_avg_price)}
            if status in ("OrderStatus.CANCELED", "OrderStatus.REJECTED",
                          "OrderStatus.EXPIRED", "canceled", "rejected", "expired"):
                return {"filled": False, "order_id": str(order_id), "status": status}
            time.sleep(1.0)
            waited += 1.0
        return {"filled": False, "order_id": str(order_id), "status": "pending"}


def connect():
    """Return a paper Broker, or None with a printed reason (never raises).
    None means 'broker unavailable this run' — the executor logs it and exits
    cleanly, exactly like a missing webhook elsewhere in the system."""
    api, sec = _keys()
    if not api or not sec:
        print("broker: no Alpaca keys (set ALPACA_API_KEY/ALPACA_SECRET_KEY "
              "or secrets.json) — skipping execution this run")
        return None
    try:
        from alpaca.trading.client import TradingClient
    except Exception:
        print("broker: alpaca-py not installed (pip install alpaca-py) — skipping")
        return None
    try:
        client = TradingClient(api, sec, paper=True)  # PAPER — hard-wired
        client.get_account()  # fail fast on bad keys
        return Broker(client)
    except Exception as e:
        print(f"broker: could not connect to Alpaca paper API ({e}) — skipping")
        return None
