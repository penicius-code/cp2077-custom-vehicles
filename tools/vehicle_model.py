"""Longitudinal model of the game's drivetrain tables (CVOO modules, Arch V4 bikes) and a real-world model.

Game side (assumed structure, to be checked with CyberslopVehicleBench logs):
  a(v) = K * T * tm_gear(v) / m  -  D * airResistanceFactor * v^2 / m
  gear shift at the gear's maxSpeed, dead time SHIFT s, top speed = min(drag equilibrium, top gear maxSpeed)
  v in true m/s (the HUD shows v * speed_to_multiplier, not v).
Real side: point mass, drivetrain efficiency, drag area, rolling resistance, traction / wheelie limited launch.
"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import math

G = 9.81
RHO = 1.2
SHIFT = 0.25


# ----------------------------------------------------------------- game side
def sim_game(T, gears, m, drag, K, D, dt=0.005, shift=SHIFT, horizon=60.0, tmax=240.0, marks=None):
    """gears: list of (minSpeed, maxSpeed, tm) forward gears, ascending. Returns dict of times (s) and top speed (m/s)."""
    top_cap = max(g[1] for g in gears)
    v = 0.0
    t = 0.0
    gi = 0
    dead = 0.0
    if marks is None:
        marks = {"60mph": 26.8224, "100": 100 / 3.6, "150": 150 / 3.6, "200": 200 / 3.6}
    times = {}
    while t < tmax:
        g = gears[gi]
        if dead > 0:
            dead -= dt
            f = 0.0
        else:
            f = K * T * g[2] / m
        a = f - D * drag * v * v / m
        v += a * dt
        t += dt
        if v < 0:
            v = 0.0
        for k, vm in marks.items():
            if k not in times and v >= vm:
                times[k] = t
        if gi < len(gears) - 1 and v >= g[1]:
            gi += 1
            dead = shift
        if v >= top_cap:
            v = top_cap
            if t > horizon and abs(a) < 0.01:
                break
        if t > horizon and a < 0.01:
            break
    return dict(times=times, top=min(v, top_cap), cap=top_cap)


def gears_from_cvoo(row):
    out = []
    for k in sorted(row["gears"], key=lambda x: int(x)):
        g = row["gears"][k]
        if "gearsMaxSpeed" in g and "gearsTorqueMult" in g:
            out.append((g.get("gearsMinSpeed", 0.0), g["gearsMaxSpeed"], g["gearsTorqueMult"]))
    return out


# ----------------------------------------------------------------- real side
def sim_real(hp, mass_kg, cda, eta=0.88, crr=0.012, a_max=10.5, shift=0.15, rider=0.0, vtop_limit=None, dt=0.005, gearing_loss=0.97):
    """Power-limited / traction-limited launch. Returns times (s) for 100/200 km/h and top speed (m/s)."""
    P = hp * 745.7 * eta
    m = mass_kg + rider
    v = 0.0
    t = 0.0
    times = {}
    marks = {"60mph": 26.8224, "100": 100 / 3.6, "150": 150 / 3.6, "200": 200 / 3.6}
    # shifts: lose `shift` seconds at ~ every 22 % of the speed range (approximate, 5 shifts to 200 km/h)
    shifts = [12, 20, 29, 38, 47, 57, 66, 76]
    si = 0
    dead = 0.0
    while t < 120:
        drag = 0.5 * RHO * cda * v * v + crr * m * G
        powered = dead <= 0
        if dead > 0:
            dead -= dt
            a = -drag / m
        else:
            p_a = (P * gearing_loss / max(v, 1.0)) / m
            a = min(a_max, p_a) - drag / m
        v += a * dt
        t += dt
        for k, vm in marks.items():
            if k not in times and v >= vm:
                times[k] = t
        if si < len(shifts) and v >= shifts[si]:
            si += 1
            dead = shift
        if powered and a < 0.002 and v > 5:
            break
        if vtop_limit and v >= vtop_limit:
            v = vtop_limit
            break
    return dict(times=times, top=v)
