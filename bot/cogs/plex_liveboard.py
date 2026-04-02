import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.modals import _get_ping_ids_for_report, build_staff_ping


PLEX_LOGS_CHANNEL_ID = 1475676107960356977

SERVER_ROLE_IDS = {
    "OMEGA": 1466939252024541423,
    "DELTA": 1472852339730681998,
    "ALPHA": 1466938881764233396,
}

SERVER_LABELS = {
    "OMEGA": {"OMEGA", "SS EAST"},
    "ALPHA": {"ALPHA"},
    "DELTA": {"DELTA"},
}

SERVER_DISPLAY_NAMES = {
    "OMEGA": "Omega",
    "ALPHA": "Alpha",
    "DELTA": "Delta",
}

DEFAULT_STATUS = {
    "OMEGA": "Unknown",
    "ALPHA": "Unknown",
    "DELTA": "Unknown",
}


def _is_staff(member: discord.Member, staff_role_id: int) -> bool:
    return any(r.id == staff_role_id for r in member.roles)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime) -> str:
    return f"<t:{int(dt.timestamp())}:R>"


def _normalize_server_name(raw: str) -> str | None:
    s = (raw or "").strip().upper()
    for canonical, aliases in SERVER_LABELS.items():
        if s in aliases:
            return canonical
    return None


def _display_server_name(server_name: str) -> str:
    return SERVER_DISPLAY_NAMES.get(str(server_name).upper(), str(server_name).title())


def _parse_server_footer(text: str | None) -> str | None:
    footer = (text or "").strip()
    if not footer.startswith("server="):
        return None
    return _normalize_server_name(footer.split("=", 1)[1])


def _clear_confirmation_phrase(server_name: str) -> str:
    return f"I CONFIRM {str(server_name).upper()} IS UP"


def _extract_message_text(msg: discord.Message) -> str:
    parts: list[str] = []

    if msg.content:
        parts.append(msg.content)

    for e in msg.embeds:
        if e.title:
            parts.append(e.title)
        if e.description:
            parts.append(e.description)
        for field in e.fields:
            if field.name:
                parts.append(field.name)
            if field.value:
                parts.append(field.value)

    return "\n".join(p for p in parts if p).strip()


def _parse_server_from_message(content: str) -> str | None:
    text = (content or "").strip().upper()
    if not text:
        return None

    for candidate in ("SS EAST", "OMEGA", "ALPHA", "DELTA"):
        if f"NOTIFICATION FOR ({candidate})" in text:
            return _normalize_server_name(candidate)
        if f"TAUTULLI ({candidate})" in text:
            return _normalize_server_name(candidate)

    return None


def _parse_state_from_message(content: str) -> str | None:
    text = (content or "").lower()
    if "the plex media server is down" in text:
        return "Down"
    if "the plex media server is up" in text:
        return "Up"
    return None


class PlexServerChoice(app_commands.Choice[str]):
    pass


class PlexStatusChoice(app_commands.Choice[str]):
    pass


class PlexLiveboardReportView(discord.ui.View):
    def __init__(self, cog: "PlexLiveboardCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Report my server as down",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="plexliveboard:report_down",
    )
    async def report_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_liveboard_report_button(interaction)


class PlexDownReportConfirmView(discord.ui.View):
    def __init__(self, cog: "PlexLiveboardCog", owner_id: int, server_name: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.owner_id = int(owner_id)
        self.server_name = str(server_name).upper()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This confirmation isn’t for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.confirm_down_report(interaction, self.server_name)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)


class PlexDownReportServerSelect(discord.ui.Select):
    def __init__(self, cog: "PlexLiveboardCog", server_names: list[str]):
        options = [
            discord.SelectOption(label=_display_server_name(server_name), value=server_name)
            for server_name in server_names
        ]
        super().__init__(placeholder="Choose the server to report", min_values=1, max_values=1, options=options)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.present_down_report_confirmation(interaction, self.values[0], edit_message=True)


class PlexDownReportServerPickerView(discord.ui.View):
    def __init__(self, cog: "PlexLiveboardCog", owner_id: int, server_names: list[str]):
        super().__init__(timeout=120)
        self.owner_id = int(owner_id)
        self.add_item(PlexDownReportServerSelect(cog, server_names))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This server picker isn’t for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)


class PlexDownReportClearView(discord.ui.View):
    def __init__(self, cog: "PlexLiveboardCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Clear report",
        style=discord.ButtonStyle.success,
        custom_id="plexliveboard:clear_report",
    )
    async def clear_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.clear_down_report(interaction)


class PlexDownReportClearModal(discord.ui.Modal):
    def __init__(self, cog: "PlexLiveboardCog", message_id: int, server_name: str):
        super().__init__(title=f"Confirm {_display_server_name(server_name)} is up")
        self.cog = cog
        self.message_id = int(message_id)
        self.server_name = str(server_name).upper()
        self.expected_phrase = _clear_confirmation_phrase(self.server_name)

        self.confirmation_phrase = discord.ui.TextInput(
            label="Type the confirmation phrase",
            placeholder=self.expected_phrase,
            required=True,
            max_length=len(self.expected_phrase),
        )
        self.add_item(self.confirmation_phrase)

    async def on_submit(self, interaction: discord.Interaction):
        if str(self.confirmation_phrase).strip() != self.expected_phrase:
            return await interaction.response.send_message(
                f"❌ Confirmation phrase must exactly match: **{self.expected_phrase}**",
                ephemeral=True,
            )

        await self.cog.finish_clear_down_report(interaction, self.message_id, self.server_name)


class PlexLiveboardCog(commands.Cog):
    def __init__(self, bot, db, cfg):
        self.bot = bot
        self.db = db
        self.cfg = cfg
        self._lock = asyncio.Lock()
        self.liveboard_view = PlexLiveboardReportView(self)
        self.clear_report_view = PlexDownReportClearView(self)
        self.plex_liveboard_loop.start()

    def cog_unload(self):
        self.plex_liveboard_loop.cancel()

    def build_plex_embed(self, statuses: dict[str, str]) -> discord.Embed:
        embed = discord.Embed(
            title="🖥️ Plex Liveboard",
            description=(
                "This board updates automatically from Plex webhook logs.\n"
                "Only Plex server up/down notifications affect this board.\n\n"
                "If your assigned server is shown as up when it is actually down, use the button below to report it.\n\n"
                f"Last refreshed: {_ts(_utcnow())}"
            ),
        )

        def fmt(value: str) -> str:
            if value == "Up":
                return "🟢 Up"
            if value == "Down":
                return "🔴 Down"
            return "⚪ Unknown"

        embed.add_field(name="Omega", value=fmt(statuses.get("OMEGA", "Unknown")), inline=True)
        embed.add_field(name="Alpha", value=fmt(statuses.get("ALPHA", "Unknown")), inline=True)
        embed.add_field(name="Delta", value=fmt(statuses.get("DELTA", "Unknown")), inline=True)

        return embed

    def build_staff_report_embed(self, reporter: discord.Member, server_name: str) -> discord.Embed:
        now = _utcnow()
        pretty_name = _display_server_name(server_name)
        embed = discord.Embed(
            title=f"Plex server reported down: {pretty_name}",
            description="A user reported that their assigned Plex server is down while the liveboard showed it as up.",
            color=discord.Color.orange(),
            timestamp=now,
        )
        embed.add_field(name="Reporter", value=reporter.mention, inline=True)
        embed.add_field(name="Assigned server", value=pretty_name, inline=True)
        embed.add_field(name="Reported at", value=_ts(now), inline=False)
        embed.set_footer(text=f"server={server_name}")
        return embed

    def build_cleared_report_embed(
        self,
        reporter: discord.abc.User | None,
        clearer: discord.Member,
        server_name: str,
    ) -> discord.Embed:
        now = _utcnow()
        pretty_name = _display_server_name(server_name)
        reporter_text = reporter.mention if reporter else "Unknown user"
        embed = discord.Embed(
            title=f"Plex server report cleared: {pretty_name}",
            description="Report cleared. Server status set back to Up.",
            color=discord.Color.green(),
            timestamp=now,
        )
        embed.add_field(name="Original reporter", value=reporter_text, inline=True)
        embed.add_field(name="Server", value=pretty_name, inline=True)
        embed.add_field(name="Cleared by", value=clearer.mention, inline=False)
        embed.add_field(name="Cleared at", value=_ts(now), inline=False)
        embed.set_footer(text=f"server={server_name}")
        return embed

    def get_member_servers(self, member: discord.Member) -> list[str]:
        return [server for server, role_id in SERVER_ROLE_IDS.items() if any(role.id == role_id for role in member.roles)]

    def get_staff_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel = guild.get_channel(int(self.cfg.staff_channel_id or 0))
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    def is_staff(self, member: discord.Member) -> bool:
        return _is_staff(member, self.cfg.staff_role_id)

    async def get_reporter_from_embed(
        self,
        guild: discord.Guild,
        embed: discord.Embed | None,
    ) -> discord.abc.User | None:
        if not embed:
            return None

        for field in embed.fields:
            if field.name != "Reporter":
                continue

            raw = field.value.strip()
            if not (raw.startswith("<@") and raw.endswith(">")):
                return None

            user_id = raw.strip("<@!>")
            if not user_id.isdigit():
                return None

            reporter = guild.get_member(int(user_id))
            if reporter is not None:
                return reporter

            try:
                return await self.bot.fetch_user(int(user_id))
            except Exception:
                return None

        return None

    async def get_current_statuses(self, guild_id: int) -> dict[str, str]:
        stored = self.db.get_plex_statuses(guild_id)
        statuses = dict(DEFAULT_STATUS)
        statuses.update(stored)
        return statuses

    async def update_plex_liveboard(self, guild_id: int):
        settings = self.db.get_plex_liveboard(guild_id)
        if not settings:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        channel = guild.get_channel(int(settings["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return

        statuses = await self.get_current_statuses(guild_id)
        embed = self.build_plex_embed(statuses)

        try:
            msg = await channel.fetch_message(int(settings["message_id"]))
            await msg.edit(embed=embed, view=self.liveboard_view)
        except discord.NotFound:
            self.db.clear_plex_liveboard(guild_id)
        except discord.Forbidden:
            pass

    async def handle_liveboard_report_button(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        matched_servers = self.get_member_servers(interaction.user)
        if not matched_servers:
            return await interaction.response.send_message("❌ You don’t have an assigned Plex server role.", ephemeral=True)

        if len(matched_servers) > 1:
            return await interaction.response.send_message(
                "Choose which assigned server you want to report.",
                view=PlexDownReportServerPickerView(self, interaction.user.id, matched_servers),
                ephemeral=True,
            )

        await self.present_down_report_confirmation(interaction, matched_servers[0], edit_message=False)

    async def present_down_report_confirmation(
        self,
        interaction: discord.Interaction,
        server_name: str,
        *,
        edit_message: bool,
    ):
        if not interaction.guild:
            if edit_message:
                return await interaction.response.edit_message(content="Use this in a server.", view=None)
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        statuses = await self.get_current_statuses(interaction.guild.id)
        if statuses.get(server_name, "Unknown") != "Up":
            if edit_message:
                return await interaction.response.edit_message(
                    content=(
                        f"ℹ️ {_display_server_name(server_name)} is already stored as **{statuses.get(server_name, 'Unknown')}**."
                        " You can only report it from this panel while it shows as **Up**."
                    ),
                    view=None,
                )
            return await interaction.response.send_message(
                f"ℹ️ {_display_server_name(server_name)} is already stored as **{statuses.get(server_name, 'Unknown')}**."
                " You can only report it from this panel while it shows as **Up**.",
                ephemeral=True,
            )

        content = (
            f"Report **{_display_server_name(server_name)}** as down?\n"
            "This will notify staff and immediately set the liveboard status to **Down** until staff clears it."
        )
        view = PlexDownReportConfirmView(self, interaction.user.id, server_name)

        if edit_message:
            return await interaction.response.edit_message(content=content, view=view)

        await interaction.response.send_message(content, view=view, ephemeral=True)

    async def confirm_down_report(self, interaction: discord.Interaction, server_name: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.edit_message(content="Use this in a server.", view=None)

        statuses = await self.get_current_statuses(interaction.guild.id)
        if statuses.get(server_name, "Unknown") != "Up":
            return await interaction.response.edit_message(
                content=(
                    f"ℹ️ {_display_server_name(server_name)} is no longer stored as **{statuses.get(server_name, 'Unknown')}**. "
                    "No report was sent."
                ),
                view=None,
            )

        staff_channel = self.get_staff_channel(interaction.guild)
        if not staff_channel:
            return await interaction.response.edit_message(
                content="❌ Staff channel not found. No report was sent.",
                view=None,
            )

        self.db.set_plex_status(interaction.guild.id, server_name, "Down", _utcnow().isoformat())
        try:
            await self.update_plex_liveboard(interaction.guild.id)
            ping_text = ""
            if self.db.get_report_pings_enabled():
                ping_text = build_staff_ping(_get_ping_ids_for_report(self.cfg, "vod"))

            await staff_channel.send(
                content=ping_text,
                embed=self.build_staff_report_embed(interaction.user, server_name),
                view=self.clear_report_view,
            )
        except Exception:
            self.db.set_plex_status(interaction.guild.id, server_name, "Up", _utcnow().isoformat())
            await self.update_plex_liveboard(interaction.guild.id)
            return await interaction.response.edit_message(
                content="❌ I couldn’t post the report in the staff channel, so the status was left unchanged.",
                view=None,
            )

        await interaction.response.edit_message(
            content=f"✅ Report sent. {_display_server_name(server_name)} is now marked as **Down**.",
            view=None,
        )

    async def clear_down_report(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.message or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)

        if not self.is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)

        if interaction.channel_id != int(self.cfg.staff_channel_id or 0):
            return await interaction.response.send_message("❌ Use this in the staff reports channel.", ephemeral=True)

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        server_name = _parse_server_footer(embed.footer.text if embed and embed.footer else None)
        if not server_name:
            return await interaction.response.send_message("❌ Couldn’t determine which server this report belongs to.", ephemeral=True)

        await interaction.response.send_modal(
            PlexDownReportClearModal(self, interaction.message.id, server_name)
        )

    async def finish_clear_down_report(self, interaction: discord.Interaction, message_id: int, server_name: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)

        if not self.is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)

        if interaction.channel_id != int(self.cfg.staff_channel_id or 0):
            return await interaction.response.send_message("❌ Use this in the staff reports channel.", ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Staff channel not found.", ephemeral=True)

        try:
            message = await channel.fetch_message(int(message_id))
        except discord.NotFound:
            return await interaction.response.send_message("❌ The original report message no longer exists.", ephemeral=True)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I can’t access the original report message.", ephemeral=True)

        embed = message.embeds[0] if message.embeds else None
        current_server_name = _parse_server_footer(embed.footer.text if embed and embed.footer else None)
        if current_server_name != server_name:
            return await interaction.response.send_message("❌ This report changed before it could be cleared. Try again.", ephemeral=True)

        reporter = await self.get_reporter_from_embed(interaction.guild, embed)

        self.db.set_plex_status(interaction.guild.id, server_name, "Up", _utcnow().isoformat())
        await self.update_plex_liveboard(interaction.guild.id)

        await message.edit(
            embed=self.build_cleared_report_embed(reporter, interaction.user, server_name),
            view=None,
        )
        await interaction.response.send_message(
            f"✅ Cleared report for **{_display_server_name(server_name)}**.",
            ephemeral=True,
        )

    async def handle_plex_log_message(self, msg: discord.Message):
        if not msg.guild or msg.channel.id != PLEX_LOGS_CHANNEL_ID:
            return

        content = _extract_message_text(msg)
        server = _parse_server_from_message(content)
        state = _parse_state_from_message(content)

        if not server or not state:
            return

        self.db.set_plex_status(msg.guild.id, server, state, _utcnow().isoformat())
        await self.update_plex_liveboard(msg.guild.id)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.webhook_id is None:
            return

        try:
            await self.handle_plex_log_message(msg)
        except Exception:
            pass

    @tasks.loop(minutes=3)
    async def plex_liveboard_loop(self):
        async with self._lock:
            for s in self.db.list_plex_liveboards():
                try:
                    await self.update_plex_liveboard(int(s["guild_id"]))
                except Exception:
                    continue

    @plex_liveboard_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="plexliveboardstart",
        description="Create (or move) the Plex liveboard message to a channel (staff only).",
    )
    @app_commands.describe(channel="Channel to post the Plex liveboard in")
    async def plexliveboardstart(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not _is_staff(interaction.user, self.cfg.staff_role_id):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        statuses = await self.get_current_statuses(interaction.guild.id)
        embed = self.build_plex_embed(statuses)

        try:
            msg = await channel.send(embed=embed, view=self.liveboard_view)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I can’t post in that channel.", ephemeral=True)

        self.db.set_plex_liveboard(interaction.guild.id, channel.id, msg.id)
        await interaction.response.send_message(f"✅ Plex liveboard started in {channel.mention}.", ephemeral=True)

    @app_commands.command(
        name="plexliveboardrefresh",
        description="Manually refresh the Plex liveboard right now (staff only).",
    )
    async def plexliveboardrefresh(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not _is_staff(interaction.user, self.cfg.staff_role_id):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        await interaction.response.send_message("Refreshing…", ephemeral=True)
        await self.update_plex_liveboard(interaction.guild.id)

    @app_commands.command(
        name="plexliveboardstop",
        description="Stop the Plex liveboard updates (staff only).",
    )
    async def plexliveboardstop(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not _is_staff(interaction.user, self.cfg.staff_role_id):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        self.db.clear_plex_liveboard(interaction.guild.id)
        await interaction.response.send_message("✅ Plex liveboard stopped.", ephemeral=True)

    @app_commands.command(
        name="plexset",
        description="Manually set a Plex server status (staff only).",
    )
    @app_commands.describe(
        server="Which Plex server to update",
        status="The status to set",
    )
    @app_commands.choices(
        server=[
            app_commands.Choice(name="Omega", value="OMEGA"),
            app_commands.Choice(name="Alpha", value="ALPHA"),
            app_commands.Choice(name="Delta", value="DELTA"),
        ],
        status=[
            app_commands.Choice(name="Up", value="Up"),
            app_commands.Choice(name="Down", value="Down"),
            app_commands.Choice(name="Unknown", value="Unknown"),
        ],
    )
    async def plexset(
        self,
        interaction: discord.Interaction,
        server: app_commands.Choice[str],
        status: app_commands.Choice[str],
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not _is_staff(interaction.user, self.cfg.staff_role_id):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        self.db.set_plex_status(interaction.guild.id, server.value, status.value, _utcnow().isoformat())
        await self.update_plex_liveboard(interaction.guild.id)

        await interaction.response.send_message(
            f"✅ Set **{server.name}** to **{status.value}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="plexstatus",
        description="Show the currently stored Plex server statuses (staff only).",
    )
    async def plexstatus(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not _is_staff(interaction.user, self.cfg.staff_role_id):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        statuses = await self.get_current_statuses(interaction.guild.id)

        await interaction.response.send_message(
            (
                f"**Omega:** {statuses.get('OMEGA', 'Unknown')}\n"
                f"**Alpha:** {statuses.get('ALPHA', 'Unknown')}\n"
                f"**Delta:** {statuses.get('DELTA', 'Unknown')}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="plexclear",
        description="Reset all stored Plex server statuses to Unknown (staff only).",
    )
    async def plexclear(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)

        if not _is_staff(interaction.user, self.cfg.staff_role_id):
            return await interaction.response.send_message("❌ Not allowed.", ephemeral=True)

        self.db.clear_plex_statuses(interaction.guild.id)
        await self.update_plex_liveboard(interaction.guild.id)

        await interaction.response.send_message("✅ Cleared stored Plex statuses.", ephemeral=True)


async def setup(bot):
    cog = PlexLiveboardCog(bot, bot.db, bot.cfg)
    bot.add_view(cog.liveboard_view)
    bot.add_view(cog.clear_report_view)
    await bot.add_cog(cog)
