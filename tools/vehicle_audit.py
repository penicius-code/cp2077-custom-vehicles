"""Realism audit of every tuned vehicle: the game's own stated specs (vehicleUIData hp / mass / layout) -> real-world
expected 0-100 km/h and top speed (fitted models), vs what the drivetrain tables give in the game (model, true speed).
Usage: python -I -X utf8 vehicle_audit.py   (writes work\\vehicle_audit.json and .md)"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import json, math, statistics, sys
sys.path.insert(0, _HERE)
from vehicle_model import sim_game

S = WORK
ui = json.load(open(S + r"\vehicle_ui_specs.json"))
cvoo = json.load(open(S + r"\cvoo_dump.json"))
arch = json.load(open(S + r"\archv4_dump.json"))
c2 = [float(x) for x in open(S + r"\car_fit2_params.txt").read().split()]
CF_C, CF_B, FLOOR = c2[0], c2[1], {"RWD": c2[2], "AWD": c2[3], "FWD": c2[4]}
bk = [float(x) for x in open(S + r"\bike_fit_params.txt").read().split()]
B_ETA, B_AMAX, B_CDAF, B_CDAN = bk
C_ETA = 0.69          # car_fit.py physics fit (top speed only)
RHO, G = 1.2, 9.81


# ---------------------------------------------------------------- real-world expectations
def car_t100(hp, kg, layout):
    return max(FLOOR.get(layout, 3.2), CF_C * (kg / hp) ** CF_B) * 1.05


def top_speed(hp, kg, cda, eta, crr=0.013):
    P = hp * 745.7 * eta
    lo, hi = 1.0, 250.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if P > 0.5 * RHO * cda * mid ** 3 + crr * kg * G * mid:
            lo = mid
        else:
            hi = mid
    return lo * 3.6


def bike_real(hp, kg, cda):
    P = hp * 745.7 * B_ETA
    m = kg + 80
    v = t = 0.0
    t100 = t200 = None
    dt = 0.002
    while t < 60:
        a = min(B_AMAX, P / max(v, 0.5) / m) - (0.5 * RHO * cda * v * v + 0.015 * m * G) / m
        v += a * dt
        t += dt
        if t100 is None and v >= 27.7778:
            t100 = t
        if t200 is None and v >= 55.5556:
            t200 = t
        if a < 1e-4:
            break
    return t100, t200, top_speed(hp, kg + 80, cda, B_ETA, 0.015)


def car_cda(rec):
    r = rec.lower()
    if any(k in r for k in ("utility", "standard3", "columbus", "mackinaw", "hellhound", "legatus", "emperor", "kurtz")):
        return 1.15
    if "standard25" in r:
        return 0.85
    return 0.70


# ---------------------------------------------------------------- game side
def gears_cvoo(row):
    out = []
    for k in sorted(row["gears"], key=lambda x: int(x)):
        if int(k) == 0:
            continue
        g = row["gears"][k]
        if "gearsMaxSpeed" in g and "gearsTorqueMult" in g:
            out.append((g.get("gearsMinSpeed", 0.0), g["gearsMaxSpeed"], g["gearsTorqueMult"]))
    return out


def game_t100(T, gears, m, drag, K):
    s = sim_game(T, gears, m, drag, K=K, D=0.5, horizon=30, tmax=60)
    return s["times"].get("100")


def solve_K(T, gears, m, drag, target):
    """K that makes the game model hit `target` seconds 0-100 (true km/h); None if the top gear is below 100 km/h."""
    if max(g[1] for g in gears) < 27.8:
        return None
    lo, hi = 1.0, 400.0
    for _ in range(40):
        mid = math.sqrt(lo * hi)
        t = game_t100(T, gears, m, drag, mid)
        if t is None or t > target:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


rows = []
for r in cvoo:
    if not r["vehicle"]:
        continue
    cand = [r["vehicle"] + "_player", r["vehicle"]] + r["targets"]
    spec = None
    for c in cand:
        if c in ui and ui[c].get("hp"):
            spec, specrec = ui[c], c
            break
    gs = gears_cvoo(r)
    if not spec or not gs or not r["torque"]:
        rows.append(dict(module=r["file"], vehicle=r["vehicle"], note="no UI spec or gear table"))
        continue
    hp, kg, lay = spec["hp"], spec["mass"], spec.get("layout", "RWD")
    m_phys = r["mass"] or kg
    if r["bike"]:
        cda = B_CDAN if "apollo" in r["vehicle"] else B_CDAF
        t100, t200, vtop = bike_real(hp, kg, cda)
    else:
        t100 = car_t100(hp, kg, lay)
        vtop = top_speed(hp, kg + 75, car_cda(r["vehicle"]), C_ETA)
    rows.append(dict(module=r["file"], vehicle=r["vehicle"], spec_from=specrec, bike=r["bike"], hp=hp, ui_kg=kg, layout=lay,
                     phys_kg=m_phys, torque=r["torque"], drag=r["drag"], gears=gs, top_game=max(g[1] for g in gs) * 3.6,
                     real_t100=t100, real_top=vtop, K=solve_K(r["torque"], gs, m_phys, r["drag"] or 2.0, t100)))

for kind in (False, True):
    ks = [x["K"] for x in rows if x.get("K") and x.get("bike") == kind]
    med = statistics.median(ks)
    for x in rows:
        if x.get("K") and x.get("bike") == kind:
            x["K_med"] = med
            x["strength"] = x["K"] and med / x["K"]          # >1: the game tune is stronger than the specs justify
            x["game_t100"] = game_t100(x["torque"], x["gears"], x["phys_kg"], x["drag"] or 2.0, med)
    print("%s: median K %.1f over %d vehicles, spread (IQR) %.1f-%.1f" % ("bikes" if kind else "cars", med, len(ks),
          statistics.quantiles(ks, n=4)[0], statistics.quantiles(ks, n=4)[2]))

json.dump(rows, open(S + r"\vehicle_audit.json", "w"), indent=1)
lines = ["| Vehicle (CVOO module) | Stated hp / kg / layout | Real 0-100 s | Game 0-100 s (model) | Tune vs specs | Real top km/h | Game top km/h (true) | Top ratio |",
         "|---|---|---|---|---|---|---|---|"]
for x in sorted(rows, key=lambda x: (x.get("bike", False), x["module"])):
    if "real_t100" not in x:
        lines.append("| %s | n/a | | | | | | |" % x["module"])
        continue
    gt = x.get("game_t100")
    lines.append("| %s | %d / %d / %s | %.1f | %s | %s | %.0f | %.0f | %.2f |" % (
        x["module"].replace("_tweak.lua", "").replace(".lua", ""), x["hp"], x["ui_kg"], x["layout"], x["real_t100"],
        ("%.1f" % gt) if gt else "> top", ("x%.2f" % x["strength"]) if x.get("strength") else "-", x["real_top"], x["top_game"],
        x["top_game"] / x["real_top"]))
open(S + r"\vehicle_audit.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
