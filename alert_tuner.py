"""Alert-frequency tuner — feedback controller targeting 2-5 BUY alerts/week.

Fixed thresholds can't hit a target alert rate: the same bars that emit 8
alerts in peak earnings season emit zero in a drought. This module keeps a
single strictness dial (0-100, persisted in tuner_state.json) and adjusts
it once per calendar day based on the trailing 7-day BUY-alert count:
fewer than TARGET_MIN → ease one step; more than TARGET_MAX → tighten.

The dial maps ONLY onto conviction-margin knobs:
  strictness   0            50           100
  supermajority 60%   ...   70%    ...   80%   (consensus vote fraction)
  positivity    60    ...   67     ...   75    (earnings positivity bar)
  beat streak   2     ...   2      ...   3     (of last 4 quarters)

NON-NEGOTIABLE at any dial setting (these never loosen):
  - earnings within 10 business days (Quinn's explicit buy rule)
  - hard vetoes (F-Score<=3, revisions<-2%, 6-mo momentum<-10%)
  - market regime gate (SPY>50d & 200d SMA, VIX<28)
  - factor conviction HIGH/MEDIUM, momentum alert threshold

A hard weekly cap (TARGET_MAX) is enforced at send time regardless of how
many names qualify — overflow goes to the updates channel, ranked.

The 2/week floor is aspirational: in an earnings drought there may be zero
gate-eligible names at the loosest setting, and the right answer is silence.
"""
import json
import time
from datetime import datetime
from pathlib import Path

STATE_PATH = Path(__file__).parent / "tuner_state.json"

TARGET_MIN = 2
TARGET_MAX = 5   # also the hard weekly send cap
STEP = 10        # dial movement per daily adjustment
DEFAULT_STRICTNESS = 60

WEEK_SECONDS = 7 * 86400


def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"strictness": DEFAULT_STRICTNESS, "last_adjust_day": "", "alerts": []}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def params(strictness):
    """Map the dial onto the adjustable thresholds."""
    s = max(0, min(100, strictness)) / 100
    return {
        "supermajority": round(0.60 + s * 0.20, 3),   # 60% .. 80%
        "min_positivity": round(60 + s * 15),          # 60 .. 75
        "min_beats": 3 if s >= 0.75 else 2,            # of last 4
    }


def weekly_alert_count(state, now=None):
    now = now or time.time()
    return sum(1 for ts in state.get("alerts", []) if now - ts < WEEK_SECONDS)


def record_alert(state, now=None):
    now = now or time.time()
    state.setdefault("alerts", []).append(now)
    state["alerts"] = [ts for ts in state["alerts"] if now - ts < 2 * WEEK_SECONDS]


def adjust_daily(state, now=None):
    """Once per calendar day, nudge the dial toward the 2-5/week band.
    Returns a human-readable adjustment note or None if no change."""
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("last_adjust_day") == today:
        return None
    state["last_adjust_day"] = today
    count = weekly_alert_count(state, now)
    old = state.get("strictness", DEFAULT_STRICTNESS)
    if count < TARGET_MIN and old > 0:
        state["strictness"] = max(0, old - STEP)
    elif count > TARGET_MAX and old < 100:
        state["strictness"] = min(100, old + STEP)
    else:
        return None
    p = params(state["strictness"])
    return (f"alert tuner: {count} alert(s) in trailing 7d (target {TARGET_MIN}-{TARGET_MAX}) — "
            f"strictness {old} → {state['strictness']} "
            f"(supermajority {p['supermajority']:.0%}, positivity ≥{p['min_positivity']}, "
            f"beats ≥{p['min_beats']}/4)")


def gate_pass(gate, p):
    """Re-judge the earnings gate under tuned thresholds. The 10-business-day
    window and >=3-signals requirements are fixed; only the conviction margins
    move with the dial. Returns (ok, reasons)."""
    gate = gate or {}
    reasons = []
    if not gate.get("in_window"):
        reasons.append("earnings not within 10 business days")
    pos = gate.get("positivity")
    signals = gate.get("signals") or {}
    if sum(1 for v in signals.values() if v is not None) < 3:
        reasons.append("fewer than 3 positivity signals computable")
    if pos is None or pos < p["min_positivity"]:
        reasons.append(f"positivity {pos} below tuned bar {p['min_positivity']}")
    beats, beats_n = gate.get("beats"), gate.get("beats_n") or 0
    need = min(p["min_beats"], beats_n) if beats_n else p["min_beats"]
    if not beats_n or (beats or 0) < need:
        reasons.append(f"beat streak {beats}/{beats_n} below tuned bar {p['min_beats']}/4")
    return (not reasons), reasons
