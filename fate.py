import discord
from discord.ext import commands
from discord.utils import get
import os
from datetime import timedelta, datetime

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=",", intents=intents)

OWNER_ID = 1477802548189593864
AUTO_ROLE_NAME = "1538730480466141335"

whitelists = {}
snapped = {}
os.makedirs("whitelists", exist_ok=True)
os.makedirs("autoroles", exist_ok=True)

# =========================
# WHITELIST CHECK
# =========================

def load_whitelist(guild_id):
    if guild_id in whitelists:
        return whitelists[guild_id]
    path = f"whitelists/{guild_id}.txt"
    s = set()
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    s.add(int(line))
    whitelists[guild_id] = s
    return s

def save_whitelist(guild_id):
    s = whitelists.get(guild_id, set())
    path = f"whitelists/{guild_id}.txt"
    with open(path, "w") as f:
        for uid in s:
            f.write(str(uid) + "\n")

def is_whitelisted(guild_id, user_id):
    return user_id in load_whitelist(guild_id)

def wlcheck(ctx):
    if ctx.author.id == OWNER_ID:
        return True
    return is_whitelisted(ctx.guild.id, ctx.author.id)

# =========================
# AUTOROLE SYSTEM
# =========================

def load_autorole(guild_id):
    path = f"autoroles/{guild_id}.txt"
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read().strip()
            if content.isdigit():
                return int(content)
    return None

def save_autorole(guild_id, role_id):
    path = f"autoroles/{guild_id}.txt"
    with open(path, "w") as f:
        f.write(str(role_id))

# =========================
# VERIFY CHANNEL AUTO-SAVE SYSTEM
# =========================

VERIFY_CHANNEL_FILE = "verify_channel.txt"

def save_verify_channel(channel_id):
    with open(VERIFY_CHANNEL_FILE, "w") as f:
        f.write(str(channel_id))

def load_verify_channel():
    if os.path.exists(VERIFY_CHANNEL_FILE):
        with open(VERIFY_CHANNEL_FILE, "r") as f:
            content = f.read().strip()
            if content.isdigit():
                return int(content)
    return None

if load_verify_channel() is None:
    save_verify_channel(1539260969019248690)

# =========================
# WELCOME SYSTEM (JOIN + LEAVE LOGS)
# =========================

COMMANDER_ROLE_ID = 1538721709798981687
LOG_CHANNEL_ID = 1539479412775452713

@bot.event
async def on_member_join(member):
    role_id = load_autorole(member.guild.id)
    role = None
    if role_id:
        role = member.guild.get_role(role_id)
    if not role:
        role = get(member.guild.roles, name=AUTO_ROLE_NAME)
    if role:
        await member.add_roles(role)

    # 🔥 FIX: Immer den Channel nehmen, der "verify" heißt
    verify_channel = discord.utils.get(member.guild.channels, name="verify")

    commander_role = member.guild.get_role(COMMANDER_ROLE_ID)

    if verify_channel and commander_role:
        await verify_channel.send(
            f"Hello {member.mention} — Ping {commander_role.mention} to get verified."
        )

    log_channel = member.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        created = member.created_at.strftime("%Y-%m-%d %H:%M:%S")
        age_days = (datetime.utcnow() - member.created_at).days
        join_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        await log_channel.send(
            f"📥 **Join Log**\n"
            f"**User:** {member} ({member.mention})\n"
            f"**ID:** `{member.id}`\n"
            f"**Account Created:** {created}\n"
            f"**Account Age:** {age_days} days\n"
            f"**Joined At:** {join_time}"
        )

@bot.event
async def on_member_remove(member):
    log_channel = member.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        created = member.created_at.strftime("%Y-%m-%d %H:%M:%S")
        age_days = (datetime.utcnow() - member.created_at).days
        leave_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        await log_channel.send(
            f"📤 **Goodbye, {member.name}! Hope to see you again soon...**\n"
            f"**User:** {member}\n"
            f"**ID:** `{member.id}`\n"
            f"**Account Created:** {created}\n"
            f"**Account Age:** {age_days} days\n"
            f"**Left At:** {leave_time}"
        )

# =========================
# UNBAN SNAP FIX
# =========================

@bot.event
async def on_member_unban(guild, user):
    s = snapped.get(guild.id)
    if s and user.id in s:
        try:
            await guild.ban(user, reason="re-snapped")
        except:
            pass

# =========================
# WHITELIST COMMANDS
# =========================

@bot.command()
@commands.check(wlcheck)
async def wladd(ctx, member: discord.Member):
    wl = load_whitelist(ctx.guild.id)
    if member.id in wl:
        wl.remove(member.id)
        await ctx.send(f"{member.mention} removed from whitelist.")
    else:
        wl.add(member.id)
        await ctx.send(f"{member.mention} added to whitelist.")
    save_whitelist(ctx.guild.id)

@bot.command()
@commands.check(wlcheck)
async def wllist(ctx):
    wl = load_whitelist(ctx.guild.id)
    if not wl:
        await ctx.send("Whitelist is empty.")
    else:
        users = [f"<@{uid}>" for uid in wl]
        await ctx.send("Whitelist:\n" + "\n".join(users))

# =========================
# MODERATION COMMANDS
# =========================

@bot.command()
@commands.check(wlcheck)
async def purge(ctx, amount: int):
    if amount < 1 or amount > 1000:
        return await ctx.send("No.")
    await ctx.channel.purge(limit=amount)
    await ctx.send(f"Purged {amount} messages.", delete_after=5)

@bot.command()
@commands.check(wlcheck)
async def autorole(ctx, role_id: int):
    role = ctx.guild.get_role(role_id)
    if not role:
        return await ctx.send("No.")
    save_autorole(ctx.guild.id, role.id)
    await ctx.send(f"Autorole set to {role.name}")

@bot.command()
@commands.check(wlcheck)
async def serverinfo(ctx):
    guild = ctx.guild
    await ctx.send(
        f"Server: {guild.name}\n"
        f"Members: {guild.member_count}\n"
        f"Channels: {len(guild.channels)}\n"
        f"Created: {guild.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Boost Level: {guild.premium_tier}\n"
        f"Boosts: {guild.premium_subscription_count or 0}"
    )

@bot.command()
@commands.check(wlcheck)
async def userinfo(ctx, member: discord.Member):
    roles = ", ".join([r.name for r in member.roles if r.name != "@everyone"]) or "None"
    joined = member.joined_at.strftime("%Y-%m-%d %H:%M:%S") if member.joined_at else "Unknown"
    created = member.created_at.strftime("%Y-%m-%d %H:%M:%S")
    timeout = "Yes" if member.is_timed_out() else "No"
    await ctx.send(
        f"User: {member}\nID: {member.id}\nRoles: {roles}\nJoined: {joined}\nCreated: {created}\nTimed out: {timeout}"
    )

@bot.command()
@commands.check(wlcheck)
async def role(ctx, action, member: discord.Member, *, role_name):
    role = get(ctx.guild.roles, name=role_name)
    if not role:
        return await ctx.send("Role not found.")
    if action.lower() == "add":
        await member.add_roles(role)
        await ctx.send(f"{role.name} added to {member.mention}.")
    elif action.lower() == "remove":
        await member.remove_roles(role)
        await ctx.send(f"{role.name} removed from {member.mention}.")
    else:
        await ctx.send("Use add or remove.")

@bot.command()
@commands.check(wlcheck)
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(member.display_avatar.url)

@bot.command()
@commands.check(wlcheck)
async def banner(ctx, member: discord.Member = None):
    member = member or ctx.author
    if member.banner:
        await ctx.send(member.banner.url)
    else:
        await ctx.send("No banner")

@bot.command(name='sav')
@commands.check(wlcheck)
async def sav(ctx):
    if ctx.guild.icon:
        await ctx.send(ctx.guild.icon.url)
    else:
        await ctx.send("No icon")

@bot.command(name='sab')
@commands.check(wlcheck)
async def sab(ctx):
    if ctx.guild.icon:
        await ctx.send(ctx.guild.icon.url)
    else:
        await ctx.send("No icon")

@bot.command()
@commands.check(wlcheck)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("Channel locked.")

@bot.command()
@commands.check(wlcheck)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("Channel unlocked.")

@bot.command()
@commands.check(wlcheck)
async def timeout(ctx, member: discord.Member, duration: str):
    try:
        delta = timedelta(minutes=int(duration))
    except:
        return await ctx.send("No.")
    await member.timeout(delta, reason=None)
    await ctx.send(f"{member.mention} timed out.")

@bot.command()
@commands.check(wlcheck)
async def untimeout(ctx, member: discord.Member):
    await member.timeout(None, reason=None)
    await ctx.send(f"{member.mention} untimed out.")

@bot.command()
@commands.check(wlcheck)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} kicked.")

@bot.command()
@commands.check(wlcheck)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f"{member.mention} banned.")

@bot.command()
@commands.check(wlcheck)
async def unban(ctx, user: discord.User):
    try:
        await ctx.guild.unban(user)
        await ctx.send(f"{user} unbanned.")
    except:
        await ctx.send("Unban failed.")

@bot.command()
@commands.check(wlcheck)
async def unbanall(ctx):
    bans = await ctx.guild.bans()
    for entry in bans:
        await ctx.guild.unban(entry.user)
    await ctx.send("All users unbanned.")

# =========================
# SNAP SYSTEM
# =========================

SNAP_GIF = "https://tenor.com/view/salute-cat-cute-yessir-gif-3721562633224755353"

@bot.command()
@commands.check(wlcheck)
async def snap(ctx, member: discord.Member):
    await ctx.guild.ban(member, reason="snapped")
    s = snapped.setdefault(ctx.guild.id, set())
    s.add(member.id)
    await ctx.send(f"{member.mention} **Demolished.**")
    await ctx.send(SNAP_GIF)

@bot.command()
@commands.check(wlcheck)
async def unsnap(ctx, user: discord.User):
    s = snapped.get(ctx.guild.id, set())
    if user.id in s:
        s.remove(user.id)
    try:
        await ctx.guild.unban(user)
    except:
        pass
    await ctx.send(f"{user.mention} **Done.**")
    await ctx.send(SNAP_GIF)

# =========================
# VERIFY SYSTEM
# =========================

VERIFY_ROLE_ID = 1538730257853714502

@bot.command()
@commands.check(wlcheck)
async def verify(ctx, member: discord.Member = None):
    if ctx.message.reference:
        try:
            replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            target = replied_message.author
        except:
            return await ctx.send("Could not find the replied message.")
    else:
        if member is None:
            return await ctx.send("Please reply to a message or mention a user.")
        target = member

    role = ctx.guild.get_role(VERIFY_ROLE_ID)
    if not role:
        return await ctx.send("Verify role not found.")

    try:
        await target.add_roles(role)
        await ctx.send(f"{target.mention} has been verified.")
    except:
        await ctx.send("Failed to verify user.")

# =========================
# NUKE SYSTEM (AUTO VERIFY CHANNEL UPDATE)
# =========================

DEFAULT_NUKE_GIF = "https://cdn.discordapp.com/attachments/1269815180519407669/1306457487804858378/caption.gif"

pending_nukes = {}

from discord.ui import View, Button

class NukeConfirm(View):
    def __init__(self, ctx):
        super().__init__(timeout=30)
        self.ctx = ctx

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id != OWNER_ID and not is_whitelisted(self.ctx.guild.id, interaction.user.id):
            return await interaction.response.send_message("No.", ephemeral=True)

        guild_id = self.ctx.guild.id
        channel_id = pending_nukes.get(guild_id)

        if not channel_id:
            return await interaction.response.send_message("No pending nuke.", ephemeral=True)

        old_channel = discord.utils.get(self.ctx.guild.channels, id=channel_id)
        if not old_channel:
            return await interaction.response.send_message("Channel not found.", ephemeral=True)

        name = old_channel.name
        category = old_channel.category
        overwrites = old_channel.overwrites

        await old_channel.delete()

        new_channel = await self.ctx.guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites
        )

        save_verify_channel(new_channel.id)

        await new_channel.send(DEFAULT_NUKE_GIF)

        del pending_nukes[guild_id]

        await interaction.response.send_message("Nuke executed.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: Button):

        if interaction.user.id != OWNER_ID and not is_whitelisted(self.ctx.guild.id, interaction.user.id):
            return await interaction.response.send_message("No.", ephemeral=True)

        guild_id = self.ctx.guild.id
        if guild_id in pending_nukes:
            del pending_nukes[guild_id]

        await interaction.response.send_message("Nuke declined.", ephemeral=True)
        self.stop()

@bot.command()
@commands.check(wlcheck)
async def nuke(ctx):
    guild_id = ctx.guild.id
    pending_nukes[guild_id] = ctx.channel.id

    view = NukeConfirm(ctx)

    msg = await ctx.send(
        f"⚠️ **Are you sure to nuke this channel?**",
        view=view
    )

    await discord.utils.sleep_until(datetime.utcnow() + timedelta(seconds=3))
    try:
        await msg.delete()
    except:
        pass 

# =========================
# GIVEAWAY SYSTEM
# =========================

import asyncio
import random

last_gw_message = {}  # guild_id : message_id

@bot.command()
@commands.check(wlcheck)
async def gw(ctx, item: str, time: str):

    # 🔥 CHECK: Normal WL oder GW-WL müssen erlaubt sein
    if not (is_gw_whitelisted(ctx.guild.id, ctx.author.id) or is_whitelisted(ctx.guild.id, ctx.author.id)):
        return await ctx.send("You are not allowed to start giveaways.")

    # Convert time (e.g. "1h", "30m")
    seconds = None
    if time.endswith("h"):
        try:
            seconds = int(time[:-1]) * 3600
        except:
            return await ctx.send("Invalid time format. Example: 1h / 30m")
    elif time.endswith("m"):
        try:
            seconds = int(time[:-1]) * 60
        except:
            return await ctx.send("Invalid time format. Example: 1h / 30m")
    else:
        return await ctx.send("Time must end with 'h' or 'm'. Example: 1h / 30m")

    embed = discord.Embed(
        title=f"🎉 Giveaway: {item}",
        description=(
            f"React with 🎉 to enter!\n\n"
            f"**Prize:** {item}\n"
            f"**Ends in:** {time}\n"
            f"**Winner:** 1\n"
            f"**Hosted by:** {ctx.author.mention}"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Started at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")

    last_gw_message[ctx.guild.id] = msg.id

    await asyncio.sleep(seconds)

    msg = await ctx.channel.fetch_message(msg.id)
    users = []

    for reaction in msg.reactions:
        if reaction.emoji == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    users.append(user)

    if len(users) == 0:
        return await ctx.send("Nobody entered the giveaway.")

    winner = random.choice(users)

    await ctx.send(f"🎉 **Giveaway Ended!** User {winner.mention} won the giveaway!")


@bot.command()
@commands.check(wlcheck)
async def gw_reroll(ctx):

    # 🔥 CHECK: Normal WL oder GW-WL müssen erlaubt sein
    if not (is_gw_whitelisted(ctx.guild.id, ctx.author.id) or is_whitelisted(ctx.guild.id, ctx.author.id)):
        return await ctx.send("You are not allowed to reroll giveaways.")

    guild_id = ctx.guild.id

    if guild_id not in last_gw_message:
        return await ctx.send("There is no giveaway to reroll.")

    try:
        msg = await ctx.channel.fetch_message(last_gw_message[guild_id])
    except:
        return await ctx.send("Could not find the giveaway message.")

    users = []

    for reaction in msg.reactions:
        if reaction.emoji == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    users.append(user)

    if len(users) == 0:
        return await ctx.send("Nobody entered the giveaway, reroll not possible.")

    winner = random.choice(users)

    await ctx.send(f"🔄 **Giveaway Reroll!** User {winner.mention} won the giveaway!")

# =========================
# GIVEAWAY WHITELIST SYSTEM
# =========================

gw_whitelist = {}  # guild_id : set(user_ids)

def load_gw_whitelist(guild_id):
    if guild_id not in gw_whitelist:
        gw_whitelist[guild_id] = set()
    return gw_whitelist[guild_id]

def is_gw_whitelisted(guild_id, user_id):
    return user_id in load_gw_whitelist(guild_id)

@bot.command()
@commands.check(wlcheck)
async def gw_wl(ctx, action: str, member: discord.Member):
    guild_id = ctx.guild.id
    wl = load_gw_whitelist(guild_id)

    action = action.lower()

    if action == "add":
        wl.add(member.id)
        await ctx.send(f"{member.mention} has been added to the Giveaway Whitelist.")
    elif action == "remove":
        if member.id in wl:
            wl.remove(member.id)
            await ctx.send(f"{member.mention} has been removed from the Giveaway Whitelist.")
        else:
            await ctx.send("This user is not in the Giveaway Whitelist.")
    else:
        await ctx.send(
            "Invalid action.\n"
            "Use:\n"
            "`-gw_wl add @user`\n"
            "`-gw_wl remove @user`"
        )



bot.run(os.getenv("TOKEN"))