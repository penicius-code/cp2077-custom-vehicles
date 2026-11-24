"""Fit the real-world CAR model (same physics as bike_fit.py, launch cap per drive layout) to measured road tests.
Data: research files where they hold a measured test, otherwise well-known magazine (Car and Driver / MotorTrend)
figures from background knowledge, marked (bg) in the table; 0-60 mph times. Usage: python -I -X utf8 car_fit.py"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import math

RHO, G, CRR = 1.2, 9.81, 0.013
DRIVER = 75.0


def run(hp, kg, layout, cda, eta, caps, dt=0.004):
    P = hp * 745.7 * eta
    m = kg + DRIVER
    amax = caps[layout]
    v = t = 0.0
    out = {}
    marks = [("60mph", 26.8224), ("100", 27.7778), ("200", 55.5556)]
    while t < 90:
        drag = 0.5 * RHO * cda * v * v + CRR * m * G
        a = min(amax, P / max(v, 0.5) / m) - drag / m
        v += a * dt
        t += dt
        for k, vm in marks:
            if k not in out and v >= vm:
                out[k] = t
        if a < 1e-4:
            break
    return out


def top(hp, kg, cda, eta):
    P = hp * 745.7 * eta
    m = kg + DRIVER
    lo, hi = 1.0, 200.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if P > 0.5 * RHO * cda * mid ** 3 + CRR * m * G * mid:
            lo = mid
        else:
            hi = mid
    return lo * 3.6


# name, hp, curb kg, layout, CdA class, 0-60 mph measured, top km/h (None if limited), source tag
DATA = [
    ("Acura NSX NA1 1991", 270, 1365, "RWD", "S", 5.5, 270, "cars-b (C/D 5.2-5.8)"),
    ("Toyota Supra A80 Turbo", 320, 1565, "RWD", "S", 5.0, None, "cars-b (4.6-5.4), limited 250"),
    ("Dodge Charger Hellcat", 707, 2069, "RWD", "M", 3.7, 327, "cars-b (C/D 3.7)"),
    ("Mustang Shelby GT500 2020", 760, 1915, "RWD", "S", 3.6, None, "cars-b (C/D 3.6), limited"),
    ("Porsche 911 Turbo S 992", 640, 1640, "AWD", "S", 2.2, 330, "(bg) C/D 2.2"),
    ("Subaru WRX STI 2019", 310, 1530, "AWD", "M", 4.8, 255, "(bg) C/D ~4.6-5.0"),
    ("Honda Civic Type R FL5", 315, 1430, "FWD", "M", 5.0, 275, "(bg) C/D ~4.9-5.4"),
    ("VW Golf GTI Mk7", 220, 1360, "FWD", "M", 5.9, 246, "(bg) C/D ~5.8-6.2"),
    ("Toyota Corolla 2.0 2020", 169, 1350, "FWD", "M", 7.6, 190, "(bg) C/D ~7.5-8.0"),
    ("Mazda MX-5 ND2", 181, 1060, "RWD", "M", 5.7, 220, "(bg) C/D 5.7"),
    ("Chevrolet Suburban 5.3 2021", 355, 2600, "AWD", "L", 7.1, None, "(bg) C/D ~7.0-7.4, governed"),
    ("Ford F-150 5.0 2021", 400, 2250, "AWD", "L", 5.9, None, "(bg) C/D ~5.6-6.2, governed"),
    ("Bugatti Chiron", 1479, 1996, "AWD", "S", 2.4, None, "(bg) C/D 2.3-2.5, limited 420"),
    ("Rimac Nevera", 1914, 2300, "AWD", "S", 1.8, 412, "(bg) MT 1.81"),
    ("Porsche 930 Turbo 3.3 1978", 300, 1300, "RWD", "M", 5.3, 260, "(bg) period tests 5.0-5.6"),
]
CDA = {"S": None, "M": None, "L": None}


def err(eta, cR, cA, cF, cdaS, cdaM, cdaL):
    caps = {"RWD": cR, "AWD": cA, "FWD": cF}
    cd = {"S": cdaS, "M": cdaM, "L": cdaL}
    e = n = 0
    for name, hp, kg, lay, cls, t60, vt, src in DATA:
        r = run(hp, kg, lay, cd[cls], eta, caps)
        e += ((r.get("60mph", 99) - t60) / t60) ** 2
        n += 1
        if vt:
            e += ((top(hp, kg, cd[cls], eta) - vt) / vt) ** 2
            n += 1
    return math.sqrt(e / n)


best = None
for eta in [0.72, 0.76, 0.80, 0.84]:
    for cR in [8.0, 8.8, 9.6, 10.4]:
        for cA in [10.0, 11.0, 12.0, 13.5]:
            for cF in [6.5, 7.5, 8.5]:
                for cdaS in [0.60, 0.70, 0.80]:
                    for cdaM in [0.65, 0.75, 0.85]:
                        e = err(eta, cR, cA, cF, cdaS, cdaM, 1.2)
                        if best is None or e < best[0]:
                            best = (e, [eta, cR, cA, cF, cdaS, cdaM, 1.2])
e, p = best
steps = [0.01, 0.3, 0.4, 0.3, 0.03, 0.03, 0.1]
for it in range(3):
    for i in range(len(p)):
        for d in (-steps[i], steps[i]):
            q = list(p)
            q[i] += d
            ee = err(*q)
            if ee < e:
                e, p = ee, q
eta, cR, cA, cF, cdaS, cdaM, cdaL = p
caps = {"RWD": cR, "AWD": cA, "FWD": cF}
cd = {"S": cdaS, "M": cdaM, "L": cdaL}
print("FIT rms %.1f %%: eta %.3f, launch cap RWD %.2f AWD %.2f FWD %.2f m/s2, CdA sport %.2f mid %.2f large %.2f" % (e * 100, eta, cR, cA, cF, cdaS, cdaM, cdaL))
for name, hp, kg, lay, cls, t60, vt, src in DATA:
    r = run(hp, kg, lay, cd[cls], eta, caps)
    print("%-28s 0-60 meas %.1f model %.2f | top meas %s model %.0f | %s" % (name, t60, r.get("60mph", 99), vt, top(hp, kg, cd[cls], eta), src))
open(_os.path.join(WORK, r"car_fit_params.txt"), "w").write(" ".join("%f" % x for x in p) + "\n")
