import discord
from db.database import get_member_by_discord_id, verify_member
from discord.ext import commands
from utils import get_logger
from utils.config import GENERAL_MEMBER_ROLE_ID, SBI_GUILD_ID, VERIFICATION_CHANNEL_ID

logger = get_logger(__name__)

EMBED_COLOR = discord.Color.from_rgb(34, 197, 94)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot: discord.Bot = bot

    admin = discord.SlashCommandGroup(
        name="admin", description="Admin commands", guild_ids=[SBI_GUILD_ID]
    )

    @admin.command(name="add_member", description="Add SBI member to DB")
    @commands.has_permissions(administrator=True)
    async def add_member(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member,
        eid: str,
        email: str,
    ):
        if not member.nick:
            await ctx.respond(
                "Please make sure the member has their nickname set as their name!"
            )
            return

        try:
            await verify_member(
                name=member.nick,
                eid=eid,
                email=email,
                discord_id=member.id,
            )
        except Exception:
            await ctx.respond(
                "Something went wrong adding the member to the database.",
                ephemeral=True,
            )
            return

        await ctx.respond(
            f"Added {member.name} ({member.nick}) to the SBI member's DB."
        )

    @admin.command(
        name="send_verification",
        description="Send a message with the verification form to a user.",
    )
    @commands.has_permissions(administrator=True)
    async def send_verification(
        self, ctx: discord.ApplicationContext, member: discord.Member
    ):
        await member.send(
            "Hello, please fill out this form so we can add you to our database.",
            view=VerificationView(bot=self.bot, timeout=None),
        )


class VerificationModal(discord.ui.Modal):
    def __init__(self, bot, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.bot: discord.Bot = bot

        self.add_item(
            discord.ui.InputText(label="What is your first name?", max_length=50)
        )
        self.add_item(
            discord.ui.InputText(
                label="What is your last name?",
                max_length=50,
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="What is your UTEID?",
                style=discord.InputTextStyle.short,
                max_length=50,
            )
        )
        self.add_item(
            discord.ui.InputText(
                label="What is your email?",
                style=discord.InputTextStyle.short,
                max_length=50,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            existing = await get_member_by_discord_id(interaction.user.id)
        except Exception:
            await interaction.response.send_message(
                "Something went wrong. Please try again later.", ephemeral=True
            )
            return

        if existing:
            await interaction.response.send_message(
                "You are already verified!", ephemeral=True
            )
            return

        first = self.children[0].value.strip()
        last = self.children[1].value.strip()
        uteid = self.children[2].value.strip()
        email = self.children[3].value.strip()

        if not all([first, last, uteid, email]):
            await interaction.response.send_message(
                "All fields are required. Please try again.", ephemeral=True
            )
            return

        if "@" not in email or "." not in email:
            await interaction.response.send_message(
                "Please enter a valid email address.", ephemeral=True
            )
            return

        try:
            await verify_member(
                name=f"{first} {last}",
                eid=uteid,
                email=email,
                discord_id=interaction.user.id,
            )
        except Exception:
            await interaction.response.send_message(
                "Something went wrong. Please contact a Director for help.",
                ephemeral=True,
            )
            return

        guild: discord.Guild | None = self.bot.get_guild(SBI_GUILD_ID)
        member: discord.Member = await guild.fetch_member(interaction.user.id)
        await member.edit(nick=f"{first} {last}")
        await member.add_roles(guild.get_role(GENERAL_MEMBER_ROLE_ID))

        embed = discord.Embed(
            title=f"{interaction.user.name}'s Verification", color=EMBED_COLOR
        )
        embed.add_field(
            name="Member", value=f"<@{interaction.user.id}>", inline=False
        )
        embed.add_field(name=self.children[0].label, value=self.children[0].value)
        embed.add_field(name=self.children[1].label, value=self.children[1].value)
        embed.add_field(name=self.children[2].label, value=self.children[2].value)
        embed.add_field(name=self.children[3].label, value=self.children[3].value)
        embed.set_footer(text="Steve | Sustainable Building Initiative")
        embed.set_author(
            name=self.bot.user.name,
            icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None,
        )

        logger.info(f"New member verified: {first} {last}")
        channel = self.bot.get_channel(VERIFICATION_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)
        await interaction.response.send_message(
            "Thanks for verifying!", ephemeral=True
        )


class VerificationView(discord.ui.View):
    def __init__(self, bot, timeout):
        super().__init__(timeout=timeout)
        self.bot: discord.Bot = bot

    @discord.ui.button(label="Start Verification")
    async def button_callback(self, button, interaction):
        try:
            existing = await get_member_by_discord_id(interaction.user.id)
        except Exception:
            await interaction.response.send_message(
                "Something went wrong. Please try again later.", ephemeral=True
            )
            return

        if existing:
            await interaction.response.send_message(
                "You are already verified!", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            VerificationModal(self.bot, title="Verification")
        )


def setup(bot):
    bot.add_cog(Admin(bot))
