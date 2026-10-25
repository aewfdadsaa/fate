import discord
from discord.ext import commands
from discord.utils import get
import os
import json
import time
import asyncio
import random
from datetime import timedelta, datetime, timezone

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=",", intents=intents)

OWNER_ID = 1477802548189593864
AUTO_ROLE_NAME = "1538730480466141335"

# =========================
# EINSTELLUNGEN (ANTINUKE)
# =========================

MAX_BANS_PER_DAY = 5        # jeder ausser OWNER_ID darf max. so viele Bans / 24h
MAX_KICKS_PER_DAY = 5       # dasselbe fuer Kicks
MAX_DELETES_PER_MIN = 3     # max. geloeschte Channels/Rollen pro 60 Sek.
PING_LIMIT = 3              # so viele @everyone/@here hintereinander loesen aus
PING_WINDOW = 60            # ...innerhalb dieser Sekunden
KICK_UNKNOWN_BOTS = True    # Bots, die nicht vom OWNER_ID hinzugefuegt wurden, werden gekickt
AUTO_RESTORE_ON_JOIN = True # Rollen automatisch zurueckgeben wenn jemand neu joint

whitelists = {}
snapped = {}
os.makedirs("whitelists", exist_ok=True)
os.makedirs("autoroles", exist_ok=True)
os.makedirs("saved_roles", exist_ok=True)

# =========================
# JSON HELFER
# =========================

def jload(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default

def jsave(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

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

def ownercheck(ctx):
    return ctx.author.id == OWNER_ID

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
# ROLLEN-SPEICHER (fuer ,restore)
# =========================

role_store = {}  # guild_id -> {str(user_id): [role_ids]}

def get_role_store(guild_id):
    if guild_id not in role_store:
        role_store[guild_id] = jload(f"saved_roles/{guild_id}.json", {})
    return role_store[guild_id]

def write_role_store(guild_id):
    jsave(f"saved_roles/{guild_id}.json", get_role_store(guild_id))

def snapshot_member(member, write=True):
    """Speichert die aktuellen Rollen eines Members (nicht waehrend Lockdown / X7)."""
    gid = member.guild.id
    if member.bot or gid in lockdown_state:
        return
    if str(member.id) in x7_state.get(str(gid), {}):
        return
    rids = [r.id for r in member.roles if not r.is_default() and not r.managed]
    if not rids:
        return  # leere Liste aendert nie den gespeicherten Stand
    store = get_role_store(gid)
    old = store.get(str(member.id), [])
    # Nur ERGAENZEN: entfernte Rollen bleiben gespeichert, damit ,restore sie zurueckgeben kann.
    merged = old + [r for r in rids if r not in old]
    # Rollen, die es im Server nicht mehr gibt, aufraeumen
    merged = [r for r in merged if member.guild.get_role(r)]
    if merged != old:
        store[str(member.id)] = merged
        if write:
            write_role_store(gid)

async def restore_roles(member):
    """Gibt gespeicherte Rollen zurueck. Gibt (given, skipped) zurueck."""
    guild = member.guild
    me = guild.me
    rids = get_role_store(guild.id).get(str(member.id), [])
    given, skipped = [], []
    for rid in rids:
        r = guild.get_role(rid)
        if r is None:
            skipped.append(f"deleted role ({rid})")
        elif r.managed or r >= me.top_role:
            skipped.append(r.name)
        elif r not in member.roles:
            given.append(r)
    if given:
        await member.add_roles(*given, reason="restore")
    return given, skipped

@bot.event
async def on_member_update(before, after):
    if before.roles != after.roles:
        snapshot_member(after)

# =========================
# LOCKDOWN / X7 STATUS
# =========================

LOCKDOWN_FILE = "lockdown.json"
X7_FILE = "x7.json"

# guild_id (int) -> {"channel": id, "roles": {str(user_id): [role_ids]}}
lockdown_state = {int(k): v for k, v in jload(LOCKDOWN_FILE, {}).items()}
# str(guild_id) -> {str(user_id): [role_ids]}
x7_state = jload(X7_FILE, {})

def save_lockdown():
    jsave(LOCKDOWN_FILE, {str(k): v for k, v in lockdown_state.items()})

def save_x7():
    jsave(X7_FILE, x7_state)

# =========================
# ANTINUKE KERN
# =========================

LOG_CHANNEL_ID = 1553512690155130900
ACTION_LOG_FILE = "actionlog.json"
action_log = jload(ACTION_LOG_FILE, {})  # "guild:user:kind" -> [timestamps]

def register_action(guild_id, user_id, kind, window):
    """Zaehlt eine Aktion und gibt zurueck wie oft sie im Zeitfenster passiert ist."""
    key = f"{guild_id}:{user_id}:{kind}"
    now = time.time()
    lst = [t for t in action_log.get(key, []) if now - t < window]
    lst.append(now)
    action_log[key] = lst
    jsave(ACTION_LOG_FILE, action_log)
    return len(lst)

async def send_log(guild, text):
    ch = guild.get_channel(LOG_CHANNEL_ID)
    if ch:
        try:
            await ch.send(text)
        except discord.HTTPException:
            pass

async def start_lockdown(guild, reason="manual"):
    gid = guild.id
    if gid in lockdown_state:
        return
    # sofort markieren, damit parallele Trigger nicht doppelt laufen
    lockdown_state[gid] = {"channel": None, "roles": {}}
    save_lockdown()
    me = guild.me

    await send_log(guild, f"🚨 **ANTINUKE TRIGGERED** — {reason}\nLockdown started.")

    # Lockdown-Channel: alle duerfen lesen, nur Bot + Owner duerfen schreiben
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False, add_reactions=False),
        me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    owner_member = guild.get_member(OWNER_ID)
    if owner_member:
        overwrites[owner_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    try:
        channel = await guild.create_text_channel("lockdown", overwrites=overwrites, reason="Antinuke lockdown")
        lockdown_state[gid]["channel"] = channel.id
        save_lockdown()
        await channel.send("server is currently on lockdown")
    except discord.HTTPException:
        pass

    # Rollen von allen entfernen (ausser Bots, Bot-Owner, Server-Owner)
    count = 0
    for member in list(guild.members):
        if member.bot or member.id == OWNER_ID or member.id == guild.owner_id:
            continue
        removable = [r for r in member.roles if not r.is_default() and not r.managed and r < me.top_role]
        if not removable:
            continue
        lockdown_state[gid]["roles"][str(member.id)] = [r.id for r in removable]
        try:
            await member.remove_roles(*removable, reason="Antinuke lockdown")
            count += 1
        except discord.HTTPException:
            pass
        if count % 20 == 0:
            save_lockdown()
        await asyncio.sleep(0.25)
    save_lockdown()
    await send_log(guild, f"🔒 Lockdown active — roles removed from {count} members.")

async def end_lockdown(guild):
    state = lockdown_state.get(guild.id)
    if not state:
        return None
    me = guild.me
    restored = 0
    for uid, rids in state["roles"].items():
        member = guild.get_member(int(uid))
        if not member:
            continue
        roles = [guild.get_role(r) for r in rids]
        roles = [r for r in roles if r and not r.managed and r < me.top_role and r not in member.roles]
        if roles:
            try:
                await member.add_roles(*roles, reason="Lockdown lifted")
                restored += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.25)
    channel = guild.get_channel(state.get("channel") or 0)
    del lockdown_state[guild.id]
    save_lockdown()
    if channel:
        try:
            await channel.delete(reason="Lockdown lifted")
        except discord.HTTPException:
            pass
    return restored

async def trigger_antinuke(guild, reason):
    if guild.id in lockdown_state:
        return
    await start_lockdown(guild, reason)

async def antinuke_gate(ctx, kind):
    """True = Aktion erlaubt. Zaehlt Bans/Kicks die ueber Bot-Befehle laufen."""
    if ctx.author.id == OWNER_ID:
        return True
    limit = MAX_BANS_PER_DAY if kind == "ban" else MAX_KICKS_PER_DAY
    count = register_action(ctx.guild.id, ctx.author.id, kind, 86400)
    if count > limit:
        await trigger_antinuke(ctx.guild, f"{ctx.author} ({ctx.author.id}) exceeded {limit} {kind}s / 24h (via bot command)")
        return False
    return True

# Globaler Check: waehrend Lockdown darf nur der Owner Befehle nutzen
@bot.check
async def global_gate(ctx):
    if ctx.guild is None:
        return False
    if ctx.guild.id in lockdown_state and ctx.author.id != OWNER_ID:
        return False
    return True

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CheckFailure, commands.CommandNotFound)):
        return
    print(f"Command error in {ctx.command}: {error}")

# --- Audit-Log basierter Schutz (Bans/Kicks/Loeschungen/Bots) ---

@bot.event
async def on_audit_log_entry_create(entry):
    guild = entry.guild
    executor = entry.user
    if executor is None or executor.id in (OWNER_ID, bot.user.id):
        return
    if guild.id in lockdown_state:
        return

    action = entry.action
    target_id = getattr(entry.target, "id", None)

    if action in (discord.AuditLogAction.ban, discord.AuditLogAction.kick):
        kind = "ban" if action == discord.AuditLogAction.ban else "kick"
        limit = MAX_BANS_PER_DAY if kind == "ban" else MAX_KICKS_PER_DAY
        count = register_action(guild.id, executor.id, kind, 86400)
        if count > limit:
            if kind == "ban" and target_id:
                try:
                    await guild.unban(discord.Object(id=target_id), reason="Antinuke: revert excess ban")
                except discord.HTTPException:
                    pass
            await trigger_antinuke(guild, f"{executor} ({executor.id}) exceeded {limit} {kind}s / 24h")

    elif action in (discord.AuditLogAction.channel_delete, discord.AuditLogAction.role_delete):
        count = register_action(guild.id, executor.id, "delete", 60)
        if count > MAX_DELETES_PER_MIN:
            await trigger_antinuke(guild, f"{executor} ({executor.id}) deleted more than {MAX_DELETES_PER_MIN} channels/roles within 60s")

    elif action == discord.AuditLogAction.bot_add and KICK_UNKNOWN_BOTS:
        if target_id:
            try:
                await guild.kick(discord.Object(id=target_id), reason="Antinuke: bot added by non-owner")
                await send_log(guild, f"🤖 Kicked bot `{target_id}` — added by {executor} ({executor.id}).")
            except discord.HTTPException:
                pass

# --- @everyone / @here Spam ---

ping_tracker = {}  # channel_id -> [(timestamp, message)]

@bot.event
async def on_message(message):
    if (
        message.guild
        and message.author.id not in (OWNER_ID, bot.user.id)
        and message.guild.id not in lockdown_state
    ):
        content = message.content or ""
        cid = message.channel.id
        if "@everyone" in content or "@here" in content:
            now = time.time()
            lst = [x for x in ping_tracker.get(cid, []) if now - x[0] < PING_WINDOW]
            lst.append((now, message))
            ping_tracker[cid] = lst
            if len(lst) >= PING_LIMIT:
                ping_tracker[cid] = []
                for _, m in lst:
                    try:
                        await m.delete()
                    except discord.HTTPException:
                        pass
                await trigger_antinuke(message.guild, f"{PING_LIMIT}x @everyone/@here in a row in #{message.channel}")
        else:
            ping_tracker.pop(cid, None)
    await bot.process_commands(message)

# =========================
# READY (Rollen-Snapshot)
# =========================

@bot.event
async def on_ready():
    for guild in bot.guilds:
        for m in guild.members:
            snapshot_member(m, write=False)
        write_role_store(guild.id)
    print(f"Logged in as {bot.user}")

# =========================
# WELCOME SYSTEM (JOIN + LEAVE LOGS)
# =========================

COMMANDER_ROLE_ID = 1538721709798981687

@bot.event
async def on_member_join(member):
    if member.guild.id not in lockdown_state:
        role_id = load_autorole(member.guild.id)
        role = None
        if role_id:
            role = member.guild.get_role(role_id)
        if not role:
            role = get(member.guild.roles, name=AUTO_ROLE_NAME)
        if role:
            try:
                await member.add_roles(role)
            except discord.HTTPException:
                pass
        if AUTO_RESTORE_ON_JOIN and not member.bot:
            try:
                await restore_roles(member)
            except discord.HTTPException:
                pass

    verify_channel = discord.utils.get(member.guild.channels, name="verify")
    commander_role = member.guild.get_role(COMMANDER_ROLE_ID)

    if verify_channel and commander_role:
        await verify_channel.send(
            f"Hello {member.mention} — Ping {commander_role.mention} to get verified."
        )

    log_channel = member.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        now = datetime.now(timezone.utc)
        created = member.created_at.strftime("%Y-%m-%d %H:%M:%S")
        age_days = (now - member.created_at).days
        join_time = now.strftime("%Y-%m-%d %H:%M:%S")

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
    # Rollen merken (gilt auch bei Ban/Kick/Leave)
    snapshot_member(member)

    log_channel = member.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        now = datetime.now(timezone.utc)
        created = member.created_at.strftime("%Y-%m-%d %H:%M:%S")
        age_days = (now - member.created_at).days
        leave_time = now.strftime("%Y-%m-%d %H:%M:%S")

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
# NEUE COMMANDS: RESTORE / X7 / LOCKDOWN
# =========================

@bot.command()
@commands.check(wlcheck)
async def restore(ctx, user: discord.User):
    """,restore <user id>  oder  ,restore @user"""
    store = get_role_store(ctx.guild.id)
    if str(user.id) not in store:
        return await ctx.send("No saved roles for this user.")

    member = ctx.guild.get_member(user.id)
    if member is None:
        if AUTO_RESTORE_ON_JOIN:
            return await ctx.send("User is not in the server (banned? unban first). Roles are saved and will be given back when they join.")
        return await ctx.send("User is not in the server (banned? unban first), then run the command again.")

    try:
        given, skipped = await restore_roles(member)
    except discord.HTTPException:
        return await ctx.send("Failed to restore roles.")

    if not given and not skipped:
        return await ctx.send(
            f"{member.mention} already has all saved roles ({len(store[str(user.id)])}). Nothing to restore.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
    msg = f"Restored {len(given)} role(s) for {member.mention}."
    if given:
        msg += "\n" + ", ".join(r.name for r in given)
    if skipped:
        msg += "\nSkipped (deleted / managed / above bot): " + ", ".join(skipped)
    await ctx.send(msg, allowed_mentions=discord.AllowedMentions.none())

@bot.command()
@commands.check(wlcheck)
async def forget(ctx, user: discord.User):
    """,forget <user id / @user> -> loescht die gespeicherten Rollen dieses Users."""
    store = get_role_store(ctx.guild.id)
    if store.pop(str(user.id), None) is None:
        return await ctx.send("No saved roles for this user.")
    write_role_store(ctx.guild.id)
    await ctx.send("Saved roles deleted.")

X7_ROLE_ID = 1538721709798981687  # diese Rolle nimmt/gibt ,X7

@bot.command(name="X7", aliases=["x7"])
@commands.check(wlcheck)
async def x7(ctx):
    """Toggle: nimmt dem Ausfuehrenden (Whitelist oder Owner) nur die X7-Rolle / gibt sie wieder."""
    gid = str(ctx.guild.id)
    uid = str(ctx.author.id)
    me = ctx.guild.me
    member = ctx.guild.get_member(ctx.author.id)
    if member is None:
        return

    guild_state = x7_state.setdefault(gid, {})

    if uid not in guild_state:
        removable = [r for r in member.roles if r.id == X7_ROLE_ID and not r.managed and r < me.top_role]
        if not removable:
            return await ctx.send("You don't have the X7 role (or it is above my top role).")
        guild_state[uid] = [r.id for r in removable]
        save_x7()
        try:
            await member.remove_roles(*removable, reason="X7")
        except discord.HTTPException:
            del guild_state[uid]
            save_x7()
            return await ctx.send("Failed to remove roles — check role hierarchy.")
        await ctx.send("Bye master")
    else:
        roles = [ctx.guild.get_role(r) for r in guild_state[uid]]
        roles = [r for r in roles if r and not r.managed and r < me.top_role and r not in member.roles]
        try:
            if roles:
                await member.add_roles(*roles, reason="X7 back")
        except discord.HTTPException:
            return await ctx.send("Failed to give roles back — check role hierarchy.")
        del guild_state[uid]
        save_x7()
        await ctx.send("Welcome back master")

@bot.command(name="lockdown")
@commands.check(ownercheck)
async def lockdown_cmd(ctx, mode: str = None):
    """,lockdown  -> Lockdown beenden (nur Bot-Owner).  ,lockdown on -> manuell starten."""
    gid = ctx.guild.id
    if mode and mode.lower() == "on":
        if gid in lockdown_state:
            return await ctx.send("Already on lockdown.")
        return await start_lockdown(ctx.guild, f"manual by {ctx.author}")

    if gid not in lockdown_state:
        return await ctx.send("Server is not on lockdown. Use `,lockdown on` to start one.")

    lock_channel_id = lockdown_state[gid].get("channel")
    await ctx.send("Lifting lockdown and restoring roles...")
    restored = await end_lockdown(ctx.guild)
    if ctx.channel.id != lock_channel_id:
        await ctx.send(f"Lockdown lifted. Roles restored for {restored} members.")
    await send_log(ctx.guild, f"🔓 Lockdown lifted by {ctx.author}. Roles restored for {restored} members.")

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
    if not await antinuke_gate(ctx, "kick"):
        return
    await member.kick(reason=reason)
    await ctx.send(f"{member.mention} kicked.")

@bot.command()
@commands.check(wlcheck)
async def ban(ctx, member: discord.Member, *, reason=None):
    if not await antinuke_gate(ctx, "ban"):
        return
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
    # discord.py 2.x: bans() ist ein async iterator
    async for entry in ctx.guild.bans(limit=None):
        try:
            await ctx.guild.unban(entry.user)
        except discord.HTTPException:
            pass
    await ctx.send("All users unbanned.")

# =========================
# SNAP SYSTEM
# =========================

SNAP_GIF = "https://tenor.com/view/salute-cat-cute-yessir-gif-3721562633224755353"

@bot.command()
@commands.check(wlcheck)
async def snap(ctx, member: discord.Member):
    if not await antinuke_gate(ctx, "ban"):
        return
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

        old_position = old_channel.position

        # clone behält Name, Kategorie, Rechte, Topic, Slowmode, NSFW
        new_channel = await old_channel.clone(reason="nuke")
        await old_channel.delete()

        # Position des alten Channels wiederherstellen
        try:
            await new_channel.edit(position=old_position)
        except discord.HTTPException:
            pass

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

    await asyncio.sleep(3)
    try:
        await msg.delete()
    except:
        pass

# =========================
# GIVEAWAY SYSTEM
# =========================

last_gw_message = {}  # guild_id : message_id

@bot.command()
@commands.check(wlcheck)
async def gw(ctx, item: str, time: str):

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
    embed.set_footer(text=f"Started at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

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
            "`,gw_wl add @user`\n"
            "`,gw_wl remove @user`"
        )


bot.run(os.getenv("TOKEN"))
