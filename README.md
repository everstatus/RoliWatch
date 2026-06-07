# RoliWatch

A Discord bot that tracks Rolimons limited item prices and sends alerts when values or RAP change.

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Configure the bot**
   ```
   copy .env.example .env
   ```
   Then edit `.env` and set your `DISCORD_TOKEN`.

3. **Create the Discord bot**
   - Go to https://discord.com/developers/applications
   - New Application → Bot → copy the token into `.env`
   - Enable **Server Members Intent** and **Message Content Intent** under Privileged Intents
   - Invite the bot with scopes: `bot` + `applications.commands`
   - Required permissions: `Send Messages`, `Embed Links`, `View Channel`

4. **Run**
   ```
   python bot.py
   ```

## Commands

| Command | Description |
|---|---|
| `/setchannel #channel` | Set the channel where price alerts appear (requires Manage Channels) |
| `/track <item_id>` | Start tracking a limited by its Rolimons item ID |
| `/untrack <item_id>` | Stop tracking an item |
| `/list` | Show all tracked items with last known prices |
| `/check` | Manually fetch current prices for all tracked items |

## Finding item IDs

Visit any item page on Rolimons — the ID is in the URL:
`https://www.rolimons.com/item/1365767`  →  ID is `1365767`

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | — | Your bot token (required) |
| `CHECK_INTERVAL` | `120` | Seconds between automatic price checks |
