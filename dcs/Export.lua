--[[--------------------------------------------------------------------
  dcs/Export.lua — 多端 DCS 外设 · P0 最小导出脚本

  作用：每帧把本机的姿态与飞行数据，按 JSON 行发到 127.0.0.1:5010。
        线格式与 tools/mock_export.py 完全一致，所以桥接服务和客户端
        可以用 mock 开发，接真机时一行代码都不用改。

  安装：
      复制到
        %USERPROFILE%\Saved Games\DCS\Scripts\Export.lua
        %USERPROFILE%\Saved Games\DCS.openbeta\Scripts\Export.lua
      如果该文件已存在（比如装了 DCS-BIOS / DCS-ExportScripts），
      **不要覆盖**，而是把本文件的 LuaExportAfterNextFrame 内容并进去。

  依赖：
      LuaSocket。DCS 一般自带；若日志里报 "socket module not found"，
      把 LuaSocket 的 socket.dll / mime.dll / lua\socket 目录放到
      Saved Games\DCS\Scripts\ 下即可。

  注意：
      1) 全部逻辑包在 pcall 里，出错只记日志，绝不让脚本影响游戏。
      2) 部分多人服务器会限制导出（MissionScripting 的导出白名单 /
         Pure Client 校验），此时本脚本可能收不到数据，属于预期内。
      3) 端口只绑本机，不做任何网络暴露。跨网由桥接服务负责。
----------------------------------------------------------------------]]

-- ============================ 配置 ============================

local CFG = {
    host     = "127.0.0.1",   -- 只发本机
    port     = 5010,
    rate     = 60,            -- 目标发送频率 Hz
    max_log  = 5,             -- 同类错误最多记几条，防止刷爆日志
}

local LOG_TAG = "DCSMultiPeriph"

-- ============================ 环境 ============================

local udp = nil
local send_ok = false
local err_count = 0
local frame_no = 0
local last_t = -1
-- 慢变量包的上一次发送时间（模型时间）。-1e9 保证第一帧就发一次，
-- 不用干等 1 秒才看到燃油读数。
local last_sys_t = -1e9

-- 令牌桶节流。
--
-- 为什么不用「t - last_sent < interval 就跳过」这种写法：
-- 仿真时间是浮点累加出来的，每帧的 dt 与 1/60 只差 1e-16，但比较时会
-- 被判成「还没到点」，于是成批丢帧 —— 实测 60 帧能丢掉 15 帧。
-- 更糟的是当实际帧率略高于目标帧率时（比如 65fps），每个间隔都差一点点，
-- 会导致隔帧发送，直接掉到 32Hz。
--
-- 令牌桶按 dt 累积配额，平均频率准确，且不会有节拍性丢帧。
local tokens = 1.0
local TOKEN_CAP = 2.0        -- 最多攒 2 个，允许一次小突发，防止追帧风暴

local function log_info(msg)
    if log and log.write then
        pcall(log.write, LOG_TAG, log.INFO, msg)
    end
end

local function log_warn(msg)
    if log and log.write then
        pcall(log.write, LOG_TAG, log.WARNING, msg)
    end
end

local function log_error(msg)
    if err_count >= CFG.max_log then return end
    err_count = err_count + 1
    if log and log.write then
        pcall(log.write, LOG_TAG, log.ERROR, msg)
    end
    if err_count == CFG.max_log then
        log_warn(string.format("后续同类错误不再记录（已记 %d 条）", CFG.max_log))
    end
end

-- ============================ 数值格式化 ============================

-- DCS 偶尔会返回 NaN / Inf（例如某些机型的地面状态）。
-- 这些值一旦进入 JSON 会变成 nan / inf，下游解析器直接崩。
-- 统一在这里清成 0，并且用 valid 标记让下游知道「这一帧有脏数据」。
local dirty = false

local function num(v, fmt)
    if v == nil then dirty = true; return "0" end
    local t = type(v)
    if t ~= "number" then dirty = true; return "0" end
    if v ~= v then dirty = true; return "0" end              -- NaN
    if v == math.huge or v == -math.huge then dirty = true; return "0" end
    return string.format(fmt, v)
end

-- ============================ 取数 ============================

-- LoGet* 返回的是嵌套表，各机型结构可能不同，取值一律带存在性检查。
-- 提到文件级是因为主帧和慢变量包都要用。
local function deepget(t, k1, k2)
    if type(t) ~= "table" then return nil end
    local a = t[k1]
    if k2 == nil then return a end
    if type(a) ~= "table" then return nil end
    return a[k2]
end

-- 有些项在不同机型上是「一个数」也可能是「带 .value 的表」，两种都认
local function val(t, k)
    local a = deepget(t, k)
    if type(a) == "number" then return a end
    if type(a) == "table" then return a.value end
    return nil
end

local function safe_call(fn, ...)
    local ok, a, b, c = pcall(fn, ...)
    if ok then return a, b, c end
    return nil
end

local function collect()
    dirty = false

    local sd = safe_call(LoGetSelfData) or {}

    local alt  = safe_call(LoGetAltitudeAboveSeaLevel) or 0
    local agl  = safe_call(LoGetAltitudeAboveGroundLevel) or 0
    local ias  = safe_call(LoGetIndicatedAirSpeed) or 0
    local tas  = safe_call(LoGetTrueAirSpeed) or 0
    local vs   = safe_call(LoGetVerticalVelocity) or 0
    local mach = safe_call(LoGetMachNumber) or (ias / 295.0)
    local aoa  = safe_call(LoGetAngleOfAttack)

    local g = 1.0
    local acc = safe_call(LoGetAccelerationUnits)
    if type(acc) == "table" and acc.y then g = acc.y end

    -- 以下的表结构是探针实测出来的（各机型可能不同），全部做存在性检查
    local eng  = safe_call(LoGetEngineInfo)  or {}
    local mech = safe_call(LoGetMechInfo)    or {}
    local pay  = safe_call(LoGetPayloadInfo) or {}

    local function deep(t, k1, k2) return deepget(t, k1, k2) end

    return {
        alt   = alt,
        agl   = agl,
        ias   = ias,
        gs    = tas,
        vs    = vs,
        pitch = sd.Pitch or 0,
        bank  = sd.Bank or 0,
        hdg   = sd.Heading or 0,
        g     = g,
        mach  = mach,

        aoa      = aoa,
        rpm_l    = deep(eng, "RPM", "left"),
        rpm_r    = deep(eng, "RPM", "right"),
        temp_l   = deep(eng, "Temperature", "left"),
        temp_r   = deep(eng, "Temperature", "right"),
        fuel     = eng.fuel_internal,
        fuel_ext = eng.fuel_external,
        gear     = deep(mech, "gear", "value"),
        flaps    = deep(mech, "flaps", "value"),
        sbrake   = deep(mech, "speedbrakes", "value"),
        shells   = deep(pay, "Cannon", "shells"),
    }
end

-- 慢变量：燃油、温度、液压、舵面…… 1Hz 单独发一包。
--
-- 为什么不塞进主帧：主帧是 60Hz 的实时仪表数据，字段越少解析越快；
-- 这些量一秒变不了几次，混进去只是让每帧白白变大一倍。
-- 包格式是 {"sys":{...}}，桥接端靠这个 key 认出来，不会当成一帧遥测。
local function collect_sys()
    local eng  = safe_call(LoGetEngineInfo) or {}
    local mech = safe_call(LoGetMechInfo)   or {}
    return {
        fuel   = eng.fuel_internal,
        fuelx  = eng.fuel_external,
        rpm_l  = deepget(eng, "RPM", "left"),
        rpm_r  = deepget(eng, "RPM", "right"),
        temp_l = deepget(eng, "Temperature", "left"),
        temp_r = deepget(eng, "Temperature", "right"),
        hyd_l  = deepget(eng, "HydraulicPressure", "left"),
        hyd_r  = deepget(eng, "HydraulicPressure", "right"),
        canopy = val(mech, "canopy"),
        wbrake = val(mech, "wheelbrakes"),
        -- 舵面实际偏度。注意这是「配平 + 杆量」的合成，不是配平本身：
        -- DCS 的 Export API 不提供配平位置（见 docs/PANEL.md）。
        cs_a   = deepget(mech, "controlsurfaces", "eleron"),
        cs_e   = deepget(mech, "controlsurfaces", "elevator"),
        cs_r   = deepget(mech, "controlsurfaces", "rudder"),
    }
end

local function encode_sys(d, t)
    local p = {
        '"t":'     .. num(t, "%.2f"),
        -- 燃油用 2 位：单位是 kg，实际值上千，1 位在长时间飞行里会明显漂
        '"fuel":'  .. num(d.fuel,   "%.2f"),
        '"fuelx":' .. num(d.fuelx,  "%.2f"),
        '"rpm_l":' .. num(d.rpm_l,  "%.1f"),
        '"rpm_r":' .. num(d.rpm_r,  "%.1f"),
        '"temp_l":'.. num(d.temp_l, "%.2f"),
        '"temp_r":'.. num(d.temp_r, "%.2f"),
        '"hyd_l":' .. num(d.hyd_l,  "%.1f"),
        '"hyd_r":' .. num(d.hyd_r,  "%.1f"),
        '"canopy":'.. num(d.canopy, "%.3f"),
        '"wbrake":'.. num(d.wbrake, "%.3f"),
        '"cs_a":'  .. num(d.cs_a,   "%.4f"),
        '"cs_e":'  .. num(d.cs_e,   "%.4f"),
        '"cs_r":'  .. num(d.cs_r,   "%.4f"),
    }
    return '{"sys":{' .. table.concat(p, ",") .. '}}'
end

local function encode(d, t)
    -- 字段顺序固定，方便对比 mock 与真机的输出。
    -- 用拼表而不是一大串 format：字段一多，format 的参数错位根本看不出来。
    local p = {
        '"t":'      .. num(t,       "%.3f"),
        '"alt":'    .. num(d.alt,   "%.2f"),
        '"agl":'    .. num(d.agl,   "%.2f"),
        '"ias":'    .. num(d.ias,   "%.2f"),
        '"gs":'     .. num(d.gs,    "%.2f"),
        '"vs":'     .. num(d.vs,    "%.2f"),
        '"pitch":'  .. num(d.pitch, "%.5f"),
        '"bank":'   .. num(d.bank,  "%.5f"),
        '"hdg":'    .. num(d.hdg,   "%.5f"),
        '"g":'      .. num(d.g,     "%.2f"),
        '"mach":'   .. num(d.mach,  "%.3f"),
        '"aoa":'    .. num(d.aoa,    "%.4f"),
        '"rpm_l":'  .. num(d.rpm_l,  "%.1f"),
        '"rpm_r":'  .. num(d.rpm_r,  "%.1f"),
        '"temp_l":' .. num(d.temp_l, "%.1f"),
        '"temp_r":' .. num(d.temp_r, "%.1f"),
        '"fuel":'   .. num(d.fuel,   "%.3f"),
        '"fuelx":'  .. num(d.fuel_ext, "%.3f"),
        '"gear":'   .. num(d.gear,   "%.3f"),
        '"flaps":'  .. num(d.flaps,  "%.3f"),
        '"sbrk":'   .. num(d.sbrake, "%.3f"),
        '"shells":' .. num(d.shells, "%.0f"),
    }
    -- dirty 由上面的 num() 置位，所以要全部算完再判断
    if dirty then p[#p + 1] = '"dirty":true' end
    return "{" .. table.concat(p, ",") .. "}"
end

-- ============================ 加载 LuaSocket ============================

-- DCS 的 LuaSocket 和标准发行版不一样，这一点非常容易踩坑：
--
--   DCS World\LuaSocket\socket.lua   ← 只有纯 Lua 包装层
--   DCS World\bin\lua-socket.dll     ← 编译好的 C 模块
--
-- 直接 require("socket") 会先命中那个包装层，而它内部要 require("socket.core")，
-- 可 DCS 里根本没有 core.dll（模块名被改成了 lua-socket）。
-- 所以必须绕过包装层，用 package.loadlib 直接调 DLL 里的 luaopen_socket。
--
-- 路径不硬编码：从 package.cpath 的模板里把 "?" 换成 "socket"，
-- 因为 DCS 的 cpath 形如 "...\bin\lua-?.dll"，替换后正好得到 lua-socket.dll。
local function load_socket()
    local tried = {}

    -- 1) 先按常规来，某些 DCS 版本/某些环境里它是通的
    local ok, mod = pcall(require, "socket")
    if ok and type(mod) == "table" and mod.udp then
        return mod, "require(socket)"
    end
    tried[#tried + 1] = "require(socket): " .. tostring(mod)

    -- 2) 直接 loadlib
    local cpath = package.cpath or ""
    for tmpl in cpath:gmatch("[^;]+") do
        for _, sub in ipairs({ "socket", "lua-socket" }) do
            local path = tmpl:gsub("%?", sub)
            for _, sym in ipairs({ "luaopen_socket", "luaopen_socket_core" }) do
                local ok2, f = pcall(package.loadlib, path, sym)
                if ok2 and type(f) == "function" then
                    local ok3, m = pcall(f)
                    if ok3 and type(m) == "table" and m.udp then
                        return m, "loadlib(" .. path .. ", " .. sym .. ")"
                    end
                    tried[#tried + 1] = path .. "|" .. sym .. ": " .. tostring(m)
                end
            end
        end
    end

    return nil, table.concat(tried, " ; ")
end

-- ============================ 结构探针 ============================

-- LoGetEngineInfo / LoGetMechInfo / LoGetPayloadInfo 返回的是嵌套表，
-- 各机型字段还不完全一样，网上没有可靠文档。与其猜，不如开局时把真实结构
-- 打进日志，照着写编码器。只在启动时跑一次，对性能没有影响。
local function describe_table(name, fn, max_keys)
    local ok, t = pcall(fn)
    if not ok then
        log_info(name .. " -> 调用失败: " .. tostring(t))
        return
    end
    if type(t) ~= "table" then
        log_info(name .. " -> " .. type(t) .. ": " .. tostring(t))
        return
    end

    local parts, n = {}, 0
    for k, v in pairs(t) do
        n = n + 1
        if max_keys and n > max_keys then
            parts[#parts + 1] = "..."
            break
        end
        local desc
        if type(v) == "table" then
            local sub = {}
            for k2 in pairs(v) do
                sub[#sub + 1] = tostring(k2)
                if #sub >= 8 then break end
            end
            desc = "table{" .. table.concat(sub, ",") .. "}"
        else
            desc = type(v) .. "=" .. tostring(v)
        end
        parts[#parts + 1] = tostring(k) .. ":" .. desc
    end
    log_info(name .. " = {" .. table.concat(parts, ", ") .. "}")
end

-- ============================ 发送 ============================

local function send_frame()
    if not send_ok or not udp then return end

    local t = safe_call(LoGetModelTime) or 0

    -- dt 上限 0.25s：游戏暂停、加载地形、切出窗口回来时，模型时间会跳一大截，
    -- 不设上限就会一口气补发一大串过期帧，把桥接端的队列打爆。
    local dt = t - last_t
    if dt < 0 then dt = 0 end
    if dt > 0.25 then dt = 0.25 end
    last_t = t

    tokens = tokens + dt * CFG.rate
    if tokens > TOKEN_CAP then tokens = TOKEN_CAP end
    if tokens < 1.0 then return end
    tokens = tokens - 1.0

    local data = collect()
    local payload = encode(data, t)

    -- settimeout(0) 之后 sendto 不会阻塞；失败也不关心，UDP 本来就是尽力而为
    udp:sendto(payload, CFG.host, CFG.port)

    -- 慢变量包：1 秒一次。用模型时间而不是墙钟，暂停时跟着一起停，
    -- 免得暂停期间还在发「燃油没变」的重复包。
    if t - last_sys_t >= 1.0 then
        last_sys_t = t
        -- 放在主帧之后：num() 会置 dirty，这里置脏不会影响已经发出去的主帧，
        -- 而下一帧 collect() 开头会把它清掉。
        udp:sendto(encode_sys(collect_sys(), t), CFG.host, CFG.port)
    end
end

-- ============================ 生命周期 ============================

function LuaExportStart()
    frame_no = 0
    err_count = 0
    dirty = false
    last_t = -1
    last_sys_t = -1e9
    tokens = 1.0

    -- 先把环境记下来：万一加载还失败，这一行就能定位问题，不用再猜
    log_info("package.path  = " .. tostring(package.path))
    log_info("package.cpath = " .. tostring(package.cpath))

    local socket, how = load_socket()
    if not socket then
        log_error("LuaSocket 加载失败。尝试记录：" .. tostring(how))
        send_ok = false
        return
    end
    log_info("LuaSocket 加载方式：" .. how)

    local ok2, sock = pcall(socket.udp)
    if not ok2 or not sock then
        log_error("创建 UDP socket 失败：" .. tostring(sock))
        send_ok = false
        return
    end

    pcall(function()
        sock:settimeout(0)
        sock:setsockname("127.0.0.1", 0)   -- 只绑回环，绝不暴露到局域网
    end)

    udp = sock
    send_ok = true

    -- 探针：把后续要用的表结构打一次，供后续扩展字段时对照
    describe_table("LoGetEngineInfo",   LoGetEngineInfo,   16)
    describe_table("LoGetMechInfo",     LoGetMechInfo,     16)
    describe_table("LoGetPayloadInfo",  LoGetPayloadInfo,  10)
    describe_table("LoGetNavigationInfo", LoGetNavigationInfo, 12)
    log_info("AoA=" .. tostring(safe_call(LoGetAngleOfAttack))
             .. "  AoS=" .. tostring(safe_call(LoGetAngleOfSlide)))

    log_info(string.format(
        "已启动：发往 %s:%d，目标 %d Hz。LuaSocket OK。",
        CFG.host, CFG.port, CFG.rate
    ))
end

function LuaExportAfterNextFrame()
    frame_no = frame_no + 1
    local ok, err = pcall(send_frame)
    if not ok then
        log_error("发送帧异常：" .. tostring(err))
    end
end

function LuaExportStop()
    send_ok = false
    if udp then
        pcall(function() udp:close() end)
        udp = nil
    end
    log_info(string.format("已停止，共处理 %d 帧。", frame_no))
end
