-- AdminGui: admin panel (coins, auras and other cosmetics, jumpscares).
-- The server clones this GUI only into admins' PlayerGui and re-checks every request.
-- Open with the ADMIN button at the top of the screen or the F2 key.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local Modules = ReplicatedStorage:WaitForChild("Modules")
local CM = ReplicatedStorage:WaitForChild("ClientModules")
local ShopConfig = require(Modules.ShopConfig)
local ClientState = require(CM.ClientState)
local UIKit = require(CM.UIKit)

local Router = ClientState.Router
local new = UIKit.new
local T = UIKit.Theme
local F = UIKit.Fonts

local gui = script.Parent
gui.DisplayOrder = 20
local root = UIKit.MakeRoot(gui, false)
local screen = UIKit.ScreenPanel(root, { name = "Admin", title = "ADMIN PANEL", maxSize = Vector2.new(1040, 640), onClose = function() Router.Close("Admin") end })

-- auras first, then titles and MVP effects
local KIND_ORDER = { aura = 1, title = 2, mvp = 3 }
local KIND_NAME = { aura = "AURA", title = "TITLE", mvp = "MVP" }
local ITEMS = {}
for _, item in pairs(ShopConfig.Items) do table.insert(ITEMS, item) end
table.sort(ITEMS, function(a, b)
	if a.kind ~= b.kind then return (KIND_ORDER[a.kind] or 9) < (KIND_ORDER[b.kind] or 9) end
	return (a.coins or 0) < (b.coins or 0)
end)

local players = {}
local selectedId: number? = nil
local render, refresh -- defined below

------------------------------------------------------------------------
-- Left: player list
------------------------------------------------------------------------
local left = new("Frame", { BackgroundColor3 = T.panel2, Size = UDim2.new(0, 290, 1, 0), Parent = screen.Content })
UIKit.corner(14).Parent = left
UIKit.padding(10).Parent = left
UIKit.text({ Text = "PLAYERS ON THIS SERVER", FontFace = F.bold, TextSize = 15, TextColor3 = T.dim, Size = UDim2.new(1, -90, 0, 30), Parent = left })
UIKit.Button({ text = "REFRESH", style = "secondary", size = UDim2.fromOffset(86, 30), position = UDim2.new(1, 0, 0, 0), anchor = Vector2.new(1, 0), textSize = 13, parent = left,
	onClick = function() refresh() end })
local list = new("ScrollingFrame", {
	BackgroundTransparency = 1, BorderSizePixel = 0, Size = UDim2.new(1, 0, 1, -40), Position = UDim2.fromOffset(0, 40),
	ScrollingDirection = Enum.ScrollingDirection.Y, ScrollBarThickness = 6, CanvasSize = UDim2.new(), AutomaticCanvasSize = Enum.AutomaticSize.Y, Parent = left,
})
UIKit.list("v", 6).Parent = list

------------------------------------------------------------------------
-- Right: selected player
------------------------------------------------------------------------
local right = new("Frame", { BackgroundTransparency = 1, Size = UDim2.new(1, -306, 1, 0), Position = UDim2.fromOffset(306, 0), Parent = screen.Content })
local empty = UIKit.text({ Text = "Select a player on the left", TextColor3 = T.dim, TextSize = 20, TextXAlignment = Enum.TextXAlignment.Center, Size = UDim2.fromScale(1, 1), Parent = right })
local detail = new("Frame", { BackgroundTransparency = 1, Size = UDim2.fromScale(1, 1), Visible = false, Parent = right })

local nameLabel = UIKit.text({ FontFace = F.heavy, TextSize = 24, Size = UDim2.new(1, 0, 0, 30), TextTruncate = Enum.TextTruncate.AtEnd, TextWrapped = false, Parent = detail })
local infoLabel = UIKit.text({ TextSize = 15, TextColor3 = T.dim, Size = UDim2.new(1, 0, 0, 22), Position = UDim2.fromOffset(0, 30), Parent = detail })

-- Coins
local coinsRow = new("Frame", { BackgroundColor3 = T.panel2, Size = UDim2.new(1, 0, 0, 64), Position = UDim2.fromOffset(0, 60), Parent = detail })
UIKit.corner(12).Parent = coinsRow
UIKit.padding(8, 12, 8, 12).Parent = coinsRow
UIKit.text({ Text = "COINS", FontFace = F.bold, TextSize = 16, Size = UDim2.new(0, 70, 1, 0), Parent = coinsRow })
local amountBox = new("TextBox", {
	Text = "1000", PlaceholderText = "Amount", ClearTextOnFocus = false, FontFace = F.bold, TextSize = 18, TextColor3 = T.text,
	PlaceholderColor3 = T.faint, BackgroundColor3 = T.panel, Size = UDim2.new(1, -340, 1, 0), Position = UDim2.fromOffset(74, 0), Parent = coinsRow,
})
UIKit.corner(8).Parent = amountBox
amountBox:GetPropertyChangedSignal("Text"):Connect(function()
	local digits = amountBox.Text:gsub("%D", ""):sub(1, 8)
	if digits ~= amountBox.Text then amountBox.Text = digits end
end)

local function sendCoins(sign: number)
	local amount = tonumber(amountBox.Text)
	if not selectedId or not amount or amount <= 0 then
		ClientState.Notify("Enter an amount", "error")
		return
	end
	local ok, view = ClientState.Request("Admin.Coins", { userId = selectedId, amount = amount * sign })
	if ok then
		ClientState.Notify((sign > 0 and "Gave %d Coins to %s" or "Took %d Coins from %s"):format(amount, view.displayName), "success")
		players[view.userId] = view
		render()
	end
end
UIKit.Button({ text = "GIVE", style = "success", size = UDim2.fromOffset(120, 48), position = UDim2.new(1, -128, 0.5, 0), anchor = Vector2.new(1, 0.5), parent = coinsRow, onClick = function() sendCoins(1) end })
UIKit.Button({ text = "TAKE", style = "danger", size = UDim2.fromOffset(120, 48), position = UDim2.new(1, 0, 0.5, 0), anchor = Vector2.new(1, 0.5), parent = coinsRow, onClick = function() sendCoins(-1) end })

-- Items (auras, titles, MVP effects)
UIKit.text({ Text = "AURAS AND COSMETICS", FontFace = F.bold, TextSize = 15, TextColor3 = T.dim, Size = UDim2.new(1, 0, 0, 24), Position = UDim2.fromOffset(0, 132), Parent = detail })
local items = new("ScrollingFrame", {
	BackgroundTransparency = 1, BorderSizePixel = 0, Size = UDim2.new(1, 0, 1, -240), Position = UDim2.fromOffset(0, 158),
	ScrollingDirection = Enum.ScrollingDirection.Y, ScrollBarThickness = 6, CanvasSize = UDim2.new(), AutomaticCanvasSize = Enum.AutomaticSize.Y, Parent = detail,
})
UIKit.list("v", 6).Parent = items
UIKit.padding(2, 10, 2, 2).Parent = items

local itemRows = {}
for i, item in ipairs(ITEMS) do
	local row = new("Frame", { BackgroundColor3 = T.panel2, Size = UDim2.new(1, 0, 0, 52), LayoutOrder = i, Parent = items })
	UIKit.corner(10).Parent = row
	UIKit.padding(6, 8, 6, 12).Parent = row
	local chip = UIKit.text({ Text = KIND_NAME[item.kind] or item.kind, FontFace = F.bold, TextSize = 12, TextColor3 = T.dark, BackgroundTransparency = 0,
		BackgroundColor3 = item.color or T.accent2, TextXAlignment = Enum.TextXAlignment.Center, Size = UDim2.fromOffset(52, 22), Position = UDim2.new(0, 0, 0.5, 0), AnchorPoint = Vector2.new(0, 0.5), Parent = row })
	UIKit.corner(6).Parent = chip
	UIKit.text({ Text = item.name, FontFace = F.bold, TextSize = 17, Size = UDim2.new(1, -330, 1, 0), Position = UDim2.fromOffset(62, 0), TextTruncate = Enum.TextTruncate.AtEnd, TextWrapped = false, Parent = row })
	local status = UIKit.text({ TextSize = 14, TextXAlignment = Enum.TextXAlignment.Right, Size = UDim2.fromOffset(130, 40), Position = UDim2.new(1, -136, 0.5, 0), AnchorPoint = Vector2.new(1, 0.5), Parent = row })
	local btn
	btn = UIKit.Button({ text = "GIVE", style = "success", size = UDim2.fromOffset(120, 40), position = UDim2.new(1, 0, 0.5, 0), anchor = Vector2.new(1, 0.5), textSize = 16, parent = row,
		onClick = function()
			local p = selectedId and players[selectedId]
			if not p then return end
			local give = not p.owned[item.id]
			local ok, view = ClientState.Request("Admin.Item", { userId = p.userId, itemId = item.id, give = give })
			if ok then
				ClientState.Notify((give and "Gave %s to %s" or "Took %s from %s"):format(item.name, view.displayName), "success")
				players[view.userId] = view
				render()
			end
		end })
	itemRows[item.id] = { status = status, button = btn }
end

-- Jumpscares
local scareRow = new("Frame", { BackgroundColor3 = T.panel2, Size = UDim2.new(1, 0, 0, 72), Position = UDim2.new(0, 0, 1, 0), AnchorPoint = Vector2.new(0, 1), Parent = detail })
UIKit.corner(12).Parent = scareRow
UIKit.padding(8, 12, 8, 12).Parent = scareRow
UIKit.text({ Text = "JUMPSCARE", FontFace = F.bold, TextSize = 16, Size = UDim2.new(1, -440, 0, 24), Parent = scareRow })
UIKit.text({ Text = "Skips players in a match and players who turned it off in Settings", TextSize = 12, TextColor3 = T.faint, TextYAlignment = Enum.TextYAlignment.Top, Size = UDim2.new(1, -440, 1, -24), Position = UDim2.fromOffset(0, 24), Parent = scareRow })

local function scare(userId: number)
	local ok, res = ClientState.Request("Admin.Jumpscare", { userId = userId })
	if ok then
		ClientState.Notify(("Jumpscare shown to %d of %d players"):format(res.sent, res.total), res.sent > 0 and "success" or "info")
	end
end
UIKit.Button({ text = "SCARE PLAYER", style = "danger", size = UDim2.fromOffset(200, 52), position = UDim2.new(1, -212, 0.5, 0), anchor = Vector2.new(1, 0.5), parent = scareRow,
	onClick = function() if selectedId then scare(selectedId) end end })
UIKit.Button({ text = "SCARE ALL", style = "primary", size = UDim2.fromOffset(200, 52), position = UDim2.new(1, 0, 0.5, 0), anchor = Vector2.new(1, 0.5), parent = scareRow,
	onClick = function() scare(0) end })

------------------------------------------------------------------------
-- Rendering
------------------------------------------------------------------------
local listButtons = {}

function render()
	for _, b in pairs(listButtons) do b:Destroy() end
	table.clear(listButtons)
	local sorted = {}
	for _, p in pairs(players) do table.insert(sorted, p) end
	table.sort(sorted, function(a, b) return a.name:lower() < b.name:lower() end)
	for i, p in ipairs(sorted) do
		local on = p.userId == selectedId
		local b = new("TextButton", {
			Text = "", AutoButtonColor = false, BackgroundColor3 = on and T.accent or T.panel, Size = UDim2.new(1, -8, 0, 54), LayoutOrder = i, Parent = list,
		})
		UIKit.corner(10).Parent = b
		UIKit.padding(6, 10, 6, 10).Parent = b
		UIKit.text({ Text = p.displayName, FontFace = F.bold, TextSize = 16, Size = UDim2.new(1, 0, 0, 22), TextTruncate = Enum.TextTruncate.AtEnd, TextWrapped = false, Parent = b })
		UIKit.text({ Text = "@" .. p.name .. "  ·  " .. UIKit.formatNumber(p.coins) .. " Coins", TextSize = 13, TextColor3 = on and T.text or T.dim,
			Size = UDim2.new(1, 0, 0, 18), Position = UDim2.fromOffset(0, 22), TextTruncate = Enum.TextTruncate.AtEnd, TextWrapped = false, Parent = b })
		b.Activated:Connect(function()
			UIKit.PlaySound("click")
			selectedId = p.userId
			render()
		end)
		table.insert(listButtons, b)
	end

	local p = selectedId and players[selectedId]
	detail.Visible = p ~= nil
	empty.Visible = p == nil
	if not p then return end
	nameLabel.Text = p.displayName .. "  (@" .. p.name .. ")"
	local notes = { UIKit.formatNumber(p.coins) .. " Coins", "UserId " .. p.userId }
	if p.inMatch then table.insert(notes, "in a match") end
	if not p.jumpscareOn then table.insert(notes, "jumpscares off") end
	infoLabel.Text = table.concat(notes, "  ·  ")
	for id, r in pairs(itemRows) do
		local owned = p.owned[id] == true
		local item = ShopConfig.Items[id]
		local worn = owned and p.equipped[item.kind] == id
		r.status.Text = worn and "OWNED · ON" or owned and "OWNED" or "not owned"
		r.status.TextColor3 = owned and T.green or T.faint
		r.button:SetText(owned and "TAKE" or "GIVE")
		r.button:SetStyle(owned and "danger" or "success")
	end
end

function refresh()
	local ok, data = ClientState.Request("Admin.Players", {})
	if not ok then return end
	table.clear(players)
	for _, p in ipairs(data) do players[p.userId] = p end
	if selectedId and not players[selectedId] then selectedId = nil end
	render()
end

Router.Register("Admin", {
	open = function() screen.Open() task.spawn(refresh) end,
	close = screen.Close,
})

-- Open button and hotkey
UIKit.Button({ name = "AdminButton", text = "ADMIN", style = "danger", size = UDim2.fromOffset(110, 40), position = UDim2.new(0.5, 0, 0, 8), anchor = Vector2.new(0.5, 0), textSize = 16, parent = root,
	onClick = function() Router.Toggle("Admin") end })
UserInputService.InputBegan:Connect(function(input, processed)
	if processed then return end
	if input.KeyCode == Enum.KeyCode.F2 then Router.Toggle("Admin") end
end)
