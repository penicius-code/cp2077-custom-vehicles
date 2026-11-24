"""Realism plan for every CVOO vehicle (cars and bikes), the three SCALED custom cars and the Arch V4 bikes.
Target = what the vehicle's own stated specs (vehicleUIData hp / mass / drive layout) give in the real world, on the TRUE
speed scale (V, 2026-11-02): 0-100 km/h (cars: empirical fit car_fit2, bikes: bike_fit physics), top speed (physics,
drag area by body class / mass, capped at 420 km/h cars and 400 km/h bikes), 0-200 km/h from the same acceleration curve.
Game tables: per gear torque multiplier from the target acceleration curve averaged over the gear's band, net of the game
model's drag; bands = the vehicle's current bands scaled to the new top speed; RPM bands kept; torque so gear 1 = 1.0;
two correction factors (low / high gears) so the game model hits 0-100 and 0-200. Game model: K and D fitted on CVOO.
Writes work\\realism_plan.json and the CET data file realism_data.lua. Usage: python -I -X utf8 realism_plan.py <lua out>"""
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
LUA_OUT = sys.argv[1]
audit = json.load(open(S + r"\vehicle_audit.json"))
cvoo = {r["file"]: r for r in json.load(open(S + r"\cvoo_dump.json"))}
ui = json.load(open(S + r"\vehicle_ui_specs.json"))
dragfit = json.load(open(S + r"\drag_fit.json"))
# Game constants MEASURED in game (scripts\bench_fit.py on CyberslopVehicleBench 1.1 traces, 2026-11-02 02:31-02:35:
# Type-66 on Authentic Shift's records, Arch V4 Valor on the BIKES records, Arch Tyger gears 5-6). The 1.1.0 values
# (fitted on CVOO's own tune: cars K 29.9 D 0.969, bikes K 23.2 D 0.710) gave ~60 % of the planned force.
K = {False: 17.92, True: 13.73}
D = {False: 0.902, True: 0.590}
RHO, G = 1.2, 9.81
CAP = {"RWD": 27.7778 / (va.FLOOR["RWD"] * 1.05) * 1.08, "AWD": 27.7778 / (va.FLOOR["AWD"] * 1.05) * 1.08,
       "FWD": 27.7778 / (va.FLOOR["FWD"] * 1.05) * 1.08}
TOPCAP = {False: 420.0, True: 400.0}
TOP_HEADROOM = 1.07


def cda_for(rec, kg, bike):
    if bike:
        return va.B_CDAN if ("apollo" in rec or "arch" in rec) else va.B_CDAF
    if kg >= 4000:
        return 3.0
    return va.car_cda(rec)


class Profile:
    """Real acceleration curve a(v) for the stated specs, with the 0-100 pinned to the empirical / fitted value."""
    def __init__(self, hp, kg, layout, cda, bike):
        self.bike = bike
        self.m = kg + (80 if bike else 75)
        self.cda = cda
        self.crr = 0.015 if bike else 0.013
        self.cap = va.B_AMAX if bike else CAP.get(layout, CAP["RWD"])
        eta_top = va.B_ETA if bike else va.C_ETA
        self.top = min(va.top_speed(hp, self.m, cda, eta_top, self.crr), TOPCAP[bike]) / 3.6
        self.p_hi = (0.5 * RHO * cda * self.top ** 3 + self.crr * self.m * G * self.top)   # power that holds the top speed
        if bike:
            self.p_lo = hp * 745.7 * va.B_ETA
            self.t100 = self.time_to(27.7778)
        else:
            self.t100 = va.car_t100(hp, kg, layout)
            lo, hi = 1e3, 3e7                              # power that gives the empirical 0-100
            for _ in range(60):
                mid = math.sqrt(lo * hi)
                self.p_lo = mid
                if (self.time_to(27.7778) or 1e9) > self.t100:
                    lo = mid
                else:
                    hi = mid
            self.p_lo = math.sqrt(lo * hi)
            if (self.time_to(27.7778) or 1e9) > self.t100 * 1.02:   # traction-limited floor: raise the cap a little
                while (self.time_to(27.7778) or 1e9) > self.t100 and self.cap < 15:
                    self.cap *= 1.02
        self.t200 = self.time_to(55.5556) if self.top > 55.6 else None

    def power(self, v):
        w = min(max((v - 20.0) / 20.0, 0.0), 1.0)
        return self.p_lo * (1 - w) + self.p_hi * w

    def a(self, v):
        return min(self.cap, self.power(v) / max(v, 0.5) / self.m) - (0.5 * RHO * self.cda * v * v + self.crr * self.m * G) / self.m

    def time_to(self, vt, dt=0.004):
        v = t = 0.0
        while v < vt and t < 120:
            a = self.a(v)
            if a <= 1e-4:
                return None
            v += a * dt
            t += dt
        return t if v >= vt else None


def floor_drag(f, nb, d_, drag, vt):
    """Every gear must out-pull the game model's drag at the top of its band (else the car stalls in that gear);
    the top gear at 99 % of the top speed."""
    out = []
    for ff, (lo, hi, _, _) in zip(f, nb):
        v = min(hi, vt)
        out.append(max(ff, d_ * drag * v * v * 1.04))
    out[-1] = max(out[-1], d_ * drag * vt * vt * 1.04)
    return out


def build(prof, bands, m_phys, drag, bike):
    """bands: list of (min, max, minRPM, maxRPM) at the OLD scale; returns torque + gear rows at the new top speed."""
    k_, d_ = K[bike], D[bike]
    # game drag factor from the real drag area: D*drag*v^2 / m_phys == 0.5*rho*CdA*v^2 / m_real
    drag = round(m_phys * 0.5 * RHO * prof.cda / (prof.m * d_), 4)
    old_top = max(b[1] for b in bands)
    s = prof.top / old_top
    nb = [(lo * s, hi * s, r1, r2) for lo, hi, r1, r2 in bands]
    base = []
    for lo, hi, _, _ in nb:
        vs = [lo + (hi - lo) * (i + 0.5) / 20 for i in range(20)]
        base.append(max(statistics.mean(prof.a(v) * m_phys + d_ * drag * v * v for v in vs), 1e-3))
    vt = 0.99 * prof.top
    low = [hi <= 27.7778 * 1.15 for lo, hi, _, _ in nb]
    low[0] = True
    c_lo = c_hi = 1.0
    t1 = t2 = None
    for _ in range(30):
        f = floor_drag([b * (c_lo if l else c_hi) for b, l in zip(base, low)], nb, d_, drag, vt)
        T = f[0] / k_
        g = [(lo, hi, ff / (k_ * T)) for (lo, hi, _, _), ff in zip(nb, f)]
        r = sim_game(T, g, m_phys, drag, K=k_, D=d_, dt=0.01, horizon=60, tmax=120)
        t1, t2 = r["times"].get("100"), r["times"].get("200")
        if t1:
            c_lo *= (t1 / prof.t100) ** 0.9
        if t2 and prof.t200:
            c_hi *= ((t2 - (t1 or 0)) / max(prof.t200 - prof.t100, 0.5)) ** 0.9
    f = floor_drag([b * (c_lo if l else c_hi) for b, l in zip(base, low)], nb, d_, drag, vt)
    T = f[0] / k_
    gears = [dict(minSpeed=round(lo, 3), maxSpeed=round(hi, 3), tm=round(ff / (k_ * T), 4), minRPM=r1, maxRPM=r2)
             for (lo, hi, r1, r2), ff in zip(nb, f)]
    # Top gear headroom (1.2.3): the band end is where the engine hits its rev limiter. Ending it AT the real top speed made
    # every vehicle top out bouncing on the limiter (bench 04:22: Valor rpm at the limiter from 236 km/h, creeping to 263 with
    # ~2-13 % rear slip = screech; Tyger 6446 of 6450 rpm at 253). +7 % so the top speed is drag-limited at ~93 % rpm, never
    # past 97 m/s (Authentic Shift caps gears at the engine's 100 m/s movement limit - 3); bands already above are kept.
    last = gears[-1]
    last["maxSpeed"] = round(max(last["maxSpeed"], min(last["maxSpeed"] * TOP_HEADROOM, 97.0)), 3)
    r = sim_game(T, [(x["minSpeed"], x["maxSpeed"], x["tm"]) for x in gears], m_phys, drag, K=k_, D=d_, dt=0.005, horizon=60, tmax=150)
    return dict(torque=round(T, 1), drag=drag, gears=gears, g100=r["times"].get("100"), g200=r["times"].get("200"), reach=r["top"] * 3.6)


entries = []
report = []

# Vehicle -> owning CVOO module. 5 vehicles are listed by two modules; the one whose vehicle name shares the most
# name parts with it wins (tie: the shorter, more generic module name). Each vehicle is rewired by one row only.
def _tokens(name):
    return set(name.replace("Vehicle.", "").replace("v_", "", 1).split("_"))
_claims = {}
for _r in cvoo.values():
    if not _r.get("vehicle"):
        continue
    for _t in set(_r["targets"] + [_r["vehicle"]]):
        _claims.setdefault(_t, []).append(_r)
OWNER = {}
for _t, _rs in _claims.items():
    OWNER[_t] = max(_rs, key=lambda r: (len(_tokens(_t) & _tokens(r["vehicle"])), -len(_tokens(r["vehicle"])), r["file"] == min(x["file"] for x in _rs)))["file"]

# ---------------------------------------------------------------- CVOO vehicles
for x in audit:
    if "hp" not in x:
        continue
    row = cvoo[x["module"]]
    bike = x["bike"]
    keys = sorted([kk for kk in row["gears"] if int(kk) > 0], key=int)
    bands, idx = [], []
    for kk in keys:
        g = row["gears"][kk]
        if "gearsMaxSpeed" not in g or "gearsTorqueMult" not in g:
            continue
        if bands and g["gearsMaxSpeed"] <= bands[-1][1]:
            break                     # a band that is not above the previous one (CVOO V-Tech gear 8): left as CVOO set it
        bands.append((g.get("gearsMinSpeed", 0.0), g["gearsMaxSpeed"], g.get("gearsMinRPM"), g.get("gearsMaxRPM")))
        idx.append(int(kk))
    prof = Profile(x["hp"], x["ui_kg"], x["layout"], cda_for(x["vehicle"], x["ui_kg"], bike), bike)
    res = build(prof, bands, x["phys_kg"], x["drag"] or 2.0, bike)
    entries.append(dict(kind="cvoo", name=x["module"], engine=x["vehicle"] + "_full_enginedata", gearPrefix=x["vehicle"] + "_inline_gear",
                        driveModel=x["vehicle"] + ("_full_vehDriveModelData"),
                        vehicles=[t for t in dict.fromkeys([x["vehicle"]] + row.get("targets", []))
                                  if OWNER.get(t) == x["module"]],
                        gearIndex=idx, **res))
    report.append(dict(name=x["module"].replace("_tweak.lua", "").replace(".lua", ""), bike=bike, hp=x["hp"], kg=x["ui_kg"], layout=x["layout"],
                       real100=prof.t100, real200=prof.t200, realtop=prof.top * 3.6, old100=x.get("game_t100"), oldtop=x["top_game"],
                       old_torque=x["torque"], **{k2: res[k2] for k2 in ("torque", "g100", "g200", "reach")}))

# ---------------------------------------------------------------- SCALED custom cars (records built by the SCALED pass)
SCALED = [("NSX Liberty Walk", "Vehicle.nsx_lb_base", "porsche_911_tweak.lua", 290, 1370, "RWD", 1370, 0.80),
          ("Supron Widebody", "Vehicle.oranje3_supron_widebody", "mahir_supron_tweak.lua", 400, 1481, "RWD", 1600, 1.140),
          ("Merrimac Necromancer", "Vehicle.oranje3_merrimac_necromancer", "thorton_merrimac_warlock.lua", 700, 1740, "RWD", 1740, 1.205)]
for name, rec, tmpl, hp, kg, lay, m_phys, vs in SCALED:
    row = cvoo[tmpl]
    keys = sorted([kk for kk in row["gears"] if int(kk) > 0 and "gearsMaxSpeed" in row["gears"][kk]], key=int)
    bands = [(row["gears"][kk].get("gearsMinSpeed", 0.0) * vs, row["gears"][kk]["gearsMaxSpeed"] * vs,
              row["gears"][kk].get("gearsMinRPM"), row["gears"][kk].get("gearsMaxRPM")) for kk in keys]
    prof = Profile(hp, kg, lay, 0.70 if "nsx" in rec or "supron" in rec else 0.85, False)
    res = build(prof, bands, m_phys, row["drag"], False)
    entries.append(dict(kind="scaled", name=name, engine=rec + "_ccv_engine", gearPrefix=rec + "_ccv_gear", driveModel=rec + "_ccv_dm", gearIndex=[int(kk) for kk in keys], **res))
    report.append(dict(name=name + " (custom)", bike=False, hp=hp, kg=kg, layout=lay, real100=prof.t100, real200=prof.t200, realtop=prof.top * 3.6,
                       old100=None, oldtop=max(b[1] for b in bands) * 3.6, old_torque=None, **{k2: res[k2] for k2 in ("torque", "g100", "g200", "reach")}))

# ---------------------------------------------------------------- Arch V4 bikes (BIKES pass: explicit tables, true scale)
arch = {r["file"]: r for r in json.load(open(S + r"\archv4_dump.json"))}
ARCH = [(0.0, 17.6, 900, 5900), (16.0, 26.7, 3900, 6100), (23.8, 32.5, 4000, 6100), (29.9, 39.0, 4000, 6150), (36.4, 44.85, 4100, 6250), (41.6, 56.0, 4400, 6450)]
BIKES = [("FZR 3000", "ArchV4_FZR.tweak", "F", ["Vehicle.v_fzr3000"]),
         ("Fyrn", "ArchV4_Fyrn.tweak", "N", ["Vehicle.v_arch_v4fyrn"] + ["Vehicle.v_arch_v4fyrn_" + c for c in ("carbon", "white", "red", "yellow", "green", "blue", "pink", "mox", "gray", "gold")]),
         ("Malina", "ArchV4_Malina.tweak", "N", ["Vehicle.v_sportbike2_arch_linas_player"]),
         ("Mogus", "ArchV4_Mogus.tweak", "N", ["Vehicle.v_arch_v4mogus"] + ["Vehicle.v_arch_v4mogus_" + c for c in ("carbon", "white", "red", "yellow", "green", "blue", "pink", "mox", "gray")]),
         ("Paladin", "ArchV4_Paladin.tweak", "N", ["Vehicle.v_arch_v4paladin"] + ["Vehicle.v_arch_v4paladin_" + c for c in ("carbon", "white", "red", "yellow", "green", "blue", "pink", "mox", "gray", "gold", "legacy", "graphite")]),
         ("Valor", "ArchV4_Valor.tweak", "N", ["Vehicle.v_arch_v4valor"] + ["Vehicle.v_arch_v4valor_" + c for c in ("carbon", "white", "red", "yellow", "green", "blue", "pink", "mox", "gray", "skin_0")]),
         ("Vigil", "ArchV4_Vigil.tweak", "N", ["Vehicle.v_arch_v4vigil"] + ["Vehicle.v_arch_v4vigil_" + c for c in ("carbon", "white", "red", "yellow", "green", "blue", "pink", "mox", "gray")])]
bike_rows = []
for name, f, cls, targets in BIKES:
    a = arch[f]
    lo_r, hi_r = a["engine"]["minRPM"], a["engine"]["maxRPM"]
    mapr = lambda r: round(lo_r + (r - 900.0) / (6450.0 - 900.0) * (hi_r - lo_r))
    bands = [(lo, hi, mapr(r1), mapr(r2)) for lo, hi, r1, r2 in ARCH]
    prof = Profile(a["hp"], a["uiMass"], "RWD", va.B_CDAF if cls == "F" else va.B_CDAN, True)
    m_phys = round(a["uiMass"] * 1.51)
    drag = 0.65 if cls == "F" else 0.75
    res = build(prof, bands, m_phys, drag, True)
    old_g = [(g["minSpeed"], g["maxSpeed"], g["tm"]) for g in a["gears"][1:]]
    old = sim_game(a["engine"]["engineMaxTorque"], old_g, a["drive"]["total_mass"], a["drive"]["airResistanceFactor"], K=K[True], D=D[True], dt=0.005, horizon=60, tmax=150)
    bike_rows.append(dict(name=name + " (Arch V4)", targets=targets, torque=res["torque"], mass=m_phys, drag=res["drag"], gears=res["gears"]))
    report.append(dict(name=name + " (Arch V4)", bike=True, hp=a["hp"], kg=a["uiMass"], layout="RWD", real100=prof.t100, real200=prof.t200,
                       realtop=prof.top * 3.6, old100=old["times"].get("100"), oldtop=max(g[1] for g in old_g) * 3.6,
                       old_torque=a["engine"]["engineMaxTorque"], **{k2: res[k2] for k2 in ("torque", "g100", "g200", "reach")}))

json.dump(dict(entries=entries, bikes=bike_rows, report=report, K={"cars": K[False], "bikes": K[True]}, D={"cars": D[False], "bikes": D[True]}),
          open(S + r"\realism_plan.json", "w"), indent=1)

# ---------------------------------------------------------------- Lua data file
def lua_gears(gs, idx=None):
    out = []
    for i, g in enumerate(gs):
        gi = idx[i] if idx else i + 1
        out.append("{ i = %d, minSpeed = %.3f, maxSpeed = %.3f, tm = %.4f, minRPM = %s, maxRPM = %s }" % (
            gi, g["minSpeed"], g["maxSpeed"], g["tm"], g["minRPM"] if g["minRPM"] is not None else "nil", g["maxRPM"] if g["maxRPM"] is not None else "nil"))
    return "{\n            " + ",\n            ".join(out) + " }"

L = ["-- GENERATED by scripts\\realism_plan.py (%d vehicles). Do not edit by hand: re-run the planner." % (len(entries) + len(bike_rows)),
     "-- Targets: the vehicle's own stated hp / mass / drive layout -> real-world 0-100, 0-200 km/h and top speed (true km/h).",
     "-- engine / gearPrefix: records built by CVOO (\"<vehicle>_full_enginedata\", \"<vehicle>_inline_gear<i>\") or by the SCALED pass.",
     "local R = {}", "R.vehicles = {"]
for e in entries:
    L.append("    { name = %s, engine = %s, gearPrefix = %s, driveModel = %s, torque = %.1f, drag = %.4f,\n        target = \"0-100 %.1f s, top %.0f km/h\",\n        vehicles = { %s },\n        gears = %s }," % (
        json.dumps(e["name"]), json.dumps(e["engine"]), json.dumps(e["gearPrefix"]), json.dumps(e["driveModel"]), e["torque"], e["drag"],
        next(r["real100"] for r in report if r["name"].startswith(e["name"].replace("_tweak.lua", "").replace(".lua", "")) or r["name"].startswith(e["name"])),
        next(r["realtop"] for r in report if r["name"].startswith(e["name"].replace("_tweak.lua", "").replace(".lua", "")) or r["name"].startswith(e["name"])),
        ", ".join(json.dumps(v) for v in e.get("vehicles", [])),
        lua_gears(e["gears"], e["gearIndex"])))
L.append("}")
L.append("R.bikes = {")
for b in bike_rows:
    L.append("    { name = %s, targets = { %s },\n        torque = %.1f, mass = %d, drag = %.4f,\n        gears = %s }," % (
        json.dumps(b["name"]), ", ".join(json.dumps(t) for t in b["targets"]), b["torque"], b["mass"], b["drag"], lua_gears(b["gears"])))
L.append("}")
L.append("return R")
open(LUA_OUT, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

print("K cars %.1f bikes %.1f | D cars %.3f bikes %.3f" % (K[False], K[True], D[False], D[True]))
print("| Vehicle | Stated hp / kg / layout | Real 0-100 | Real 0-200 | Real top | Before: 0-100 / top (true) | After: 0-100 / 0-200 / top (model) | Torque before -> after |")
print("|---|---|---|---|---|---|---|---|")
for r in sorted(report, key=lambda r: (r["bike"], r["name"])):
    print("| %s | %d / %d / %s | %.1f s | %s | %.0f | %s / %.0f | %s / %s / %.0f | %s -> %.0f |" % (
        r["name"], r["hp"], r["kg"], r["layout"], r["real100"], ("%.1f s" % r["real200"]) if r["real200"] else "-", r["realtop"],
        ("%.1f s" % r["old100"]) if r["old100"] else "-", r["oldtop"], ("%.1f s" % r["g100"]) if r["g100"] else "-",
        ("%.1f s" % r["g200"]) if r["g200"] else "-", r["reach"], ("%.0f" % r["old_torque"]) if r["old_torque"] else "-", r["torque"]))
