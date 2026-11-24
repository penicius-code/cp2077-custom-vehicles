"""Dump every CVOO module's tuning numbers (all multipliers 1.0) to JSON + a text table.
Usage: python -I -X utf8 cvoo_dump.py <CVOO modules dir> <out json>"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import json, os, re, sys

mods = sys.argv[1]
out = sys.argv[2]

num = r"(-?\d+(?:\.\d+)?)"
rows = []
for fn in sorted(os.listdir(mods)):
    if not fn.endswith(".lua"):
        continue
    text = open(os.path.join(mods, fn), encoding="utf-8", errors="replace").read()
    if len(text.strip()) == 0:
        continue
    code = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("--"):
            continue
        code.append(ln.split("--")[0])
    code = "\n".join(code)

    def one(name):
        m = re.search(r"^\s*%s\s*=\s*%s" % (name, num), code, re.M)
        return float(m.group(1)) if m else None

    desc = re.search(r'description\s*=\s*"([^"]*)"', text)
    vname = re.search(r'^\s*vehicleName\s*=\s*"([^"]*)"', code, re.M)
    fmap = re.search(r"WheelsFrictionMapToSet\s*=\s*\[\[([^\]]*)\]\]", code)
    gears = {}
    for kind in ("gearsTorqueMult", "gearsMinSpeed", "gearsMaxSpeed", "gearsMinRPM", "gearsMaxRPM"):
        for m in re.finditer(r"^\s*%s\[(\d+)\]\s*=\s*%s" % (kind, num), code, re.M):
            gears.setdefault(int(m.group(1)), {})[kind] = float(m.group(2))
    ng = re.search(r"AmountOfGears\s*=\s*(\d+)", code)
    targets = re.findall(r'setVehicleSettings\("([^"]+)"', code)
    bike = bool(re.search(r"setVehicleSettings\([^)]*,\s*true\s*\)", code)) or "BikeDrivingFrictionMap" in code
    row = dict(
        file=fn,
        description=desc.group(1) if desc else None,
        vehicle=("Vehicle.v_" + vname.group(1)) if vname else None,
        bike=bike,
        torque=one("MaxTorque"),
        mass=one("TotalMass"),
        minRPM=one("MinRPM"), maxRPM=one("MaxRPM"),
        drag=one("airResistanceFactor"),
        brakeFrictionFactor=one("BrakingFrictionFactor"),
        frontBrake=one("MaxBrakingTorqueFront"), rearBrake=one("MaxBrakingTorqueRear"),
        friction=fmap.group(1) if fmap else None,
        nGears=int(ng.group(1)) if ng else None,
        gears={str(k): v for k, v in sorted(gears.items())},
        n_targets=len(targets),
        targets=targets,                 # all of them: CyberslopCustomVehicles 1.2 rewires each one's live records
    )
    rows.append(row)

json.dump(rows, open(out, "w", encoding="utf-8"), indent=1)
print(len(rows), "modules")
for r in rows:
    g = r["gears"]
    top = max((v.get("gearsMaxSpeed", 0) for v in g.values()), default=0)
    print("%-44s %-8s T=%-7s m=%-6s drag=%-5s topgear=%-6s kmh=%-5s n=%s" % (
        r["file"][:44], "BIKE" if r["bike"] else "car", r["torque"], r["mass"], r["drag"], top, round(top * 3.6), len(g)))
