"""Fit the game drivetrain constants from CyberslopVehicleBench 1.1 runs.
Model: a = K * T * tm_gear / m  -  D * airResistanceFactor * v^2 / m   (true m/s, per gear the bench trace reports)
Reads the bench log (chain lines: torque, gear tm per index, drag, mass) and trace.csv (t, v, gear, rpm).
Samples: central differences over 0.5 s inside one gear, skipping 0.35 s after each gear change, a > 0 phases only
(up to the run's peak speed), launch gear skipped when its rpm runs ahead of speed (wheelspin).
Usage: python -I -X utf8 scripts/bench_fit.py [--exclude-gear1 rec,...]"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import re, sys, math

MODS = _os.path.join(GAME_DIR, r"bin\x64\plugins\cyber_engine_tweaks\mods\CyberslopVehicleBench")
LOG = MODS + r"\CyberslopVehicleBench.log"
TRACE = MODS + r"\trace.csv"

excl1 = set()
if "--exclude-gear1" in sys.argv:
    excl1 = set(sys.argv[sys.argv.index("--exclude-gear1") + 1].split(","))

# ---- chains: latest per record
chains = {}
for line in open(LOG, encoding="utf8", errors="replace"):
    m = re.search(r"chain (Vehicle\.\S+) \| engine (\S+) \| torque ([\d.]+) .*?\| gears (.*?) \| drive\((\w+)\) \S+ \| drag ([\d.]+) \| mass ([\d.]+)", line)
    if not m:
        continue
    rec, eng, T, gears, kind, drag, mass = m.groups()
    tms = {}
    for gm in re.finditer(r"(\d+):\S+?\[([-\d.]+)-([-\d.]+) x([\d.]+)\]", gears):
        tms[int(gm.group(1))] = (float(gm.group(2)), float(gm.group(3)), float(gm.group(4)))
    chains[rec] = dict(engine=eng, T=float(T), tm=tms, bike=(kind == "bike"), drag=float(drag), m=float(mass))

# ---- traces
runs, cur = [], None
for line in open(TRACE, encoding="utf8", errors="replace"):
    line = line.strip()
    if line.startswith("# run"):
        rec = line.split()[-1]
        cur = dict(rec=rec, rows=[])
        runs.append(cur)
        continue
    if cur is None or not line:
        continue
    p = line.split(",")
    try:
        cur["rows"].append((float(p[0]), float(p[1]), int(p[2]) if p[2] else None, float(p[3]) if p[3] else None))
    except (ValueError, IndexError):
        pass

samples = {False: [], True: []}
for run in runs:
    c = chains.get(run["rec"])
    rows = run["rows"]
    if c is None or len(rows) < 10:
        continue
    itop = max(range(len(rows)), key=lambda i: rows[i][1])
    if rows[itop][1] < 25:
        continue
    last_change = -1e9
    for i in range(2, itop - 1):
        t, v, g, r = rows[i]
        if g != rows[i - 1][2]:
            last_change = t
        if g is None or g < 1 or g not in c["tm"]:
            continue
        if t - last_change < 0.35 + 0.25:
            continue
        a_ = rows[i - 2], rows[i + 1]
        if a_[0][2] != g or a_[1][2] != g:
            continue
        dt = a_[1][0] - a_[0][0]
        if dt <= 0:
            continue
        acc = (a_[1][1] - a_[0][1]) / dt
        if g == 1 and run["rec"] in excl1:
            continue
        x = c["T"] * c["tm"][g][2] / c["m"]
        y = c["drag"] * v * v / c["m"]
        samples[c["bike"]].append((acc, x, y, run["rec"], g, v))


def lsq(S):
    # acc = K x - D y  -> normal equations
    sxx = sum(s[1] * s[1] for s in S); sxy = sum(s[1] * s[2] for s in S); syy = sum(s[2] * s[2] for s in S)
    sax = sum(s[0] * s[1] for s in S); say = sum(s[0] * s[2] for s in S)
    det = sxx * syy - sxy * sxy
    K = (sax * syy - say * sxy) / det
    D = -(sxx * say - sxy * sax) / det
    return K, D

for bike in (False, True):
    S = samples[bike]
    if len(S) < 4:
        print("bikes" if bike else "cars", "too few samples", len(S))
        continue
    K, D = lsq(S)
    res = [s[0] - (K * s[1] - D * s[2]) for s in S]
    rms = math.sqrt(sum(e * e for e in res) / len(res))
    print("%s: K = %.2f  D = %.3f  (n=%d, rms %.2f m/s2)" % ("bikes" if bike else "cars", K, D, len(S), rms))
    by = {}
    for s, e in zip(S, res):
        by.setdefault((s[3], s[4]), []).append((e, s[5], s[0]))
    for (rec, g), L in sorted(by.items()):
        print("   %-45s gear %d  v %5.1f-%5.1f  a %5.2f  resid %+5.2f" % (rec, g, min(l[1] for l in L), max(l[1] for l in L),
              sum(l[2] for l in L) / len(L), sum(l[0] for l in L) / len(L)))
