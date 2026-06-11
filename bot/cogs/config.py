import discord
from discord.ext import commands
import yaml
import io


class Config(commands.Cog):
    """Per-server configuration management."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="config", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def config_group(self, ctx):
        """View or manage server configuration. Use !config view, !config set, !config import, !config export"""
        await ctx.send_help(ctx.command)

    @config_group.command(name="view")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def config_view(self, ctx):
        """View the current server configuration."""
        cfg = self.bot.config_manager.get(ctx.guild.id)
        raw = self.bot.config_manager.get_raw(ctx.guild.id)

        embed = discord.Embed(
            title=f"⚙️ Configuration for {ctx.guild.name}",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Prefix", value=f"`{cfg.get('prefix', '!')}`", inline=True)

        log_ch = cfg.get("log_channel")
        embed.add_field(
            name="Log Channel",
            value=ctx.guild.get_channel(int(log_ch)).mention if log_ch and ctx.guild.get_channel(int(log_ch)) else "Not set",
            inline=True,
        )
        mod_log = cfg.get("mod_log_channel")
        embed.add_field(
            name="Mod Log Channel",
            value=ctx.guild.get_channel(int(mod_log)).mention if mod_log and ctx.guild.get_channel(int(mod_log)) else "Not set",
            inline=True,
        )
        mute_role_id = cfg.get("mute_role")
        mute_role = ctx.guild.get_role(int(mute_role_id)) if mute_role_id else None
        embed.add_field(name="Mute Role", value=mute_role.mention if mute_role else "Auto-create on first use", inline=True)

        automod = cfg.get("automod", {})
        embed.add_field(name="AutoMod", value="✅ Enabled" if automod.get("enabled") else "❌ Disabled", inline=True)

        yaml_str = yaml.dump(raw, default_flow_style=False, allow_unicode=True) if raw else "# No custom config set\n"
        if len(yaml_str) <= 1000:
            embed.add_field(name="Raw Config (YAML)", value=f"```yaml\n{yaml_str}\n```", inline=False)
        else:
            embed.add_field(name="Raw Config", value="Too long to display — use `!config export` to download.", inline=False)

        await ctx.send(embed=embed)

    @config_group.command(name="set")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def config_set(self, ctx, key: str, *, value: str):
        """Set a config value: !config set prefix ? or !config set log_channel #channel
        
        Keys: prefix, log_channel, mod_log_channel, mute_role,
              automod.enabled, automod.anti_spam.enabled, automod.anti_invite.enabled,
              automod.bad_words.enabled, automod.caps_limit.enabled,
              moderation.dm_on_action, logging.message_delete, etc.
        """
        if key in ("log_channel", "mod_log_channel"):
            if ctx.message.channel_mentions:
                value = str(ctx.message.channel_mentions[0].id)
            elif value.isdigit():
                ch = ctx.guild.get_channel(int(value))
                if not ch:
                    return await ctx.send(embed=discord.Embed(
                        description="❌ Channel not found.", color=discord.Color.red()))
                value = str(ch.id)
            else:
                return await ctx.send(embed=discord.Embed(
                    description="❌ Please mention a channel or provide its ID.", color=discord.Color.red()))

        elif key == "mute_role":
            if ctx.message.role_mentions:
                value = str(ctx.message.role_mentions[0].id)
            elif value.isdigit():
                role = ctx.guild.get_role(int(value))
                if not role:
                    return await ctx.send(embed=discord.Embed(
                        description="❌ Role not found.", color=discord.Color.red()))
                value = str(role.id)

        elif value.lower() in ("true", "yes", "on", "1", "enable", "enabled"):
            value = True
        elif value.lower() in ("false", "no", "off", "0", "disable", "disabled"):
            value = False
        elif value.isdigit():
            value = int(value)

        self.bot.config_manager.set_key(ctx.guild.id, key, value)
        await ctx.send(embed=discord.Embed(
            description=f"✅ Set `{key}` to `{value}`.",
            color=discord.Color.green()
        ))

    @config_group.command(name="export")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def config_export(self, ctx):
        """Export your server's config as a YAML file."""
        raw = self.bot.config_manager.get_raw(ctx.guild.id)
        yaml_str = yaml.dump(raw, default_flow_style=False, allow_unicode=True) if raw else "# Empty config\n"
        file = discord.File(
            fp=io.BytesIO(yaml_str.encode()),
            filename=f"config_{ctx.guild.id}.yaml",
        )
        await ctx.send(
            embed=discord.Embed(description="📄 Here's your server config:", color=discord.Color.blurple()),
            file=file,
        )

    @config_group.command(name="import")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def config_import(self, ctx):
        """Import a YAML config file. Attach a .yaml file to your message."""
        if not ctx.message.attachments:
            return await ctx.send(embed=discord.Embed(
                description="❌ Please attach a `.yaml` config file to your message.",
                color=discord.Color.red()
            ))
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith(".yaml"):
            return await ctx.send(embed=discord.Embed(
                description="❌ Only `.yaml` files are accepted.",
                color=discord.Color.red()
            ))
        content = await attachment.read()
        try:
            new_cfg = yaml.safe_load(content.decode("utf-8"))
        except yaml.YAMLError as e:
            return await ctx.send(embed=discord.Embed(
                description=f"❌ Invalid YAML: {e}",
                color=discord.Color.red()
            ))
        if not isinstance(new_cfg, dict):
            return await ctx.send(embed=discord.Embed(
                description="❌ Config must be a YAML mapping (dictionary).",
                color=discord.Color.red()
            ))
        self.bot.config_manager.set(ctx.guild.id, new_cfg)
        await ctx.send(embed=discord.Embed(
            description="✅ Config imported successfully!",
            color=discord.Color.green()
        ))

    @config_group.command(name="reset")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def config_reset(self, ctx):
        """Reset the server config to defaults."""
        self.bot.config_manager.set(ctx.guild.id, {})
        await ctx.send(embed=discord.Embed(
            description="✅ Config reset to defaults.",
            color=discord.Color.green()
        ))

    @commands.command(name="setprefix")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setprefix(self, ctx, prefix: str):
        """Change the bot prefix: !setprefix ?"""
        if len(prefix) > 5:
            return await ctx.send(embed=discord.Embed(
                description="❌ Prefix must be 5 characters or fewer.", color=discord.Color.red()))
        self.bot.config_manager.set_key(ctx.guild.id, "prefix", prefix)
        await ctx.send(embed=discord.Embed(
            description=f"✅ Prefix changed to `{prefix}`.",
            color=discord.Color.green()
        ))

    @commands.command(name="setlogchannel")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setlogchannel(self, ctx, channel: discord.TextChannel):
        """Set the log channel: !setlogchannel #logs"""
        self.bot.config_manager.set_key(ctx.guild.id, "log_channel", channel.id)
        await ctx.send(embed=discord.Embed(
            description=f"✅ Log channel set to {channel.mention}.",
            color=discord.Color.green()
        ))

    @commands.command(name="setmodlog")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setmodlog(self, ctx, channel: discord.TextChannel):
        """Set the mod log channel: !setmodlog #mod-log"""
        self.bot.config_manager.set_key(ctx.guild.id, "mod_log_channel", channel.id)
        await ctx.send(embed=discord.Embed(
            description=f"✅ Mod log channel set to {channel.mention}.",
            color=discord.Color.green()
        ))


async def setup(bot):
    await bot.add_cog(Config(bot))
