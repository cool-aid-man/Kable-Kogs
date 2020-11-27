import asyncio
import contextlib
import logging
import re
from collections import namedtuple
from datetime import datetime, timedelta
from typing import Optional, Union, cast

import discord
from redbot.core import checks, commands, i18n, modlog
from redbot.core.commands import BadArgument, Converter
from redbot.core.utils.chat_formatting import bold, humanize_number, pagify
from redbot.core.utils.mod import get_audit_reason, is_allowed_by_hierarchy

_id_regex = re.compile(r"([0-9]{15,21})$")
_mention_regex = re.compile(r"<@!?([0-9]{15,21})>$")


log = logging.getLogger("red.mod")
_ = i18n.Translator("Mod", __file__)


class RawUserIds(Converter):
    async def convert(self, ctx, argument):
        if match := _id_regex.match(argument) or _mention_regex.match(argument):
            return int(match.group(1))

        raise BadArgument(_("{} doesn't look like a valid user ID.").format(argument))


class IDKick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    """
    Kick a list of IDs from server.
    """

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True)
    @checks.admin_or_permissions(kick_members=True)
    async def idkick(
        self,
        ctx: commands.Context,
        user_ids: commands.Greedy[RawUserIds],
        *,
        reason: str = None,
    ):
        """Kick a list of users by ID

        If a reason is specified, it will be the reason that shows up
        in the audit log
        """
        kicked = []
        errors = {}

        async def show_results():
            text = _("Kicked {num} users from the server.").format(
                num=humanize_number(len(kicked))
            )
            if errors:
                text += _("\nErrors:\n")
                text += "\n".join(errors.values())

            for p in pagify(text):
                await ctx.send(p)

        def remove_processed(ids):
            return [_id for _id in ids if _id not in kicked and _id not in errors]

        user_ids = list(set(user_ids))  # No dupes

        author = ctx.author
        guild = ctx.guild

        if not user_ids:
            await ctx.send_help()
            return

        if not guild.me.guild_permissions.kick_members:
            return await ctx.send(_("I lack the permissions to do this."))

        kick_list = [RawUserIds]
        for entry in kick_list:
            for user_id in user_ids:
                if entry.user.id == user_id:
                    errors[user_id] = _("User {user_id} is not in guild.").format(
                         user_id=user_id
                         )

        user_ids = remove_processed(user_ids)

        if not user_ids:
            await show_results()
            return

        for user_id in user_ids:
            user = guild.get_member(user_id)
            if user is not None:
                try:
                    result = await guild.kick(
                    user=user, reason=reason
                    )
                    if result is True:
                        kicked.append(user_id)
                    else:
                        errors[user_id] = _("Failed to kick user {user_id}: {reason}").format(
                        user_id=user_id, reason=result
                        )
                except Exception as e:
                    errors[user_id] = _("Failed to kick user {user_id}: {reason}").format(
                    user_id=user_id, reason=e
                    )

        user_ids = remove_processed(user_ids)

        if not user_ids:
            await show_results()
            return

        for user_id in user_ids:
            user = discord.Object(id=user_id)
            audit_reason = get_audit_reason(author, reason)
            queue_entry = (guild.id, user_id)
            try:
                await guild.kick(user, reason=audit_reason)
                log.info("{}({}) kicked {}".format(author.name, author.id, user_id))
            except discord.NotFound:
                errors[user_id] = _("User {user_id} does not exist.").format(user_id=user_id)
                continue
            except discord.Forbidden:
                errors[user_id] = _("Could not kick {user_id}: missing permissions.").format(
                    user_id=user_id
                )
                continue
            else:
                kicked.append(user_id)
        await show_results()