"""Dump the engine / bike drive model numbers of every Arch V4 bike (r6\\tweaks\\ArchV4_*.tweak) to JSON.
Usage: python -I -X utf8 archv4_dump.py <tweaks dir> <out json>"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import glob, json, os, re, sys

tdir, out = sys.argv[1], sys.argv[2]
res = []
for fp in sorted(glob.glob(os.path.join(tdir, "ArchV4_*.tweak"))):
    text = open(fp, encoding="utf-8", errors="replace").read()
    name = os.path.basename(fp)
    head = re.search(r"^([a-z0-9_]+)\s*:\s*v_sportbike2_arch", text, re.M)
    hp = re.search(r"horsepower\s*=\s*([\d.]+)", text)
    mass = re.search(r"mass\s*=\s*([\d.]+);\s*\n\s*info", text) or re.search(r"\n\s*mass\s*=\s*([\d.]+)", text)
    eng = re.search(r"vehEngineData\s*=\s*\{(.*?)\}\s*:\s*VehicleEngineData", text, re.S)
    ed = {}
    gears = []
    if eng:
        body = eng.group(1)
        for k in ("engineMaxTorque", "resistanceTorque", "wheelsResistanceRatio", "flyWheelMomentOfInertia", "gearChangeTime",
                  "gearChangeCooldown", "minRPM", "maxRPM", "finalGearTorqueDecimationScalor"):
            m = re.search(r"\b%s\s*=\s*([-\d.]+)f?" % k, body)
            if m:
                ed[k] = float(m.group(1))
        for g in re.finditer(r"\{\s*minSpeed\s*=\s*([-\d.]+)f?;\s*maxSpeed\s*=\s*([-\d.]+)f?;\s*minEngineRPM\s*=\s*([-\d.]+)f?;\s*maxEngineRPM\s*=\s*([-\d.]+)f?;\s*torqueMultiplier\s*=\s*([-\d.]+)f?;", body):
            gears.append(dict(minSpeed=float(g.group(1)), maxSpeed=float(g.group(2)), minRPM=float(g.group(3)),
                              maxRPM=float(g.group(4)), tm=float(g.group(5))))
    dm = re.search(r"bikeDriveModelData\s*=\s*\{(.*?)\}\s*:\s*VehicleDriveModelData", text, re.S)
    dd = {}
    if dm:
        body = dm.group(1)
        for k in ("total_mass", "chassis_mass", "airResistanceFactor", "brakingFrictionFactor", "bikeMaxTilt", "handbrakeBrakingTorque"):
            m = re.search(r"\b%s\s*=\s*([-\d.]+)f?" % k, body)
            if m:
                dd[k] = float(m.group(1))
        fm = re.search(r"wheelsFrictionMap\s*=\s*\"([^\"]+)\"", body)
        if fm:
            dd["wheelsFrictionMap"] = fm.group(1)
        brakes = re.findall(r"maxBrakingTorque\s*=\s*([-\d.]+)f?", body)
        dd["brakes"] = [float(b) for b in brakes]
    res.append(dict(file=name, record=head.group(1) if head else None, hp=float(hp.group(1)) if hp else None,
                    uiMass=float(mass.group(1)) if mass else None, engine=ed, gears=gears, drive=dd))
json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
for r in res:
    g = r["gears"]
    print("%-18s hp=%-6s ui=%-5s T=%-6s res=%-5s rpm=%s-%s gears=%d top=%.1f m/s (%.0f km/h) mass=%s/%s drag=%s fric=%s brakes=%s" % (
        r["file"][6:-6], r["hp"], r["uiMass"], r["engine"].get("engineMaxTorque"), r["engine"].get("resistanceTorque"),
        r["engine"].get("minRPM"), r["engine"].get("maxRPM"), len(g), max([x["maxSpeed"] for x in g], default=0),
        max([x["maxSpeed"] for x in g], default=0) * 3.6, r["drive"].get("total_mass"), r["drive"].get("chassis_mass"),
        r["drive"].get("airResistanceFactor"), r["drive"].get("wheelsFrictionMap"), r["drive"].get("brakes")))
