import discord
from cogs.admin import VerificationView
from discord.ext import commands
from utils import get_logger

logger = get_logger(__name__)


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="help", description="help command")
    async def help(self, ctx: discord.ApplicationContext):
        await ctx.respond("help command")

    @commands.slash_command(name="verification", description="Get verified!")
    async def verification(self, ctx: discord.ApplicationContext):
        await ctx.respond(
            "Click the button to verify.",
            view=VerificationView(bot=self.bot, timeout=None),
        )


def setup(bot):
    bot.add_cog(Utility(bot))
