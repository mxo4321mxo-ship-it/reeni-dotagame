-- AdminService: admin panel backend (coins, cosmetics, jumpscares).
-- Every action is checked here on the server; the panel itself is only cloned into admins' PlayerGui,
-- so other players never receive its code.
--
-- Who is an admin:
--   * the game owner (or the group owner, rank 255, if the game belongs to a group);
--   * any UserId listed in EXTRA_ADMINS below;
--   * everyone while testing in Roblox Studio.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ServerStorage = game:GetService("ServerStorage")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local ShopConfig = require(ReplicatedStorage.Modules.ShopConfig)

local Net = require(script.Parent.Net)
local DataService = require(script.Parent.DataService)
local CosmeticService = require(script.Parent.CosmeticService)

local AdminService = {}

-- Add more admins here, e.g. { 12345678, 87654321 }
local EXTRA_ADMINS: { number } = {}

local MAX_COINS_PER_ACTION = 10_000_000

local adminCache: { [Player]: boolean } = {}

local function matchService()
	return require(script.Parent.MatchService)
end

function AdminService.IsAdmin(player: Player): boolean
	local cached = adminCache[player]
	if cached ~= nil then return cached end
	local admin = RunService:IsStudio() or table.find(EXTRA_ADMINS, player.UserId) ~= nil
	if not admin then
		if game.CreatorType == Enum.CreatorType.User then
			admin = player.UserId == game.CreatorId
		elseif game.CreatorType == Enum.CreatorType.Group then
			local ok, rank = pcall(function() return player:GetRankInGroup(game.CreatorId) end)
			admin = ok and rank >= 255
		end
	end
	adminCache[player] = admin
	return admin
end

local function log(admin: Player, text: string)
	print(("[Admin] %s (%d): %s"):format(admin.Name, admin.UserId, text))
end

local function target(payload): Player?
	local p = Players:GetPlayerByUserId(tonumber(payload.userId) or 0)
	if p and DataService.IsLoaded(p) then return p end
	return nil
end

local function playerView(p: Player)
	local d = DataService.Get(p)
	if not d then return nil end
	local owned = {}
	for id in pairs(d.owned) do owned[id] = true end
	return {
		userId = p.UserId,
		name = p.Name,
		displayName = p.DisplayName,
		coins = d.coins,
		owned = owned,
		equipped = DataService.DeepCopy(d.equipped),
		inMatch = matchService().IsInMatch(p),
		jumpscareOn = d.settings.jumpscare ~= false,
	}
end

-- Wraps a handler so only admins can run it.
local function adminOnly(fn)
	return function(player: Player, payload)
		if not AdminService.IsAdmin(player) then
			warn(("[Admin] blocked request from %s (%d)"):format(player.Name, player.UserId))
			return Net.Err("Not allowed")
		end
		return fn(player, payload)
	end
end

local function giveGui(player: Player)
	if not AdminService.IsAdmin(player) then return end
	local template = ServerStorage:FindFirstChild("AdminGui")
	if not template then
		warn("[Admin] ServerStorage.AdminGui is missing")
		return
	end
	local pg = player:WaitForChild("PlayerGui", 30)
	if pg and not pg:FindFirstChild("AdminGui") then
		template:Clone().Parent = pg
	end
end

function AdminService.Init()
	Players.PlayerAdded:Connect(function(p) task.spawn(giveGui, p) end)
	for _, p in ipairs(Players:GetPlayers()) do task.spawn(giveGui, p) end
	Players.PlayerRemoving:Connect(function(p) adminCache[p] = nil end)

	Net.On("Admin.Players", adminOnly(function()
		local list = {}
		for _, p in ipairs(Players:GetPlayers()) do
			local v = playerView(p)
			if v then table.insert(list, v) end
		end
		table.sort(list, function(a, b) return a.name:lower() < b.name:lower() end)
		return Net.Ok(list)
	end))

	-- amount > 0 gives coins, amount < 0 takes them (never below 0)
	Net.On("Admin.Coins", adminOnly(function(admin, payload)
		local p = target(payload)
		if not p then return Net.Err("Player not found") end
		local amount = math.floor(tonumber(payload.amount) or 0)
		if amount == 0 or math.abs(amount) > MAX_COINS_PER_ACTION then
			return Net.Err("Amount must be between 1 and " .. MAX_COINS_PER_ACTION)
		end
		local _, after = DataService.Update(p, function(d)
			d.coins = math.max(0, d.coins + amount)
			return d.coins
		end)
		DataService.SaveNow(p)
		log(admin, ("coins %+d -> %s (now %d)"):format(amount, p.Name, after))
		if amount > 0 then
			Net.Notify(p, ("An admin gave you %d Coins"):format(amount), "success")
		end
		return Net.Ok(playerView(p))
	end))

	-- give = true grants the item and puts it on; give = false removes it
	Net.On("Admin.Item", adminOnly(function(admin, payload)
		local p = target(payload)
		if not p then return Net.Err("Player not found") end
		local item = ShopConfig.Items[payload.itemId]
		if not item then return Net.Err("Unknown item") end
		local give = payload.give == true
		DataService.Update(p, function(d)
			if give then
				d.owned[item.id] = d.owned[item.id] or "admin"
				d.equipped[item.kind] = item.id
			else
				d.owned[item.id] = nil
				if d.equipped[item.kind] == item.id then d.equipped[item.kind] = "" end
			end
		end)
		CosmeticService.Apply(p)
		DataService.SaveNow(p)
		log(admin, ("%s %s -> %s"):format(give and "gave" or "took", item.id, p.Name))
		if give then
			Net.Notify(p, "An admin gave you " .. item.name, "success")
		end
		return Net.Ok(playerView(p))
	end))

	-- userId = 0 scares everyone in the lobby except the admin
	Net.On("Admin.Jumpscare", adminOnly(function(admin, payload)
		local targets = {}
		local id = tonumber(payload.userId) or 0
		if id == 0 then
			for _, p in ipairs(Players:GetPlayers()) do
				if p ~= admin then table.insert(targets, p) end
			end
		else
			local p = Players:GetPlayerByUserId(id)
			if not p then return Net.Err("Player not found") end
			table.insert(targets, p)
		end
		local sent = CosmeticService.SendJumpscare(targets, admin.DisplayName)
		log(admin, ("jumpscare %s: %d shown"):format(id == 0 and "ALL" or tostring(id), sent))
		return Net.Ok({ sent = sent, total = #targets })
	end))
end

return AdminService
