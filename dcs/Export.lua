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

-- 慢变量专用：缺失就如实发 null，不伪装成 0。
--
-- 为什么必须区分：「这个机型不提供这个字段」和「这个字段的值就是 0」
-- 是两件事。TF-51D 没有液压、没有舵面偏度、没有座舱盖，如果一律发 0，
-- 面板就会显示「液压 0」「温度 0°C」——看着像设备故障，其实是没这个字段。
-- 慢变量包是给人看的，宁可显示「--」也不能给假数。
--
-- 不进 dirty 统计：缺字段是机型差异，是常态，不是坏帧。
local function numo(v, fmt)
    if v == nil then return "null" end
    local t = type(v)
    if t ~= "number" then return "null" end
    if v ~= v then return "null" end                         -- NaN
    if v == math.huge or v == -math.huge then return "null" end
    return string.format(fmt, v)
end

-- 布尔字段（比如雷达开关）：nil 也要如实发 null，
-- 否则面板会把「这机型没有这个字段」显示成「雷达是关的」。
local function boolo(v)
    if v == nil then return "null" end
    if type(v) ~= "boolean" then return "null" end
    return v and "true" or "false"
end

-- 字符串字段（机型名、弹种）。只保留字母数字和少量符号，
-- 免得 CLSID 里的引号把整包 JSON 打断。
local function stro(v)
    if type(v) ~= "string" or v == "" then return "null" end
    local s = v:gsub('[^%w%-%._/ ]', '')
    if s == "" then return "null" end
    return '"' .. s .. '"'
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
-- 温度有两种口径，实测都存在：
--   摄氏度（Su-25T 664.07）  0–1 比例（JF-17 0.72334）
-- 比例口径无法换算成温度 —— 不知道额定值，猜一个就是编数据。
-- 所以小于 5 的一律发 null，面板显示「--」，比显示「1 °C」诚实。
local function temp_or_nil(v)
    if type(v) ~= "number" then return nil end
    if v < 5 then return nil end
    return v
end

-- 有些字段是 {value=0.5} 这种包了一层的表，有些是裸标量，两种都认
local function scalar(v)
    if type(v) == "table" then return v.value end
    return v
end

-- 弹种标识瘦身：DIS_SD-10_DUAL_L → SD-10
local function short_clsid(s)
    if type(s) ~= "string" or s == "" then return nil end
    s = s:gsub("^DIS_", "")
    s = s:gsub("_DUAL_[LR]$", "")
    s = s:gsub("_DUAL$", "")
    s = s:gsub("_POD$", "")
    return s
end

-- 雷达开关。
--
-- 这里绝对不能写成 `cond and sd.Flags.RadarActive or nil` —— 当它返回
-- false（雷达关着）时，表达式会得到 nil，于是「雷达关着」被误报成
-- 「这机型没这个字段」，面板显示 -- 而不是「关」。Lua 的 and/or 只能
-- 安全传递 truthy 值，false 会被后面的 or 吞掉。
local function radar_state(sd)
    local fl = sd and sd.Flags
    if type(fl) ~= "table" then return nil end
    if type(fl.RadarActive) ~= "boolean" then return nil end
    return fl.RadarActive
end

-- 当前挂点。索引口径不确定：可能 1 起也可能 0 起，没选中时可能是 0 或 nil。
local function current_station(pay)
    local cur = scalar(pay.CurrentStation)
    if type(cur) ~= "number" then return nil end
    if cur == 0 then return nil end          -- 0 通常是「没选」
    local stations = pay.Stations
    if type(stations) ~= "table" then return nil end
    -- 两种索引都试一遍：1 起用 stations[cur]，0 起用 stations[cur+1]。
    -- 宁可多试一次，也不要因为差一位就整块空白（这个字段是最重要的反馈）。
    local st = stations[cur]
    if type(st) ~= "table" then st = stations[cur + 1] end
    if type(st) ~= "table" then return nil end
    return cur, short_clsid(st.CLSID), tonumber(st.count)
end

-- 挂载清单：把 7 个挂点里所有有弹的拼成一行，如 "PL-5EIIx1 SD-10x2 SPJx1"。
--
-- 为什么不能只读 CurrentStation：它是「当前选中哪个站」，实测进任务后
-- 一直是 0（没选），要按过武器切换键才会变。而 Stations 是任务加载时就
-- 定死的挂载清单，一进座舱就有 —— 这才是「我这架飞机带了什么」的答案。
local function payload_summary(pay)
    local stations = pay and pay.Stations
    if type(stations) ~= "table" then return nil end
    local out = {}
    for i = 1, #stations do
        local st = stations[i]
        if type(st) == "table" then
            local cls = short_clsid(st.CLSID)
            local n = tonumber(st.count) or 0
            if cls and n > 0 then
                out[#out + 1] = cls .. "x" .. n
            end
        end
    end
    if #out == 0 then return nil end
    return table.concat(out, " ")
end

-- 反向通道回执。**必须在 collect_sys 之前定义** —— Lua 的 local 作用域
-- 从声明处开始，collect_sys 在文件里出现得比 apply_command 早，如果这些
-- 变量定义在后面的「反向通道」节里，collect_sys 读到的是全局 nil，
-- 于是回执永远是 null（踩过这个坑，白排查了一轮）。
--
-- dbg 格式  "dev:cmd:标志"
--   D  设备拿到、方法调用了
--   N  GetDevice 返回空（设备号不对）
--   M  设备有但没有 performClickableAction
--   X  调用抛异常（连退回 0 号设备也失败）
local last_ack = nil
local ack_count = 0
local last_dbg = nil

local function collect_sys()
    local eng  = safe_call(LoGetEngineInfo) or {}
    local mech = safe_call(LoGetMechInfo)   or {}
    local sd   = safe_call(LoGetSelfData)   or {}
    local pay  = safe_call(LoGetPayloadInfo) or {}

    -- 当前选中的挂点：按下「武器切换」之后这里会变，是唯一能反映
    -- 「现在挂了什么弹」的反馈。
    local cur, cur_clsid, cur_count = current_station(pay)

    return {
        fuel   = eng.fuel_internal,
        fuelx  = eng.fuel_external,
        rpm_l  = deepget(eng, "RPM", "left"),
        rpm_r  = deepget(eng, "RPM", "right"),
        temp_l = temp_or_nil(deepget(eng, "Temperature", "left")),
        temp_r = temp_or_nil(deepget(eng, "Temperature", "right")),
        hyd_l  = deepget(eng, "HydraulicPressure", "left"),
        hyd_r  = deepget(eng, "HydraulicPressure", "right"),
        canopy = val(mech, "canopy"),
        wbrake = val(mech, "wheelbrakes"),
        -- 舵面实际偏度。注意这是「配平 + 杆量」的合成，不是配平本身：
        -- DCS 的 Export API 不提供配平位置（见 docs/PANEL.md）。
        cs_a   = deepget(mech, "controlsurfaces", "eleron"),
        cs_e   = deepget(mech, "controlsurfaces", "elevator"),
        cs_r   = deepget(mech, "controlsurfaces", "rudder"),

        -- 机型名（如 "JF-17"）。面板靠它做机型自适应 —— 同样是
        -- 「有这个字段」和「值是 0」的区别，不同机型差别很大。
        ac     = type(sd.Name) == "string" and sd.Name or nil,
        -- 雷达开关。只在 SelfData.Flags 里有，实测 JF-17 可用。
        radar  = radar_state(sd),
        -- 当前挂点 / 弹种 / 余量（要按过武器切换键才有值）
        st     = cur_clsid and cur or nil,
        wn     = cur_clsid,
        wc     = cur_count,
        -- 挂载清单（一进任务就有）与机炮余弹
        wl     = payload_summary(pay),
        cn     = tonumber(deepget(pay, "Cannon", "shells")),
        -- 起落架收放进度 0–1，做「正在收起」用
        gr     = deepget(mech, "gear", "nose", "rod"),
        -- 反向通道回执：最近执行成功的命令号 + 累计条数 + 诊断串
        ack    = last_ack,
        acn    = ack_count,
        dbg    = last_dbg,
    }
end

local function encode_sys(d, t)
    local p = {
        '"t":'     .. num(t, "%.2f"),
        -- 燃油用 4 位小数：单位有两种口径，得同时伺候。
        --   公斤的机型（战斗机）：值上千，4 位是无害的余量；
        --   比例的机型（TF-51D）：每秒只掉 0.0002，2 位小数直接把它量化没了，
        --   斜率算出来会跳成 0 或翻倍，续航跟着乱报。
        '"fuel":'  .. numo(d.fuel,   "%.4f"),
        '"fuelx":' .. numo(d.fuelx,  "%.4f"),
        '"rpm_l":' .. numo(d.rpm_l,  "%.1f"),
        '"rpm_r":' .. numo(d.rpm_r,  "%.1f"),
        '"temp_l":'.. numo(d.temp_l, "%.2f"),
        '"temp_r":'.. numo(d.temp_r, "%.2f"),
        '"hyd_l":' .. numo(d.hyd_l,  "%.1f"),
        '"hyd_r":' .. numo(d.hyd_r,  "%.1f"),
        '"canopy":'.. numo(d.canopy, "%.3f"),
        '"wbrake":'.. numo(d.wbrake, "%.3f"),
        '"cs_a":'  .. numo(d.cs_a,   "%.4f"),
        '"cs_e":'  .. numo(d.cs_e,   "%.4f"),
        '"cs_r":'  .. numo(d.cs_r,   "%.4f"),
        -- 机型与战斗区状态（2026-11-13 新增，实测 JF-17 可用）
        '"ac":'    .. stro(d.ac),
        '"radar":' .. boolo(d.radar),
        '"st":'    .. numo(d.st, "%.0f"),
        '"wn":'    .. stro(d.wn),
        '"wc":'    .. numo(d.wc, "%.0f"),
        '"wl":'    .. stro(d.wl),
        '"cn":'    .. numo(d.cn, "%.0f"),
        '"gr":'    .. numo(d.gr, "%.3f"),
        '"ack":'   .. numo(d.ack, "%.0f"),
        '"acn":'   .. numo(d.acn, "%.0f"),
        '"dbg":'   .. stro(d.dbg),
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

-- ============================ 反向通道 ============================
--
-- 座舱操作回传：iPad/手机 → beacon → UDP 127.0.0.1:5020 → 这里执行。
--
-- 为什么用 UDP 不用 TCP：这个文件每帧都被调用一次，顺手非阻塞收一下最自然；
-- TCP 要维护连接、处理粘包和重连，在 Lua 沙盒里做这些很容易埋雷。丢一条
-- 命令的代价是「再点一次」，完全可以接受。
--
-- 命令格式： device:command:value
--   例如  32:505:0     （设备 32 = GEAR，命令 505 = 起落架手柄，值 0）
-- 注意 device 是 devices.lua 里的编号，不是 elements 的 ID。两者数值接近
-- 但含义完全不同，混了会点错东西。
--
-- 值语义（和 clickabledata.lua 里的 default_* 对应）：
--   按钮  1 = 按下、0 = 松开（有些要成对发才有效）
--   两档  0 / 1
--   三档  0 / 0.5 / 1

local CMD_PORT = 5020
local cmd_sock = nil

-- 文件兜底通道。
--
-- UDP 这条路实测收不到（端口确实被绑定了，但 receive 一直返回空，
-- 可能是 LuaSocket 的 UDP 在 DCS 沙盒里的行为问题）。与其继续猜，
-- 不如加一条确定能用的：PC 把命令写进这个文件，这里每帧看一眼，
-- 读到就删。
--
-- 每帧 io.open 一个不存在的文件开销很小（一次系统调用），而 io 在
-- 这个环境里是确认可用的（结构探针就是用它写的文件）。
local CMD_FILE = (os.getenv("USERPROFILE") or "C:/Users/lenovo")
                 .. "/Saved Games/DCS/Logs/dcs_cmd.txt"


local function open_cmd_socket(socket)
    local ok, s = pcall(socket.udp)
    if not ok or not s then return nil end
    -- 单元测试里 socket 是 mock，没有 receive。没有就别开通道 ——
    -- 宁可反向控制不可用，也不能让主帧发送每帧抛异常。
    if type(s.receive) ~= "function" then return nil end
    local ok2 = pcall(function()
        -- 只绑回环，绝不暴露到局域网 —— 这条通道能直接操作飞机
        s:setsockname("127.0.0.1", CMD_PORT)
        s:settimeout(0)
    end)
    if not ok2 then
        pcall(function() s:close() end)
        return nil
    end
    return s
end

local function apply_command(line)
    local dev, cmd, val = line:match("^(%d+):(%d+):(%-?[%d%.]+)$")
    if not dev then
        last_dbg = "fmt"
        return false
    end
    local dnum, cnum, vnum = tonumber(dev), tonumber(cmd), tonumber(val)

    local okd, d = pcall(GetDevice, dnum)
    if not okd or not d then
        -- 设备号不对是最常见的失败原因：devices.lua 里那些编号是脚本内部
        -- 计数器，和 DCS 运行时暴露的 device id 不一定一致
        last_dbg = string.format("%d:%d:N", dnum, cnum)
        return false
    end
    if type(d.performClickableAction) ~= "function" then
        last_dbg = string.format("%d:%d:M", dnum, cnum)
        return false
    end

    local ok1 = pcall(function()
        d:performClickableAction(cnum, vnum)
    end)
    if ok1 then
        last_ack = cnum
        ack_count = ack_count + 1
        last_dbg = string.format("%d:%d:D", dnum, cnum)
        return true
    end

    -- 退一步：有些机型要求在 0 号主设备上点
    local ok2 = pcall(function()
        local d0 = GetDevice(0)
        if d0 and d0.performClickableAction then
            d0:performClickableAction(cnum, vnum)
        end
    end)
    if ok2 then
        last_ack = cnum
        ack_count = ack_count + 1
        last_dbg = string.format("%d:%d:D0", dnum, cnum)
    else
        last_dbg = string.format("%d:%d:X", dnum, cnum)
    end
    return ok2
end

-- ============================ 结构探针 ============================
--
-- 目的：把 DCS **实际能给**的每一样东西真实抓一次，而不是照着文档猜。
-- 设计外设布局时最怕的就是「以为这个数据能读到」，做到一半才发现是 nil。
--
-- 三个关键取舍：
--
-- 1) **抓一次就停**：靠「输出文件是否存在」判断，抓过就不再抓。想重抓就删
--    掉那个 json。这样不会每次进任务都写一次盘。
-- 2) **延后到第 60 帧**：LuaExportStart 时座舱还没加载完，LoGet* 大多返回
--    nil —— 在那里探测会得到满屏「这个接口没有数据」的假结论。
-- 3) **缺失也如实记**：`__missing__` = 这个版本根本没有这个函数，
--    `__nil__` = 有函数但当前返回空。两者含义完全不同，不能混。

local PROBE_AT_FRAME = 60
local PROBE_DIR = (os.getenv("USERPROFILE") or "C:/Users/lenovo")
                  .. "/Saved Games/DCS/Logs"
local PROBE_PATH = PROBE_DIR .. "/dcsprobe.json"
local probe_done = false

-- 需要探的接口。名字即 `LoGet<名字>`。
local PROBE_FUNCS = {
    "SelfData", "RadarInfo", "LockedTargetInformation", "TargetInformation",
    "SightingSystemInfo", "PayloadInfo", "MechInfo", "EngineInfo",
    "NavigationInfo", "WingInfo", "CockpitInfo", "Route", "FlightInfo",
    "AltitudeAboveSeaLevel", "AltitudeAboveGroundLevel",
    "AngleOfAttack", "AngleOfSlide", "AccelerationUnits",
    "IndicatedAirSpeed", "TrueAirSpeed", "VerticalVelocity", "MachNumber",
    "ModelTime", "MissionTime", "PlayerPlaneId", "CameraPos",
}

local function jesc(s)
    s = tostring(s)
    s = s:gsub("\\", "\\\\"):gsub('"', '\\"')
    s = s:gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
    return '"' .. s .. '"'
end

local function to_json(v, depth, seen)
    depth = depth or 0
    if depth > 6 then return '"<too-deep>"' end
    local t = type(v)
    if v == nil then return "null" end
    if t == "boolean" then return v and "true" or "false" end
    if t == "number" then
        if v ~= v or v == math.huge or v == -math.huge then return "null" end
        return string.format("%.6g", v)
    end
    if t == "string" then return jesc(v) end
    if t ~= "table" then return jesc(tostring(v)) end

    seen = seen or {}
    if seen[v] then return '"<cycle>"' end
    seen[v] = true

    local n = 0
    for _ in pairs(v) do n = n + 1 end

    local parts = {}
    if n > 0 and n == #v then
        for i = 1, #v do
            parts[#parts + 1] = to_json(v[i], depth + 1, seen)
        end
        seen[v] = nil
        return "[" .. table.concat(parts, ",") .. "]"
    end
    for k, val in pairs(v) do
        parts[#parts + 1] = jesc(k) .. ":" .. to_json(val, depth + 1, seen)
    end
    seen[v] = nil
    return "{" .. table.concat(parts, ",") .. "}"
end

local function probe_once()
    local out = {}
    for _, name in ipairs(PROBE_FUNCS) do
        local fn = _G["LoGet" .. name]
        if type(fn) ~= "function" then
            out[name] = "__missing__"
        else
            local ok, v = pcall(fn)
            if not ok then
                out[name] = "__error__:" .. tostring(v)
            elseif v == nil then
                out[name] = "__nil__"
            else
                out[name] = v
            end
        end
    end

    local okj, txt = pcall(to_json, out)
    if not okj then
        log_error("探针序列化失败：" .. tostring(txt))
        return
    end

    local f = io and io.open(PROBE_PATH, "w")
    if f then
        pcall(function() f:write(txt); f:close() end)
        log_info("探针已写出：" .. PROBE_PATH
                 .. "（" .. string.format("%.1f", #txt / 1024) .. " KB）")
    else
        log_error("探针写文件失败：io 不可用或路径无权限（" .. PROBE_PATH .. "）")
    end
end

local function probe_wanted()
    if probe_done then return false end
    if not io then return false end

    -- 测试环境显式退出。单元测试用 lupa 跑这个文件、会跑到第 60 帧，
    -- 探针跟着触发，把夹具的假数据写进真实日志目录 —— 踩过一次：
    -- SelfData 只有 4 个字段、IAS 244.75，而那个文件一存在，真机上的
    -- 探针就再也不会跑了。夹具里置了 _TEST_ENV 来挡住这条路。
    if _TEST_ENV then return false end

    -- 必须存在这把「钥匙」才抓，避免每次进任务都写盘
    local flag = io.open(PROBE_DIR .. "/probe.on", "r")
    if not flag then return false end
    flag:close()

    -- 已有结果就跳过。想重抓：删掉 json，再放一把钥匙。
    local done = io.open(PROBE_PATH, "r")
    if done then
        done:close()
        return false
    end
    return true
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

    -- 反向通道：绑定回环 UDP，等 PC 那边转发座舱操作过来
    cmd_sock = open_cmd_socket(socket)
    if cmd_sock then
        log_info("反向通道已开启：UDP 127.0.0.1:" .. CMD_PORT)
    else
        log_error("反向通道开启失败（端口 " .. CMD_PORT .. " 占用？）")
    end

    -- 清掉上一局残留的命令文件：否则你上次退出前点的那一下，会在这次
    -- 进任务的第一帧被执行 —— 比如一起飞起落架就被收起来。
    if io then pcall(os.remove, CMD_FILE) end

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

    -- 探针只在进座舱后跑一次（第 60 帧 ≈ 1 秒），见文件上方说明
    if frame_no == PROBE_AT_FRAME and probe_wanted() then
        probe_done = true
        local okp, errp = pcall(probe_once)
        if not okp then log_error("探针异常：" .. tostring(errp)) end
    end

    local ok, err = pcall(send_frame)
    if not ok then
        log_error("发送帧异常：" .. tostring(err))
    end

    -- 收座舱操作：先看文件（确定能用），再看 UDP（可能收不到）。
    -- 每帧最多处理 4 条，点得再快也够用，又不至于让一批积压的命令在
    -- 同一帧砸下来（那会让飞机瞬移一样地切换状态）。
    --
    -- 整段 pcall 兜底：反向通道出任何问题都不能影响遥测，遥测才是主链路。
    local okr = pcall(function()
        for _ = 1, 4 do
            local line = nil
            local f = io and io.open(CMD_FILE, "r")
            if f then
                line = f:read("*l")
                f:close()
                pcall(os.remove, CMD_FILE)
            end
            if not line and cmd_sock then
                local got = cmd_sock:receive()
                if got then line = got end
            end
            if not line then break end
            pcall(apply_command, line)
        end
    end)
    if not okr then
        log_error("反向通道接收异常")
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
