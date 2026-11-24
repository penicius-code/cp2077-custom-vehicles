"""Empirical 0-60 mph fit for cars: t60 = max(floor[layout], c * (kg_per_hp) ** b), fitted on measured road tests.
0-100 km/h = t60 * 1.05. Top speed: physics with CdA per body class (car_fit.py). Usage: python -I -X utf8 car_fit2.py"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import math
import importlib.util, sys
sys.path.insert(0, _HERE)

DATA = [  # name, hp, curb kg, layout, 0-60 measured
    ("Acura NSX NA1 1991", 270, 1365, "RWD", 5.5), ("Toyota Supra A80 Turbo", 320, 1565, "RWD", 5.0),
    ("Dodge Charger Hellcat", 707, 2069, "RWD", 3.7), ("Mustang GT500 2020", 760, 1915, "RWD", 3.6),
    ("Porsche 911 Turbo S 992", 640, 1640, "AWD", 2.2), ("Subaru WRX STI 2019", 310, 1530, "AWD", 4.8),
    ("Honda Civic Type R FL5", 315, 1430, "FWD", 5.0), ("VW Golf GTI Mk7", 220, 1360, "FWD", 5.9),
    ("Toyota Corolla 2.0 2020", 169, 1350, "FWD", 7.6), ("Mazda MX-5 ND2", 181, 1060, "RWD", 5.7),
    ("Chevrolet Suburban 5.3", 355, 2600, "AWD", 7.1), ("Ford F-150 5.0", 400, 2250, "AWD", 5.9),
    ("Bugatti Chiron", 1479, 1996, "AWD", 2.4), ("Rimac Nevera", 1914, 2300, "AWD", 1.8),
    ("Porsche 930 Turbo 3.3", 300, 1300, "RWD", 5.3), ("Fiat 500 1.2", 69, 940, "FWD", 12.5),
    ("Toyota Camry V6 2018", 301, 1600, "FWD", 5.8), ("Jeep Wrangler 3.6", 285, 2000, "AWD", 6.9),
    ("Chevrolet Corvette C8", 495, 1530, "RWD", 2.9), ("Ford Transit 3.5 EcoBoost van", 310, 2400, "RWD", 7.4),
]


def t60(hp, kg, lay, c, b, floors):
    return max(floors[lay], c * (kg / hp) ** b)


best = None
for c in [x / 100 for x in range(80, 260, 5)]:
    for b in [x / 100 for x in range(55, 110, 3)]:
        for fR in [2.6, 2.8, 3.0, 3.2]:
            for fA in [1.8, 2.0, 2.2]:
                for fF in [4.6, 4.9, 5.2]:
                    fl = {"RWD": fR, "AWD": fA, "FWD": fF}
                    e = math.sqrt(sum(((t60(h, k, l, c, b, fl) - t) / t) ** 2 for _, h, k, l, t in DATA) / len(DATA))
                    if best is None or e < best[0]:
                        best = (e, c, b, fl)
e, c, b, fl = best
print("FIT rms %.1f %%: t60 = max(floor, %.2f * (kg/hp)^%.2f), floors %s" % (e * 100, c, b, fl))
for n, h, k, l, t in DATA:
    print("  %-28s meas %.1f  model %.2f" % (n, t, t60(h, k, l, c, b, fl)))
open(_os.path.join(WORK, r"car_fit2_params.txt"), "w").write("%f %f %f %f %f\n" % (c, b, fl["RWD"], fl["AWD"], fl["FWD"]))
