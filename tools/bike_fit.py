"""Fit the real-world bike model to measured data (work\\vehicle-research\\bikes.md) and print the fit.
Model: point mass (bike wet + 80 kg rider), wheel power = eta * crank power, launch capped at a_max (wheelie/traction),
drag 0.5*rho*CdA*v^2, rolling 0.015*m*g. CdA by class (faired / naked). No explicit shifts (eta absorbs them).
Usage: python -I -X utf8 bike_fit.py"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import itertools, math

RHO, G, RIDER, CRR = 1.2, 9.81, 80.0, 0.015


def run(hp, kg, cda, eta, amax, dt=0.002, tmax=60.0):
    P = hp * 745.7 * eta
    m = kg + RIDER
    v = x = t = 0.0
    out = {}
    marks = [("60mph", 26.8224), ("100", 27.7778), ("100mph", 44.704), ("150mph", 67.056), ("200", 55.5556)]
    while t < tmax:
        drag = 0.5 * RHO * cda * v * v + CRR * m * G
        a = min(amax, P / max(v, 0.5) / m) - drag / m
        v += a * dt
        x += v * dt
        t += dt
        for k, vm in marks:
            if k not in out and v >= vm:
                out[k] = t
        if "qm" not in out and x >= 402.336:
            out["qm"] = t
            out["trap"] = v * 2.23694
        if a < 1e-4:
            break
    out["top"] = v * 3.6
    return out


def top_speed(hp, kg, cda, eta):
    P = hp * 745.7 * eta
    m = kg + RIDER
    lo, hi = 1.0, 200.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if P > (0.5 * RHO * cda * mid ** 3 + CRR * m * G * mid):
            lo = mid
        else:
            hi = mid
    return lo * 3.6


# name, crank hp, wet kg, class, measured: 0-60 s, qm s, trap mph, other
DATA = [
    ("Panigale V4", 214, 200, "F", dict(**{"60mph": 2.88, "qm": 10.35, "trap": 149.7})),
    ("R1 (2016)", 198, 201, "F", dict(**{"60mph": 2.9, "qm": 10.11, "trap": 146.6})),
    ("ZX-10R (2016)", 207, 207, "F", dict(**{"60mph": 2.8, "qm": 10.29, "trap": 146.0})),
    ("Hayabusa Gen3", 187, 264, "F", dict(**{"60mph": 2.69, "100mph": 5.18, "150mph": 10.71})),
    ("Ninja H2", 200, 240, "F", dict(**{"60mph": 2.6, "qm": 9.62, "trap": 152.0})),
    ("RSV4 1100", 217, 205, "F", dict(**{"60mph": 3.1, "qm": 10.4, "trap": 147.3})),
    ("KTM 1290 SDR", 180, 214, "N", dict(**{"qm": 10.32, "trap": 137.6})),
    ("FZ-09", 113, 193, "N", dict(**{"qm": 11.29, "trap": 123.7})),
    ("FZ-07", 74, 184, "N", dict(**{"qm": 12.38, "trap": 107.9})),
    ("R3", 42, 170, "F", dict(**{"qm": 14.49, "trap": 91.07})),
    ("RC 390", 44, 166, "F", dict(**{"qm": 13.95, "trap": 94.86})),
]
TOPS = [("Panigale V4 (unlimited)", 214, 200, "F", 304), ("Hayabusa Gen1 1999", 173, 250, "F", 307), ("KTM 1290 SDR", 180, 214, "N", 271),
        ("H2R (Hillier, app)", 310, 216, "F", 332), ("S 1000 RR 2019+", 205, 197, "F", 308)]


def err(params):
    eta, amax, cdaF, cdaN = params
    e = 0.0
    n = 0
    for name, hp, kg, cls, meas in DATA:
        r = run(hp, kg, cdaF if cls == "F" else cdaN, eta, amax)
        for k, v in meas.items():
            if k not in r:
                e += 1.0
                continue
            e += ((r[k] - v) / v) ** 2
            n += 1
    for name, hp, kg, cls, vt in TOPS:
        e += ((top_speed(hp, kg, cdaF if cls == "F" else cdaN, eta) - vt) / vt) ** 2
        n += 1
    return math.sqrt(e / n)


best = None
for eta in [0.80, 0.83, 0.86, 0.89, 0.92]:
    for amax in [8.5, 9.0, 9.5, 10.0, 10.5, 11.0]:
        for cdaF in [0.26, 0.28, 0.30, 0.32, 0.34, 0.36]:
            for cdaN in [0.34, 0.38, 0.42, 0.46, 0.50]:
                e = err((eta, amax, cdaF, cdaN))
                if best is None or e < best[0]:
                    best = (e, (eta, amax, cdaF, cdaN))
# refine
e0, (eta, amax, cdaF, cdaN) = best
for d_eta in [-0.015, 0, 0.015]:
    for d_a in [-0.25, 0, 0.25]:
        for d_f in [-0.01, 0, 0.01]:
            for d_n in [-0.02, 0, 0.02]:
                p = (eta + d_eta, amax + d_a, cdaF + d_f, cdaN + d_n)
                e = err(p)
                if e < best[0]:
                    best = (e, p)
e, (eta, amax, cdaF, cdaN) = best
print("FIT rms rel error %.1f %%: eta %.3f  a_max %.2f m/s2 (%.2f g)  CdA faired %.2f  naked %.2f" % (e * 100, eta, amax, amax / G, cdaF, cdaN))
print("%-16s %-24s %-24s" % ("bike", "measured", "model"))
for name, hp, kg, cls, meas in DATA:
    r = run(hp, kg, cdaF if cls == "F" else cdaN, eta, amax)
    print("%-16s %-50s | %s" % (name, " ".join("%s %.2f" % (k, v) for k, v in meas.items()),
                                " ".join("%s %.2f" % (k, r.get(k, float('nan'))) for k in meas) + "  0-100 %.2f 0-200 %s top %.0f" % (
                                    r.get("100", float('nan')), ("%.1f" % r["200"]) if "200" in r else "-", top_speed(hp, kg, cdaF if cls == "F" else cdaN, eta))))
for name, hp, kg, cls, vt in TOPS:
    print("%-24s top measured %d model %.0f" % (name, vt, top_speed(hp, kg, cdaF if cls == "F" else cdaN, eta)))
open(_os.path.join(WORK, r"bike_fit_params.txt"), "w").write("%f %f %f %f\n" % (eta, amax, cdaF, cdaN))
