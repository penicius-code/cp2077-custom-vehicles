"""Check work\\realism_plan.json: every vehicle within 5 % of its real 0-100, 10 % of 0-200, reaches 97 % of its real
top speed, and gear torque multipliers never rise by more than 5 % from gear 2 upward. Usage: python -I -X utf8 realism_check.py"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import json

d = json.load(open(_os.path.join(WORK, r"realism_plan.json")))
bad = mono = 0
for r in d["report"]:
    off = []
    if r["g100"] is None or abs(r["g100"] - r["real100"]) / r["real100"] > 0.05:
        off.append("0-100 %s vs %.1f" % (r["g100"] and round(r["g100"], 2), r["real100"]))
    if r["real200"] and (r["g200"] is None or abs(r["g200"] - r["real200"]) / r["real200"] > 0.10):
        off.append("0-200 %s vs %.1f" % (r["g200"] and round(r["g200"], 1), r["real200"]))
    if r["reach"] < 0.97 * r["realtop"]:
        off.append("top %.0f vs %.0f" % (r["reach"], r["realtop"]))
    if off:
        bad += 1
        print("OFF", r["name"], "; ".join(off))
for e in d["entries"] + d["bikes"]:
    tms = [g["tm"] for g in e["gears"]]
    if any(tms[i + 1] > tms[i] * 1.05 for i in range(1, len(tms) - 1)):
        mono += 1
        print("NON-MONOTONIC", e["name"], tms)
drags = [e["drag"] for e in d["entries"] + d["bikes"]]
print("%d vehicles, %d off target, %d non-monotonic; game drag factor %.3f-%.3f" % (len(d["report"]), bad, mono, min(drags), max(drags)))
