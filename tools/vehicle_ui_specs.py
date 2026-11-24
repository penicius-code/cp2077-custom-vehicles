"""Read the game's own stated vehicle specs (vehicleUIData: horsepower, mass, driveLayout, productionYear) from the
2.31 TweakDB text sources (<game>\\tools\\redmod\\tweaks\\{base,ep1}\\...\\vehicles\\**\\*.tweak), resolving inheritance.
Usage: python -I -X utf8 vehicle_ui_specs.py <out json>"""
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
# Folder for intermediate files (JSON dumps, fit parameters). Override with the environment variable VEHICLE_WORK.
WORK = _os.environ.get("VEHICLE_WORK", _os.path.join(_HERE, "work"))
# Game folder. Set the environment variable CP2077_DIR to your install.
GAME_DIR = _os.environ.get("CP2077_DIR", "")
import json, os, re, sys

GAME = _os.path.join(GAME_DIR, r"tools\redmod\tweaks")
LAYOUT = {"45370": "FWD", "45371": "RWD", "45372": "AWD"}   # inferred mapping (research agent, cross-checked)

rec_hdr = re.compile(r"^([A-Za-z_][\w]*)\s*:\s*([\w.]+)\s*$")
rec_hdr2 = re.compile(r"^([A-Za-z_][\w]*)\s*$")
recs = {}
for sub in ("base", "ep1"):
    root = os.path.join(GAME, sub)
    for dp, dn, fn in os.walk(root):
        if "vehicles" not in dp.lower():
            continue
        for f in fn:
            if not f.endswith(".tweak"):
                continue
            text = open(os.path.join(dp, f), encoding="utf-8", errors="replace").read()
            lines = text.splitlines()
            i = 0
            cur = None
            depth = 0
            buf = []
            while i < len(lines):
                ln = lines[i]
                s = ln.strip()
                if depth == 0:
                    m = rec_hdr.match(s) or rec_hdr2.match(s)
                    if m and not s.startswith(("package", "using")):
                        cur = m.group(1)
                        base = m.group(2) if m.lastindex and m.lastindex >= 2 else None
                        recs[cur] = {"base": base, "file": sub + "/" + f, "text": ""}
                        buf = []
                depth += ln.count("{") - ln.count("}")
                if cur:
                    buf.append(ln)
                    if depth == 0 and "}" in ln:
                        recs[cur]["text"] = "\n".join(buf)
                        cur = None
                i += 1

def ui_fields(b):
    def g(k):
        mm = re.search(r"\b%s\s*=\s*\"?([^;\"]+)\"?\s*;" % k, b)
        return mm.group(1).strip() if mm else None
    out = {}
    hp, mass, dl, yr = g("horsepower"), g("mass"), g("driveLayout"), g("productionYear")
    if hp: out["hp"] = float(hp.rstrip("f"))
    if mass: out["mass"] = float(mass.rstrip("f"))
    if dl: out["layout"] = LAYOUT.get(dl.split("#")[-1], dl)
    if yr: out["year"] = yr
    return out


def ui_record(name, depth=0):
    r = recs.get(name)
    if not r or depth > 8:
        return {}
    parent = ui_record(r["base"].split(".")[-1], depth + 1) if r["base"] else {}
    out = dict(parent)
    out.update(ui_fields(r["text"]))
    return out


def own_ui(r):
    t = r["text"]
    ref = re.search(r"vehicleUIData\s*=\s*\"Vehicle\.(\w+)\"", t)
    if ref:
        return ui_record(ref.group(1))
    m = re.search(r"vehicleUIData\s*=\s*\{(.*?)\}", t, re.S)
    if not m:
        return None
    b = m.group(1)
    def g(k):
        mm = re.search(r"\b%s\s*=\s*\"?([^;\"]+)\"?\s*;" % k, b)
        return mm.group(1).strip() if mm else None
    out = {}
    hp, mass, dl, yr = g("horsepower"), g("mass"), g("driveLayout"), g("productionYear")
    if hp: out["hp"] = float(hp.rstrip("f"))
    if mass: out["mass"] = float(mass.rstrip("f"))
    if dl:
        k = dl.split("#")[-1]
        out["layout"] = LAYOUT.get(k, dl)
    if yr: out["year"] = yr
    return out

def resolve(name, depth=0):
    r = recs.get(name)
    if not r or depth > 12:
        return {}
    base = r["base"]
    parent = resolve(base.split(".")[-1], depth + 1) if base else {}
    mine = own_ui(r) or {}
    out = dict(parent)
    out.update(mine)
    return out

res = {}
for name in recs:
    if name.startswith("v_") or name.startswith("q") or "_player" in name:
        ui = resolve(name)
        if ui.get("hp"):
            res["Vehicle." + name] = ui
json.dump(res, open(sys.argv[1], "w", encoding="utf-8"), indent=1, sort_keys=True)
print(len(recs), "records,", len(res), "with UI horsepower")
for k in ["Vehicle.v_sport2_porsche_911turbo", "Vehicle.v_sportbike2_arch", "Vehicle.v_standard25_mahir_supron", "Vehicle.v_sport1_rayfield_caliburn", "Vehicle.v_sportbike1_yaiba_kusanagi", "Vehicle.v_sportbike3_brennan_apollo"]:
    print(k, res.get(k))
