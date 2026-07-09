"""Alert-rate measurement — observe, don't enforce.

Records when BUY alerts are sent and reports the trailing weekly count
against the CALIBRATION BAND (the rate the thresholds were tuned to produce
naturally: ~2-6/week, calibrated 2026-07-09 against a peak earnings-season
cross-section). Deliberately NO feedback into thresholds and NO cap:
8 genuinely qualified setups should mean 8 alerts; a dead week means 0.
If the observed rate drifts from the band for several weeks, recalibrate
the fixed bars deliberately (consensus.SUPERMAJORITY, earnings_gate bars) —
a human decision, not an automatic one.
"""
import json
import time
from pathlib import Path

STATE_PATH = Path(__file__).parent / "alert_stats.json"

BAND_LOW, BAND_HIGH = 2, 6
WEEK_SECONDS = 7 * 86400


def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"alerts": []}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def record_alert(now=None):
    now = now or time.time()
    state = load_state()
    state.setdefault("alerts", []).append(now)
    # keep ~90 days so weekly.py can show a trend
    state["alerts"] = [ts for ts in state["alerts"] if now - ts < 90 * 86400]
    save_state(state)


def weekly_count(now=None):
    now = now or time.time()
    return sum(1 for ts in load_state().get("alerts", []) if now - ts < WEEK_SECONDS)


def summary(now=None):
    n = weekly_count(now)
    if n < BAND_LOW:
        judge = f"below the {BAND_LOW}-{BAND_HIGH} calibration band (fine in an earnings drought)"
    elif n > BAND_HIGH:
        judge = f"above the {BAND_LOW}-{BAND_HIGH} calibration band (fine if the setups were real)"
    else:
        judge = f"inside the {BAND_LOW}-{BAND_HIGH} calibration band"
    return f"BUY alerts, trailing 7 days: {n} — {judge}. Persistent drift → recalibrate thresholds deliberately."
