import discord
from discord.ext import commands
import logging
from bot.core.config_loader import get_config, get_plugin_config, is_plugin_enabled
from bot.core.database import get_pool

log = logging.getLogger("bot.reaction_roles")


class ReactionRolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def setup_reaction_roles(self, guild: discord.Guild):
        config = await get_config(guild.id)
        if not is_plugin_enabled(config, "reaction_roles"):
            return
        plugin_cfg = get_plugin_config(config, "reaction_roles")
        groups = plugin_cfg.get("groups", []) or []

        for group in groups:
            rtype = group.get("type", "emoji")
            channel_id = group.get("channel_id")
            if not channel_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if not channel:
                continue

            if rtype == "button":
                await self._setup_button_group(guild, channel, group)
            elif rtype == "dropdown":
                await self._setup_dropdown_group(guild, channel, group)

    async def _setup_button_group(self, guild, channel, group):
        roles_cfg = group.get("roles", []) or []
        if not roles_cfg:
            return

        message_text = group.get("message", "Click a button to get a role!")
        view = discord.ui.View(timeout=None)

        for role_cfg in roles_cfg:
            role_id = role_cfg.get("role")
            label = role_cfg.get("label", "Role")
            emoji = role_cfg.get("emoji")
            style_str = role_cfg.get("style", "primary")
            style_map = {
                "primary": discord.ButtonStyle.primary,
                "secondary": discord.ButtonStyle.secondary,
                "success": discord.ButtonStyle.success,
                "danger": discord.ButtonStyle.danger,
            }
            style = style_map.get(style_str, discord.ButtonStyle.primary)

            async def make_callback(rid):
                async def callback(interaction: discord.Interaction):
                    role = interaction.guild.get_role(int(rid))
                    if not role:
                        return await interaction.response.send_message("Role not found.", ephemeral=True)
                    member = interaction.user
                    if role in member.roles:
                        await member.remove_roles(role)
                        await interaction.response.send_message(f"Removed role **{role.name}**.", ephemeral=True)
                    else:
                        await member.add_roles(role)
                        await interaction.response.send_message(f"Added role **{role.name}**.", ephemeral=True)
                return callback

            btn = discord.ui.Button(label=label, style=style, emoji=emoji or discord.utils.MISSING)
            btn.callback = await make_callback(role_id)
            view.add_item(btn)

        try:
            await channel.send(content=message_text, view=view)
        except Exception as e:
            log.error(f"Failed to send button group: {e}")

    async def _setup_dropdown_group(self, guild, channel, group):
        roles_cfg = group.get("roles", []) or []
        if not roles_cfg:
            return

        placeholder = group.get("placeholder", "Select your roles...")
        min_values = group.get("min_values", 0)
        max_values = min(group.get("max_values", 1), len(roles_cfg))

        options = []
        for role_cfg in roles_cfg:
            options.append(discord.SelectOption(
                label=role_cfg.get("label", "Role"),
                description=role_cfg.get("description", "")[:100],
                emoji=role_cfg.get("emoji"),
                value=str(role_cfg.get("role")),
            ))

        view = discord.ui.View(timeout=None)
        select = discord.ui.Select(
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=options,
        )

        async def select_callback(interaction: discord.Interaction):
            member = interaction.user
            selected_ids = [int(v) for v in interaction.data.get("values", [])]
            all_option_ids = [int(o.value) for o in options]
            added, removed = [], []

            for role_id in all_option_ids:
                role = interaction.guild.get_role(role_id)
                if not role:
                    continue
                if role_id in selected_ids and role not in member.roles:
                    await member.add_roles(role)
                    added.append(role.name)
                elif role_id not in selected_ids and role in member.roles:
                    await member.remove_roles(role)
                    removed.append(role.name)

            parts = []
            if added:
                parts.append(f"Added: {', '.join(added)}")
            if removed:
                parts.append(f"Removed: {', '.join(removed)}")
            msg = "\n".join(parts) or "No changes."
            await interaction.response.send_message(msg, ephemeral=True)

        select.callback = select_callback
        view.add_item(select)

        try:
            await channel.send(content=group.get("message", "Select your roles:"), view=view)
        except Exception as e:
            log.error(f"Failed to send dropdown group: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or payload.member and payload.member.bot:
            return
        await self._handle_reaction(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        await self._handle_reaction(payload, add=False)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent, add: bool):
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        config = await get_config(guild.id)
        if not is_plugin_enabled(config, "reaction_roles"):
            return

        plugin_cfg = get_plugin_config(config, "reaction_roles")
        groups = plugin_cfg.get("groups", []) or []

        for group in groups:
            if group.get("type") != "emoji":
                continue
            if int(group.get("message_id", 0)) != payload.message_id:
                continue
            if int(group.get("channel_id", 0)) != payload.channel_id:
                continue

            emoji_str = str(payload.emoji)
            roles_map = group.get("roles", {}) or {}
            role_id = roles_map.get(emoji_str)
            if not role_id:
                continue

            role = guild.get_role(int(role_id))
            if not role:
                continue

            member = guild.get_member(payload.user_id)
            if not member or member.bot:
                continue

            try:
                if add:
                    await member.add_roles(role, reason="Reaction role")
                else:
                    await member.remove_roles(role, reason="Reaction role removed")
            except Exception as e:
                log.error(f"Reaction role error: {e}")


async def setup(bot):
    cog = ReactionRolesCog(bot)
    await bot.add_cog(cog)
