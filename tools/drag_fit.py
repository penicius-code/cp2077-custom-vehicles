"""Calibrate the game model's drag scale D: for each CVOO vehicle, the largest D at which it still reaches 97 % of its
top-gear cap (assumption: CVOO-tuned vehicles reach their top gear's max speed). Usage: python -I -X utf8 drag_fit.py"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import json, statistics, sys
sys.path.insert(0, _HERE)
from vehicle_model import sim_game

S = WORK
rows = [x for x in json.load(open(S + r"\vehicle_audit.json")) if x.get("K_med")]
res = {False: [], True: []}
for x in rows:
    cap = max(g[1] for g in x["gears"])
    lo, hi = 0.0, 5.0
    for _ in range(30):
        mid = (lo + hi) / 2
        s = sim_game(x["torque"], x["gears"], x["phys_kg"], x["drag"] or 2.0, K=x["K_med"], D=mid, horizon=60, tmax=120)
        if s["top"] >= 0.97 * cap:
            lo = mid
        else:
            hi = mid
    x["Dmax"] = lo
    res[x["bike"]].append(lo)
for k, v in res.items():
    print("%s: D_max median %.3f, quartiles %s" % ("bikes" if k else "cars", statistics.median(v), [round(q, 3) for q in statistics.quantiles(v, n=4)]))
json.dump({"cars": statistics.median(res[False]), "bikes": statistics.median(res[True])}, open(S + r"\drag_fit.json", "w"))
