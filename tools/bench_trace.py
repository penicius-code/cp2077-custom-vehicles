"""Summarise CyberslopVehicleBench trace.csv runs: per gear speed range / mean accel, plateau check.
Usage: python -I -X utf8 scripts/bench_trace.py [trace.csv] [min_top_mps]"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import sys

path = sys.argv[1] if len(sys.argv) > 1 else _os.path.join(GAME_DIR, r"bin\x64\plugins\cyber_engine_tweaks\mods\CyberslopVehicleBench\trace.csv")
min_top = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

runs, cur = [], None
for line in open(path, encoding="utf8", errors="replace"):
    line = line.strip()
    if not line:
        continue
    if line.startswith("# run"):
        cur = {"head": line[6:], "rows": []}
        runs.append(cur)
        continue
    if cur is None:
        continue
    p = line.split(",")
    try:
        t, v = float(p[0]), float(p[1])
    except ValueError:
        continue
    g = int(p[2]) if len(p) > 2 and p[2].strip().lstrip("-").isdigit() else None
    r = float(p[3]) if len(p) > 3 and p[3].strip() else None
    cur["rows"].append((t, v, g, r))

for run in runs:
    rows = run["rows"]
    if not rows:
        continue
    top = max(v for _, v, _, _ in rows)
    if top < min_top:
        continue
    itop = max(range(len(rows)), key=lambda i: rows[i][1])
    print(f"== {run['head']}  top {top:.1f} m/s ({top*3.6:.0f} km/h) at t={rows[itop][0]:.1f}s")
    # speed gained in the 5 s / 10 s before the peak
    for back in (5.0, 10.0):
        prev = [v for t, v, _, _ in rows if t <= rows[itop][0] - back]
        if prev:
            print(f"   gain in last {back:.0f}s before peak: {top - prev[-1]:.2f} m/s")
    # per gear segments up to the peak
    seg = []
    for t, v, g, r in rows[: itop + 1]:
        if not seg or seg[-1]["g"] != g:
            seg.append({"g": g, "t0": t, "v0": v, "t1": t, "v1": v, "rmin": r, "rmax": r})
        s = seg[-1]
        s["t1"], s["v1"] = t, v
        if r is not None:
            s["rmin"] = r if s["rmin"] is None else min(s["rmin"], r)
            s["rmax"] = r if s["rmax"] is None else max(s["rmax"], r)
    for s in seg:
        dt = s["t1"] - s["t0"]
        a = (s["v1"] - s["v0"]) / dt if dt > 0 else 0.0
        print(f"   gear {s['g']}: t {s['t0']:6.2f}-{s['t1']:6.2f}  v {s['v0']:5.1f}-{s['v1']:5.1f} m/s  a {a:5.2f}  rpm {s['rmin']}-{s['rmax']}")
