"""Arch V4 bike settings v4: per-gear torque multipliers derived from the real acceleration curve.
Real (fitted bike model, stated hp / kg + 80 kg rider): a_real(v) = min(a_max, eta*P/(v*m)) - drag(v)/m.
Game model (calibrated on CVOO bikes): a_game(v) = K*T*tm/m_phys - D*drag*v^2/m_phys.
Scale A (CVOO top-speed map, factor k = game top / real top): the game should reach k*v when the real bike reaches v,
so a_game(k*v) = k*a_real(v). Scale B: k = 1. Each gear's tm makes a_game equal the target averaged over its band.
Bands: CVOO Arch superbike's 6 forward gears, speed-scaled; RPM bands mapped onto the bike's own RPM range.
T is set so gear 1 has tm 1.0. Usage: python -I -X utf8 bike_plan4.py"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import json, math, statistics, sys
sys.path.insert(0, _HERE)
from vehicle_model import sim_game
import vehicle_audit as va

S = WORK
rows = json.load(open(S + r"\vehicle_audit.json"))
K = statistics.median([x["K"] for x in rows if x.get("K") and x.get("bike")])
D = json.load(open(S + r"\drag_fit.json"))["bikes"]
arch = {r["file"]: r for r in json.load(open(S + r"\archv4_dump.json"))}
old = json.load(open(S + r"\bike_plan.json"))
ARCH = [(0.0, 17.6, 900, 5900), (16.0, 26.7, 3900, 6100), (23.8, 32.5, 4000, 6100),
        (29.9, 39.0, 4000, 6150), (36.4, 44.85, 4100, 6250), (41.6, 56.0, 4400, 6450)]
ARCH_TOP, ARCH_RPM = 56.0, (900.0, 6450.0)
DRAG = {"F": 0.65, "N": 0.75}
RHO, G = 1.2, 9.81

pts = [(math.log(x["real_top"]), math.log(x["top_game"])) for x in rows if x.get("real_top")]
n = len(pts); mx = sum(p[0] for p in pts) / n; my = sum(p[1] for p in pts) / n
b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sum((p[0] - mx) ** 2 for p in pts); a = my - b * mx
cvoo_top = lambda real: math.exp(a + b * math.log(real))


def a_real(v, hp, kg, cda):
    m = kg + 80
    P = hp * 745.7 * va.B_ETA
    return min(va.B_AMAX, P / max(v, 0.5) / m) - (0.5 * RHO * cda * v * v + 0.015 * m * G) / m


plan = []
for p in old:
    cls = "F" if p["name"] == "FZR 3000" else "N"
    cda = va.B_CDAF if cls == "F" else va.B_CDAN
    a_rec = arch[p["file"]]
    rpm_lo, rpm_hi = a_rec["engine"]["minRPM"], a_rec["engine"]["maxRPM"]
    m_phys = round(p["ui_kg"] * 1.51)
    dg = DRAG[cls]
    out = {}
    for scale in ("A", "B"):
        top = cvoo_top(p["real_top"]) if scale == "A" else p["real_top"]
        k = top / p["real_top"]
        s = (top / 3.6) / ARCH_TOP
        force = []           # K*T*tm per gear (game units of m_phys * accel)
        bands = []
        for lo, hi, r1, r2 in ARCH:
            glo, ghi = lo * s, hi * s
            vs = [glo + (ghi - glo) * (i + 0.5) / 20 for i in range(20)]
            need = statistics.mean(k * a_real(v / k, p["hp"], p["ui_kg"], cda) * m_phys + D * dg * v * v for v in vs)
            # top gear must still out-pull drag at 99 % of the top speed
            force.append(max(need, 0.0))
            mapr = lambda r: round(rpm_lo + (r - ARCH_RPM[0]) / (ARCH_RPM[1] - ARCH_RPM[0]) * (rpm_hi - rpm_lo))
            bands.append((round(glo, 2), round(ghi, 2), mapr(r1), mapr(r2)))
        vt = 0.99 * top / 3.6
        force[-1] = max(force[-1], D * dg * vt * vt * 1.03)
        base_force = list(force)
        lowmask = [bl[1] <= 27.7778 * k * 1.15 for bl in bands]     # gears that carry the 0-100 run
        lowmask[0] = True
        c_lo = c_hi = 1.0
        for _it in range(25):        # shift dead time in the game model costs time: scale low / high gears to the real times
            force = [f * (c_lo if lm else c_hi) for f, lm in zip(base_force, lowmask)]
            force[-1] = max(force[-1], D * dg * vt * vt * 1.03)
            T = force[0] / K
            gl = [(bl[0], bl[1], f / (K * T)) for bl, f in zip(bands, force)]
            sim = sim_game(T, gl, m_phys, dg, K=K, D=D, dt=0.005, horizon=60, tmax=120, marks={"100": 27.7778 * k, "200": 55.5556 * k})
            t1, t2 = sim["times"].get("100"), sim["times"].get("200")
            if t1:
                c_lo *= (t1 / p["real_t100"]) ** 0.9
            if t2 and p["real_t200"]:
                c_hi *= ((t2 - (t1 or 0)) / max(p["real_t200"] - p["real_t100"], 0.5)) ** 0.9
        T = force[0] / K                  # gear 1 multiplier = 1.0
        gears = [dict(minSpeed=bl[0], maxSpeed=bl[1], minRPM=bl[2], maxRPM=bl[3], tm=round(f / (K * T), 4)) for bl, f in zip(bands, force)]
        sim = sim_game(T, [(g["minSpeed"], g["maxSpeed"], g["tm"]) for g in gears], m_phys, dg, K=K, D=D, dt=0.005, horizon=60, tmax=120,
                       marks={"100": 27.7778 * k, "200": 55.5556 * k})
        out[scale] = dict(torque=round(T), mass=m_phys, drag=dg, top=round(top), k=round(k, 4), gears=gears,
                          t100=sim["times"].get("100"), t200=sim["times"].get("200"), reach=sim["top"] * 3.6)
    p["v4"] = out
    p["cls"] = cls
    plan.append(p)
json.dump(plan, open(S + r"\bike_plan4.json", "w"), indent=1)
print("K_bike %.1f D_bike %.3f; CVOO map: game top = %.2f * real^%.3f" % (K, D, math.exp(a), b))
for p in plan:
    for sc in ("A", "B"):
        v = p["v4"][sc]
        print("%-9s %s T %4d m %3d top %3d | to %3.0f: %.2f s (real %.2f) | to %3.0f: %s (real %s) | reaches %.0f | tm %s" % (
            p["name"], sc, v["torque"], v["mass"], v["top"], 100 * v["k"], v["t100"] or -1, p["real_t100"], 200 * v["k"],
            ("%.2f" % v["t200"]) if v["t200"] else "-", ("%.1f" % p["real_t200"]) if p["real_t200"] else "-", v["reach"],
            [g["tm"] for g in v["gears"]]))
