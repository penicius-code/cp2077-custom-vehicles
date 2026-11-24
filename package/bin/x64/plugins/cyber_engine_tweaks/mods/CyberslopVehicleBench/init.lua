-- ============================================================
--  Cyberslop Vehicle Bench 1.2.1 (2026-11-02; 1.2.1 2026-11-23: the start frame's dt is no longer counted twice,
--  so 0-60 / 0-100 / 0-200 times are ~1 frame (8-16 ms) shorter and correct)
--  1.2.0: OFF at every launch, so normal driving costs nothing. Arm it with the CET hotkey
--  "Vehicle Bench: arm / disarm" or GetMod("CyberslopVehicleBench").arm() in the console; it stays armed until
--  disarmed or the game restarts.
--  Measures what a vehicle really does in the game: 0-100 / 0-200 times from a standstill and top speed.
-- ============================================================
-- Why: the drivetrain physics is native, so 0-100 km/h and top speed cannot be read from TweakDB. This mod times it.
-- The in-game speedometer shows speed x a curve (vehicle_ui / speed_to_multiplier), not true speed, so BOTH are logged:
--   true   = VehicleObject:GetCurrentSpeed() in m/s (x3.6 = km/h): the physical speed the engine simulates
--   shown  = what the speedometer prints (same call the HUD makes)
-- How to use: stop the car, then floor it on a long straight road and keep it floored until top speed; brake to a stop for the next run.
-- Every run is written to CyberslopVehicleBench.log and bench.csv (next to init.lua), one line per run, per vehicle record.
-- A run starts when the car moves off after standing still for 0.5 s. Do not use slow-motion (Kerenzikov / Sandevistan) while testing.
-- Console: GetMod("CyberslopVehicleBench").status(), GetMod("CyberslopVehicleBench").chain() (live records of the mounted vehicle)
-- 1.1.0: each run also logs the LIVE record chain (which engine / gears / drive model the vehicle really points at, with
-- torque, gear bands and drag; other mods such as Authentic Shift repoint vehicles to their own clones) and writes a
-- speed trace (every 0.25 s: time, true speed, gear, rpm) to trace.csv, so a plateau can be told from the end of the road.

local VERSION = "1.2.0"
local M = { version = VERSION }

local TH_TRUE = { { "0-60mph", 26.8224 }, { "0-100", 100 / 3.6 }, { "0-150", 150 / 3.6 }, { "0-200", 200 / 3.6 } }
local TH_SHOWN = { { "0-100s", 100 }, { "0-200s", 200 } }
local STAND = 0.25          -- m/s below this counts as standing
local MOVE = 0.6            -- m/s above this starts a run
local STAND_TIME = 0.5      -- s of standing before a run can start

local vPrev = 0.0
local armed = false
local st = { standT = 0.0, running = false, t = 0.0, topTrue = 0.0, topShown = 0, times = {}, rec = "?", last = {}, tried = false, csvOk = true }

local function rec(veh)
    local ok, s = pcall(function() return TDBID.ToStringDEBUG(veh:GetRecordID()) end)
    if ok and s and s ~= "" then return s end
    return "unknown"
end

local function shown(v)
    local ok, r = pcall(function()
        local m = Game.GetStatsDataSystem():GetValueFromCurve("vehicle_ui", v, "speed_to_multiplier")
        return math.floor(v * m + 0.5)
    end)
    if ok then return r end
    return nil
end

local function idStr(id)
    if id == nil then return "nil" end
    local ok, s = pcall(function() return TDBID.ToStringDEBUG(id) end)
    if ok and s and s ~= "" then return s end
    return tostring(id)
end

local function flat(id, prop)
    local ok, v = pcall(function() return TweakDB:GetFlat(TweakDBID.new(id, prop)) end)
    if ok then return v end
    return nil
end

local function num(v)
    if type(v) == "number" then return string.format("%.4g", v) end
    return tostring(v)
end

-- The records the vehicle uses right now, resolved through its own pointers.
local function chainOfId(recId)
    local out = {}
    local eng = flat(recId, ".vehEngineData")
    out[#out + 1] = "engine " .. idStr(eng)
    if eng ~= nil then
        out[#out + 1] = "torque " .. num(flat(eng, ".engineMaxTorque"))
        out[#out + 1] = "rpm " .. num(flat(eng, ".minRPM")) .. "-" .. num(flat(eng, ".maxRPM"))
        local gears = flat(eng, ".gears")
        if type(gears) == "table" then
            local g = {}
            for i, gid in ipairs(gears) do
                g[#g + 1] = string.format("%d:%s[%s-%s x%s]", i - 1, idStr(gid), num(flat(gid, ".minSpeed")),
                    num(flat(gid, ".maxSpeed")), num(flat(gid, ".torqueMultiplier")))
            end
            out[#out + 1] = "gears " .. table.concat(g, " ")
        end
    end
    local dm = flat(recId, ".bikeDriveModelData")
    local dmProp = "bike"
    local okDm = dm ~= nil and pcall(function() return TweakDB:GetRecord(dm) end) and TweakDB:GetRecord(dm) ~= nil
    if not okDm then dm = flat(recId, ".vehDriveModelData"); dmProp = "car" end
    out[#out + 1] = "drive(" .. dmProp .. ") " .. idStr(dm)
    if dm ~= nil then
        out[#out + 1] = "drag " .. num(flat(dm, ".airResistanceFactor"))
        out[#out + 1] = "mass " .. num(flat(dm, ".total_mass"))
        -- 1.1.1: traction inputs (CVOO sets bike weight transfer to 0.01; CyberslopCustomVehicles 1.2.1 raises bike rear grip)
        out[#out + 1] = "weightTransfer " .. num(flat(dm, ".forwardWeightTransferFactor"))
        local ws = flat(dm, ".wheelSetup")
        if ws ~= nil then
            local fr, rr = flat(ws, ".frontPreset"), flat(ws, ".backPreset")
            out[#out + 1] = string.format("grip long F %s R %s (rear %s)", num(fr and flat(fr, ".frictionMulLongitudinal")),
                num(rr and flat(rr, ".frictionMulLongitudinal")), idStr(rr))
        end
    end
    return "chain " .. idStr(recId) .. " | " .. table.concat(out, " | ")
end

local function chainOf(veh)
    local okR, recId = pcall(function() return veh:GetRecordID() end)
    if not okR or recId == nil then return "chain: no record id" end
    return chainOfId(recId)
end

-- Logged once per session after load, so the live chain is known even without driving them.
local WATCH = {
    "Vehicle.v_sport2_quadra_type66_02_player", "Vehicle.v_sport2_quadra_type66_player",
    "Vehicle.v_sportbike1_yaiba_kusanagi_player", "Vehicle.v_sportbike2_arch_tyger_player",
    "Vehicle.v_sportbike2_arch_player", "Vehicle.v_arch_v4valor_carbon", "Vehicle.v_arch_v4valor",
    "Vehicle.v_sport1_yaiba_semimaru_player",
}
local watchLogged = false
local function logWatch()
    for _, name in ipairs(WATCH) do
        local id = TweakDBID.new(name)
        local okRec = pcall(function() return TweakDB:GetRecord(id) end) and TweakDB:GetRecord(id) ~= nil
        if okRec then
            local ok, line = pcall(chainOfId, id)
            spdlog.info(ok and line or ("chain failed " .. name .. ": " .. tostring(line)))
        else
            spdlog.info("chain " .. name .. ": no such record")
        end
    end
end

function M.chain()
    local player = Game.GetPlayer()
    local veh = player and Game.GetMountedVehicle(player)
    if not veh then print("[CyberslopVehicleBench] not in a vehicle"); return end
    local line = chainOf(veh)
    print(line)
    spdlog.info(line)
end

local function gearRpm(veh)
    local ok, g, r = pcall(function()
        local bb = veh:GetBlackboard()
        local defs = GetAllBlackboardDefs().Vehicle
        return bb:GetInt(defs.GearValue), bb:GetFloat(defs.RPMValue)
    end)
    if ok then return g, r end
    return nil, nil
end

local trace = { f = nil, next = 0.0 }

local function traceStart(veh)
    trace.f = io.open("trace.csv", "a")
    trace.next = 0.0
    if trace.f then
        trace.f:write(string.format("# run %s %s\n", os.date("%Y-%m-%d %H:%M:%S"), st.rec))
    end
end

local function traceStep(veh, v)
    if not trace.f or st.t < trace.next then return end
    trace.next = trace.next + 0.25
    local g, r = gearRpm(veh)
    trace.f:write(string.format("%.2f,%.3f,%s,%s\n", st.t, v, tostring(g or ""), r and string.format("%.0f", r) or ""))
end

local function traceEnd()
    if trace.f then trace.f:close() end
    trace.f = nil
end

local function finish(reason)
    if not st.running then return end
    st.running = false
    traceEnd()
    if st.topTrue < 5 then return end
    local parts = {}
    for _, th in ipairs(TH_TRUE) do
        parts[#parts + 1] = string.format("%s=%s", th[1], st.times[th[1]] and string.format("%.2f", st.times[th[1]]) or "-")
    end
    for _, th in ipairs(TH_SHOWN) do
        parts[#parts + 1] = string.format("%s=%s", th[1], st.times[th[1]] and string.format("%.2f", st.times[th[1]]) or "-")
    end
    local line = string.format("%s | %s | top true %.1f m/s (%.0f km/h) shown %s | %s",
        st.rec, table.concat(parts, " "), st.topTrue, st.topTrue * 3.6, tostring(st.topShown), reason)
    spdlog.info(line)
    st.last[#st.last + 1] = line
    if #st.last > 30 then table.remove(st.last, 1) end
    local f = io.open("bench.csv", "a")
    if f then
        f:write(string.format("%s,%s,%.3f,%s,%s,%s,%s,%s,%.2f,%s\n", os.date("%Y-%m-%d %H:%M:%S"), st.rec,
            st.topTrue, tostring(st.topShown),
            tostring(st.times["0-60mph"] or ""), tostring(st.times["0-100"] or ""), tostring(st.times["0-150"] or ""),
            tostring(st.times["0-200"] or ""), st.t, reason))
        f:close()
    end
end

function M.arm(on)
    if on == nil then on = not armed end
    if not on and st.running then finish("disarmed") end
    armed = on
    st.standT = 0.0
    vPrev = 0.0
    local msg = "[CyberslopVehicleBench " .. VERSION .. "] " .. (armed and "ARMED: stop, then floor it" or "off")
    print(msg)
    spdlog.info(msg)
    return armed
end

registerHotkey("vehicle_bench_arm", "Vehicle Bench: arm / disarm", function() M.arm() end)

function M.status()
    print("[CyberslopVehicleBench " .. VERSION .. "] last runs:")
    for _, l in ipairs(st.last) do print("  " .. l) end
end

-- Once per session: write the speedometer curve (speed -> multiplier -> shown value) to the log.
local curveLogged, curveTries = false, 0
local function logCurve()
    local parts = {}
    for v = 0, 100, 5 do
        local ok, m = pcall(function() return Game.GetStatsDataSystem():GetValueFromCurve("vehicle_ui", v, "speed_to_multiplier") end)
        if not ok or m == nil then return false end
        parts[#parts + 1] = string.format("%d m/s -> x%.3f = %d shown", v, m, math.floor(v * m + 0.5))
    end
    spdlog.info("speedometer curve: " .. table.concat(parts, "; "))
    return true
end

registerForEvent("onUpdate", function(dt)
    if not armed then return end
    local player = Game.GetPlayer()
    if not player then return end
    if not curveLogged and curveTries < 30 then
        curveTries = curveTries + 1
        curveLogged = logCurve()
    end
    if not watchLogged then
        watchLogged = true
        local ok, err = pcall(logWatch)
        if not ok then spdlog.info("watch list failed: " .. tostring(err)) end
    end
    local veh = Game.GetMountedVehicle(player)
    if not veh then
        if st.running then finish("dismounted") end
        st.standT = 0.0
        return
    end
    local ok, v = pcall(function() return veh:GetCurrentSpeed() end)
    if not ok or v == nil then return end
    v = math.abs(v)
    local vLast = vPrev
    vPrev = v

    if not st.running then
        if v < STAND then
            st.standT = st.standT + dt
        elseif v > MOVE and st.standT >= STAND_TIME then
            st.running = true
            local aEst = (v - vLast) / dt                      -- the run really began v / a seconds before this frame
            -- v / aEst already reaches the end of this frame; the common "+ dt" below adds this frame again
            st.t = math.max(0.0, ((aEst > 0.5) and (v / aEst) or 0.0) - dt)
            st.topTrue = 0.0
            st.topShown = 0
            st.times = {}
            st.rec = rec(veh)
            local okC, line = pcall(chainOf, veh)
            spdlog.info(okC and line or ("chain failed: " .. tostring(line)))
            traceStart(veh)
        else
            if v > MOVE then st.standT = 0.0 end
        end
        if not st.running then return end
    end

    st.t = st.t + dt
    if v > st.topTrue then st.topTrue = v end
    traceStep(veh, v)
    local s = shown(v)
    if s and s > st.topShown then st.topShown = s end
    for _, th in ipairs(TH_TRUE) do
        if not st.times[th[1]] and v >= th[2] then st.times[th[1]] = st.t end
    end
    if s then
        for _, th in ipairs(TH_SHOWN) do
            if not st.times[th[1]] and s >= th[2] then st.times[th[1]] = st.t end
        end
    end
    -- run ends when the car stops again (after a launch) or after a long run
    if v < STAND and st.t > 2.0 then
        finish("stopped")
        st.standT = 0.0
    elseif st.t > 150 then
        finish("timeout")
        st.standT = 0.0
    end
end)

return M
