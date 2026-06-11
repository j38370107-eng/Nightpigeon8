import discord
from discord.ext import commands
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled
from bot.core.level_check import get_user_level
from bot.core.database import get_pool

log = logging.getLogger("bot.tickets")


class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_level(self, ctx, level: int) -> bool:
        user_level = await get_user_level(ctx.guild.id, ctx.author.id, ctx.author)
        return user_level >= level

    async def _get_ticket_number(self, guild_id: int) -> int:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(MAX(ticket_number), 0) + 1 as next FROM tickets WHERE guild_id=$1",
                guild_id
            )
        return row["next"]

    @commands.group(name="ticket", invoke_without_command=True)
    @commands.guild_only()
    async def ticket(self, ctx):
        await ctx.send("Commands: `ticket panel`, `ticket add @user`, `ticket remove @user`, `ticket close [reason]`, `ticket claim`, `ticket delete`")

    @ticket.command(name="panel")
    async def ticket_panel(self, ctx):
        config = await get_config(ctx.guild.id)
        if not is_plugin_enabled(config, "tickets"):
            return
        plugin_cfg = get_plugin_config(config, "tickets")
        manage_level = ((plugin_cfg.get("config", {}) or {}).get("levels", {}) or {}).get("manage", 50)
        if not await self._check_level(ctx, manage_level):
            return await ctx.send("You don't have permission.")

        cfg = plugin_cfg.get("config", {}) or {}
        panel_cfg = cfg.get("panel", {}) or {}
        panel_channel_id = cfg.get("panel_channel")
        if panel_channel_id:
            channel = ctx.guild.get_channel(int(panel_channel_id))
        else:
            channel = ctx.channel

        if not channel:
            return await ctx.send("Panel channel not found.")

        panel_type = panel_cfg.get("type", "button")
        msg_text = panel_cfg.get("message", "Open a support ticket by clicking below.")

        if panel_type == "button":
            btn_label = panel_cfg.get("button_label", "Open Ticket")
            btn_emoji = panel_cfg.get("button_emoji", "🎫")
            btn_style_str = panel_cfg.get("button_style", "primary")
            style_map = {"primary": discord.ButtonStyle.primary, "secondary": discord.ButtonStyle.secondary,
                         "success": discord.ButtonStyle.success, "danger": discord.ButtonStyle.danger}
            btn_style = style_map.get(btn_style_str, discord.ButtonStyle.primary)

            view = discord.ui.View(timeout=None)
            btn = discord.ui.Button(label=btn_label, emoji=btn_emoji, style=btn_style, custom_id=f"ticket_open_{ctx.guild.id}")

            async def btn_callback(interaction: discord.Interaction):
                await self._create_ticket(interaction, config, plugin_cfg)

            btn.callback = btn_callback
            view.add_item(btn)
            await channel.send(content=msg_text, view=view)
            await ctx.send("Ticket panel sent!", delete_after=5)

    async def _create_ticket(self, interaction: discord.Interaction, config, plugin_cfg):
        guild = interaction.guild
        user = interaction.user
        cfg = plugin_cfg.get("config", {}) or {}

        pool = await get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM tickets WHERE guild_id=$1 AND user_id=$2 AND status='open'",
                guild.id, user.id
            )

        max_open = cfg.get("max_open_per_user", 1)
        if existing:
            msgs = plugin_cfg.get("config", {}).get("messages", {}) or {}
            return await interaction.response.send_message(
                msgs.get("ticket_exists", "You already have an open ticket."), ephemeral=True
            )

        # Check blacklist
        async with pool.acquire() as conn:
            blacklisted = await conn.fetchrow(
                "SELECT reason FROM ticket_blacklist WHERE guild_id=$1 AND user_id=$2",
                guild.id, user.id
            )
        if blacklisted:
            msgs = plugin_cfg.get("config", {}).get("messages", {}) or {}
            return await interaction.response.send_message(
                msgs.get("blacklisted", "You are blacklisted from opening tickets."), ephemeral=True
            )

        ticket_number = await self._get_ticket_number(guild.id)
        category_id = cfg.get("category")
        category = guild.get_channel(int(category_id)) if category_id else None
        staff_roles = [guild.get_role(int(r)) for r in (cfg.get("staff_roles", []) or []) if guild.get_role(int(r))]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for role in staff_roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)

        try:
            ticket_channel = await guild.create_text_channel(
                f"ticket-{ticket_number:04d}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {user}"
            )
        except Exception as e:
            log.error(f"Failed to create ticket channel: {e}")
            return await interaction.response.send_message("Failed to create ticket.", ephemeral=True)

        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO tickets (guild_id,channel_id,user_id,ticket_number,status) VALUES ($1,$2,$3,$4,'open')",
                guild.id, ticket_channel.id, user.id, ticket_number
            )

        msgs = cfg.get("messages", {}) or {}
        ticket_msg = msgs.get("ticket_created", "Your ticket has been created: {channel}").format(
            channel=ticket_channel.mention
        )

        close_view = discord.ui.View(timeout=None)
        close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id=f"ticket_close_{ticket_channel.id}")
        claim_btn = discord.ui.Button(label="Claim", style=discord.ButtonStyle.secondary, emoji="✋", custom_id=f"ticket_claim_{ticket_channel.id}")

        async def close_cb(i: discord.Interaction):
            await self._close_ticket(i, ticket_channel.id)

        async def claim_cb(i: discord.Interaction):
            await self._claim_ticket(i, ticket_channel.id)

        close_btn.callback = close_cb
        claim_btn.callback = claim_cb
        close_view.add_item(close_btn)
        close_view.add_item(claim_btn)

        await ticket_channel.send(
            content=f"{user.mention} | Ticket #{ticket_number:04d}",
            embed=discord.Embed(description="Staff will be with you shortly. Use the buttons below to manage this ticket.", color=0x6D78C4),
            view=close_view
        )

        await interaction.response.send_message(ticket_msg, ephemeral=True)

        log_channel_id = cfg.get("log_channel")
        if log_channel_id:
            log_ch = guild.get_channel(int(log_channel_id))
            if log_ch:
                await log_ch.send(embed=discord.Embed(
                    title="Ticket Opened",
                    description=f"Ticket #{ticket_number:04d} opened by {user.mention} → {ticket_channel.mention}",
                    color=0x6CBF8A
                ))

    async def _close_ticket(self, interaction: discord.Interaction, channel_id: int):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tickets WHERE channel_id=$1", channel_id)
        if not row:
            return await interaction.response.send_message("Ticket not found.", ephemeral=True)

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return

        opener = interaction.guild.get_member(row["user_id"])
        if opener:
            try:
                await channel.set_permissions(opener, view_channel=False)
            except Exception:
                pass

        await channel.edit(name=f"closed-{row['ticket_number']:04d}")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE tickets SET status='closed' WHERE channel_id=$1", channel_id)

        await channel.send(embed=discord.Embed(
            description=f"🔒 Ticket closed by {interaction.user.mention}",
            color=0xC46D7A
        ))
        await interaction.response.send_message("Ticket closed.", ephemeral=True)

    async def _claim_ticket(self, interaction: discord.Interaction, channel_id: int):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE tickets SET claimed_by=$1 WHERE channel_id=$2", interaction.user.id, channel_id)

        await interaction.channel.send(embed=discord.Embed(
            description=f"✋ Ticket claimed by {interaction.user.mention}",
            color=0x6D78C4
        ))
        await interaction.response.send_message("You claimed this ticket.", ephemeral=True)

    @ticket.command(name="close")
    async def ticket_close(self, ctx, *, reason: str = "No reason provided"):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tickets WHERE channel_id=$1", ctx.channel.id)
        if not row:
            return await ctx.send("This is not a ticket channel.")
        await self._close_ticket_cmd(ctx, row, reason)

    async def _close_ticket_cmd(self, ctx, row, reason):
        opener = ctx.guild.get_member(row["user_id"])
        if opener:
            try:
                await ctx.channel.set_permissions(opener, view_channel=False)
            except Exception:
                pass
        await ctx.channel.edit(name=f"closed-{row['ticket_number']:04d}")
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE tickets SET status='closed' WHERE channel_id=$1", ctx.channel.id)
        await ctx.send(f"🔒 Ticket closed by {ctx.author.mention}. Reason: {reason}")

    @ticket.command(name="add")
    async def ticket_add(self, ctx, user: discord.Member):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM tickets WHERE channel_id=$1", ctx.channel.id)
        if not row:
            return await ctx.send("This is not a ticket channel.")
        await ctx.channel.set_permissions(user, view_channel=True, send_messages=True)
        await ctx.send(f"Added {user.mention} to the ticket.")

    @ticket.command(name="remove")
    async def ticket_remove(self, ctx, user: discord.Member):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM tickets WHERE channel_id=$1", ctx.channel.id)
        if not row:
            return await ctx.send("This is not a ticket channel.")
        await ctx.channel.set_permissions(user, view_channel=False)
        await ctx.send(f"Removed {user.mention} from the ticket.")

    @ticket.command(name="claim")
    async def ticket_claim(self, ctx):
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM tickets WHERE channel_id=$1", ctx.channel.id)
        if not row:
            return await ctx.send("This is not a ticket channel.")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE tickets SET claimed_by=$1 WHERE channel_id=$2", ctx.author.id, ctx.channel.id)
        await ctx.send(f"✋ Ticket claimed by {ctx.author.mention}")

    @ticket.command(name="delete")
    async def ticket_delete(self, ctx):
        config = await get_config(ctx.guild.id)
        plugin_cfg = get_plugin_config(config, "tickets")
        manage_level = ((plugin_cfg.get("config", {}) or {}).get("levels", {}) or {}).get("manage", 50)
        if not await self._check_level(ctx, manage_level):
            return await ctx.send("You don't have permission.")

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM tickets WHERE channel_id=$1", ctx.channel.id)
        if not row:
            return await ctx.send("This is not a ticket channel.")
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM tickets WHERE channel_id=$1", ctx.channel.id)
        await ctx.send("Deleting ticket channel in 3 seconds...")
        import asyncio
        await asyncio.sleep(3)
        await ctx.channel.delete(reason=f"Ticket deleted by {ctx.author}")

    @commands.command(name="blacklist")
    @commands.guild_only()
    async def blacklist(self, ctx, user: discord.Member, *, reason: str = "No reason provided"):
        config = await get_config(ctx.guild.id)
        plugin_cfg = get_plugin_config(config, "tickets")
        manage_level = ((plugin_cfg.get("config", {}) or {}).get("levels", {}) or {}).get("manage", 50)
        if not await self._check_level(ctx, manage_level):
            return await ctx.send("You don't have permission.")
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ticket_blacklist (guild_id,user_id,reason) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                ctx.guild.id, user.id, reason
            )
        await ctx.send(f"{user} has been blacklisted from opening tickets.")

    @commands.command(name="unblacklist")
    @commands.guild_only()
    async def unblacklist(self, ctx, user: discord.Member):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM ticket_blacklist WHERE guild_id=$1 AND user_id=$2", ctx.guild.id, user.id)
        await ctx.send(f"{user} has been removed from the ticket blacklist.")


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))
