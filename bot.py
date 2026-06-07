import asyncio
import os
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import database as db
import rolimons

load_dotenv()

TOKEN          = os.getenv("DISCORD_TOKEN")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))  # seconds

# ─── Trend label mapping ────────────────────────────────────────────────────
TREND_LABELS = {
    1:  "▲ Projected",
    0:  "➡ Stable",
    -1: "▼ UnProjected",
    2:  "▲▲ Hyped",
    -2: "▼▼ Lowered",
}

ITEM_URL = "https://www.rolimons.com/item/{item_id}"


# ─── Bot setup ──────────────────────────────────────────────────────────────
intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)


# ─── Helpers ────────────────────────────────────────────────────────────────
def fmt_robux(value: int | None) -> str:
    if value is None:
        return "N/A"
    return f"R${value:,}"


def pct_change(old: int | None, new: int | None) -> str:
    if old is None or new is None or old == 0:
        return ""
    delta = new - old
    pct   = delta / old * 100
    sign  = "+" if delta >= 0 else ""
    return f" ({sign}{pct:.1f}%)"


def build_alert_embed(item: dict, old_value: int | None, old_rap: int | None) -> discord.Embed:
    url   = ITEM_URL.format(item_id=item["id"])
    trend = TREND_LABELS.get(item["trend"], "Unknown")

    value_change = item["value"] != old_value
    rap_change   = item["rap"]   != old_rap

    if value_change and old_value is not None:
        direction = "📈" if (item["value"] or 0) > (old_value or 0) else "📉"
    elif rap_change and old_rap is not None:
        direction = "📈" if (item["rap"] or 0) > (old_rap or 0) else "📉"
    else:
        direction = "🔔"

    colour = discord.Colour.green() if "📈" in direction else discord.Colour.red()

    embed = discord.Embed(
        title=f"{direction} {item['name']}",
        url=url,
        colour=colour,
    )
    embed.add_field(
        name="Value",
        value=f"{fmt_robux(old_value)} → **{fmt_robux(item['value'])}**{pct_change(old_value, item['value'])}",
        inline=True,
    )
    embed.add_field(
        name="RAP",
        value=f"{fmt_robux(old_rap)} → **{fmt_robux(item['rap'])}**{pct_change(old_rap, item['rap'])}",
        inline=True,
    )
    embed.add_field(name="Trend", value=trend, inline=True)
    embed.set_footer(text=f"Item ID: {item['id']}")
    return embed


async def safe_defer(interaction: discord.Interaction, ephemeral: bool = False) -> bool:
    """Defer an interaction, returning False if it already expired."""
    try:
        await interaction.response.defer(ephemeral=ephemeral)
        return True
    except (discord.NotFound, discord.HTTPException):
        return False


# ─── Price-check loop ────────────────────────────────────────────────────────
@tasks.loop(seconds=CHECK_INTERVAL)
async def price_check():
    rows = db.get_all_tracked_items()
    if not rows:
        return

    try:
        all_items = await rolimons.fetch_all_items()
    except Exception as e:
        print(f"[RoliWatch] ⚠  Rolimons fetch failed: {e}")
        return

    alerts_sent = 0
    for row in rows:
        item_id  = row["item_id"]
        guild_id = row["guild_id"]
        raw      = all_items.get(str(item_id))
        if raw is None:
            continue

        new_value = raw[rolimons.IDX_VALUE] if raw[rolimons.IDX_VALUE] != -1 else None
        new_rap   = raw[rolimons.IDX_RAP]   if raw[rolimons.IDX_RAP]   != -1 else None
        old_value = row["last_value"]
        old_rap   = row["last_rap"]

        price_changed = (old_value is not None and new_value != old_value) or \
                        (old_rap   is not None and new_rap   != old_rap)

        db.update_item_prices(item_id, guild_id, new_value, new_rap)

        if not price_changed:
            continue

        channel_id = db.get_alert_channel(guild_id)
        if not channel_id:
            continue

        channel = client.get_channel(channel_id)
        if not channel:
            continue

        item = {
            "id":    item_id,
            "name":  raw[rolimons.IDX_NAME],
            "acro":  raw[rolimons.IDX_ACRO],
            "rap":   new_rap,
            "value": new_value,
            "trend": raw[rolimons.IDX_TREND] if len(raw) > rolimons.IDX_TREND else None,
        }
        embed = build_alert_embed(item, old_value, old_rap)
        try:
            await channel.send(embed=embed)
            alerts_sent += 1
            print(f"[RoliWatch] 🔔 Alert sent — {item['name']} (guild {guild_id})")
        except discord.Forbidden:
            print(f"[RoliWatch] ⚠  Missing send perms in channel {channel_id}")

    if alerts_sent == 0:
        print(f"[RoliWatch] ✓  Price check done — no changes across {len(rows)} item(s)")


# ─── Slash commands ──────────────────────────────────────────────────────────
@tree.command(name="setchannel", description="Set the channel where price alerts are sent")
@app_commands.checks.has_permissions(manage_channels=True)
async def cmd_setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        db.set_alert_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            f"✅ Alerts will be sent to {channel.mention}.", ephemeral=True
        )
        print(f"[RoliWatch] ✓  Alert channel set to #{channel.name} (guild {interaction.guild_id})")
    except (discord.NotFound, discord.HTTPException):
        pass


@tree.command(name="track", description="Start tracking a Rolimons limited by item ID")
async def cmd_track(interaction: discord.Interaction, item_id: int):
    if not await safe_defer(interaction, ephemeral=True):
        return

    item = await rolimons.fetch_item(item_id)
    if item is None:
        await interaction.followup.send("❌ Item not found on Rolimons. Check the ID and try again.")
        return

    db.add_tracked_item(item_id, interaction.guild_id, interaction.user.id)
    db.update_item_prices(item_id, interaction.guild_id, item["value"], item["rap"])

    embed = discord.Embed(
        title=f"✅ Now tracking: {item['name']}",
        url=ITEM_URL.format(item_id=item_id),
        colour=discord.Colour.blurple(),
    )
    embed.add_field(name="Value", value=fmt_robux(item["value"]), inline=True)
    embed.add_field(name="RAP",   value=fmt_robux(item["rap"]),   inline=True)
    embed.add_field(name="Trend", value=TREND_LABELS.get(item["trend"], "Unknown"), inline=True)
    embed.set_footer(text=f"Item ID: {item_id}")
    await interaction.followup.send(embed=embed)
    print(f"[RoliWatch] + Tracking {item['name']} ({item_id}) for guild {interaction.guild_id}")


@tree.command(name="untrack", description="Stop tracking a limited item")
async def cmd_untrack(interaction: discord.Interaction, item_id: int):
    try:
        removed = db.remove_tracked_item(item_id, interaction.guild_id)
        if removed:
            await interaction.response.send_message(f"✅ Stopped tracking item `{item_id}`.", ephemeral=True)
            print(f"[RoliWatch] - Untracked item {item_id} for guild {interaction.guild_id}")
        else:
            await interaction.response.send_message(f"❌ Item `{item_id}` is not being tracked.", ephemeral=True)
    except (discord.NotFound, discord.HTTPException):
        pass


@tree.command(name="list", description="Show all currently tracked items")
async def cmd_list(interaction: discord.Interaction):
    if not await safe_defer(interaction, ephemeral=True):
        return

    rows = db.get_tracked_items(interaction.guild_id)
    if not rows:
        await interaction.followup.send("No items are being tracked. Use `/track <item_id>` to add one.")
        return

    try:
        all_items = await rolimons.fetch_all_items()
    except Exception:
        all_items = {}

    embed = discord.Embed(title="📋 Tracked Limiteds", colour=discord.Colour.blurple())
    for row in rows:
        raw  = all_items.get(str(row["item_id"]))
        name = raw[rolimons.IDX_NAME] if raw else f"Item {row['item_id']}"
        val  = fmt_robux(row["last_value"])
        rap  = fmt_robux(row["last_rap"])
        url  = ITEM_URL.format(item_id=row["item_id"])
        embed.add_field(
            name=f"[{name}]({url})",
            value=f"Value: {val} | RAP: {rap}",
            inline=False,
        )
    await interaction.followup.send(embed=embed)


@tree.command(name="check", description="Manually fetch current prices for all tracked items")
async def cmd_check(interaction: discord.Interaction):
    if not await safe_defer(interaction):
        return

    rows = db.get_tracked_items(interaction.guild_id)
    if not rows:
        await interaction.followup.send("No items tracked. Use `/track <item_id>` first.")
        return

    try:
        all_items = await rolimons.fetch_all_items()
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to reach Rolimons: {e}")
        return

    embed = discord.Embed(title="📊 Current Prices", colour=discord.Colour.blurple())
    for row in rows:
        raw = all_items.get(str(row["item_id"]))
        if raw is None:
            embed.add_field(name=f"Item {row['item_id']}", value="Not found", inline=False)
            continue
        name  = raw[rolimons.IDX_NAME]
        value = raw[rolimons.IDX_VALUE] if raw[rolimons.IDX_VALUE] != -1 else None
        rap   = raw[rolimons.IDX_RAP]   if raw[rolimons.IDX_RAP]   != -1 else None
        trend = TREND_LABELS.get(raw[rolimons.IDX_TREND] if len(raw) > rolimons.IDX_TREND else None, "Unknown")
        url   = ITEM_URL.format(item_id=row["item_id"])
        embed.add_field(
            name=f"[{name}]({url})",
            value=f"Value: **{fmt_robux(value)}** | RAP: **{fmt_robux(rap)}** | {trend}",
            inline=False,
        )
    await interaction.followup.send(embed=embed)


# ─── Bot events ──────────────────────────────────────────────────────────────
BOT_DESCRIPTION = (
    "Track Roblox limited item prices from Rolimons. "
    "Get instant Discord alerts whenever a limited's value or RAP changes. "
    "Add items by ID, set a dedicated alert channel, and never miss a price swing."
)

BANNER = """
╔══════════════════════════════════════╗
║           R O L I W A T C H          ║
║     Rolimons Limited Price Bot       ║
╚══════════════════════════════════════╝"""


@client.event
async def on_ready():
    db.init_db()
    await tree.sync()
    try:
        await client.application.edit(description=BOT_DESCRIPTION)
    except Exception:
        pass
    price_check.start()
    print(BANNER)
    print(f"  Bot      : {client.user}")
    print(f"  Guilds   : {len(client.guilds)}")
    print(f"  Interval : every {CHECK_INTERVAL}s")
    print(f"  Status   : online ✓")
    print("─" * 40)


@client.event
async def on_guild_join(guild: discord.Guild):
    print(f"[RoliWatch] + Joined guild: {guild.name} ({guild.id})")


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    client.run(TOKEN, log_handler=None)
