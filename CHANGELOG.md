# Changelog

Built on game version 2.31 unless a line says otherwise.

## Custom Vehicles

### 1.2.5 - 2026-11-23 (game 2.5)
- The after-load pass waits for a loaded save instead of running in the main menu.
- The log line for bikes shows the real previous top-gear value.

Tested in game, not extensively.

### 1.2.4 - 2026-11-23 (game 2.5)
- A CET "Reload all mods" no longer multiplies the bike rear grip a second time.

Tested in game, not extensively.

### 1.2.3 - 2026-11-02
- Top gear gets 7 % headroom above the planned top speed.
- Shift time of the superbikes 0.05 s.

Not benched.

### 1.2.2 - 2026-11-02
- Add-on bikes: burn-out friction floor 0.73 (was 0.1), shift time 0.08 s, rear grip factor 1.8.
- Console command `bikeShift(t)`.

Benched in game.

### 1.2.1 - 2026-11-02
- Bike rear grip raised by a factor of 1.6 after the bench showed wheelspin on launch.
- Console command `bikeGrip(f)`.

Benched in game.

### 1.2.0 - 2026-11-02
- `LIVE` pass: values are also written to the records a vehicle really uses when another mod has re-pointed it.
- The drivetrain constants in the plan are measured with Vehicle Bench instead of assumed.

Benched in game.

### 1.1.0 - 2026-11-02
- `REALISM` and `BIKES` passes: torque, gear bands and drag from a generated plan, on the true speed scale.

### 1.0.0 - 2026-11-02
- First version: `CLONES` (add-on vehicles copied from a vanilla record use the tuned engine and drive model of their base) and `SCALED` (add-on vehicles with their own engine).

Confirmed in game.

## Vehicle Bench

### 1.2.1 - 2026-11-23 (game 2.5)
- The first frame of a run is no longer counted twice, so the 0-60, 0-100 and 0-200 times are about one frame shorter.

Tested in game, not extensively. The version string inside the script still reads 1.2.0.

### 1.2.0 - 2026-11-02
- Off at every game start; armed by hotkey or console command.

### 1.1.1 - 2026-11-02
- Logs weight transfer and tyre grip values.

### 1.1.0 - 2026-11-02
- Each run logs the records the vehicle really uses, and a speed trace (time, true speed, gear, rpm every 0.25 s) is written to `trace.csv`.

### 1.0.0 - 2026-11-02
- First version: 0-100 and 0-200 km/h times and top speed, in true speed and speedometer speed, written to `bench.csv`.
