import asyncio
import traceback
from datetime import datetime
from pathlib import Path

import discord
from ai import start_transcription
from db import Meeting, create_meeting, create_recording, delete_meeting, update_meeting
from discord.ext import commands, tasks
from utils import get_logger

logger = get_logger(__name__)


class RecordingView(discord.ui.View):
    def __init__(self, _stop_recording, timeout):
        super().__init__(timeout=timeout)
        self._stop_recording = _stop_recording

    async def disable_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @discord.ui.button(label="Stop Recording", style=discord.ButtonStyle.red)
    async def stop_recording_callback(self, button, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._stop_recording(interaction.guild.id)
        await self.disable_buttons()
        await interaction.followup.edit_message(interaction.message.id, view=self)


class Recording(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.connections = {}
        self.recording_tasks = {}
        self.max_recording_duration = 3600 * 5  # 5 hour max recording
        # self.socket_keepalive.start()
        self.send_packet.start()

    @commands.slash_command(
        name="join",
        description="Join the voice channel and start recording.",
    )
    @commands.guild_only()
    async def join(self, ctx: discord.ApplicationContext):
        voice = ctx.author.voice

        if not voice:
            embed = discord.Embed(
                title="Not in Voice Channel",
                description="You need to be in a voice channel to start recording!",
                color=discord.Color.red(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        if ctx.guild.id in self.connections:
            embed = discord.Embed(
                title="Already Recording",
                description="Already recording in this server! Use `/stop` first.",
                color=discord.Color.orange(),
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

        try:
            # Defer the response since connection might take time
            await ctx.defer()

            # Connect to voice channel
            vc: discord.VoiceClient = await voice.channel.connect(
                reconnect=True, timeout=10.0
            )

            # Create initial status embed
            start_time = datetime.now()
            status_embed = self._create_status_embed(start_time, voice.channel.id)
            status_view = RecordingView(self._stop_recording, timeout=None)
            status_message = await ctx.followup.send(
                embed=status_embed, view=status_view
            )

            meeting = await create_meeting(
                Meeting(
                    guild_id=ctx.guild.id,
                    channel_id=voice.channel.id,
                    start=start_time,
                )
            )

            if not meeting:
                embed = discord.Embed(
                    title="Recording Failed",
                    description="Failed to create meeting record. Please try again.",
                    color=discord.Color.red(),
                )
                await ctx.followup.send(embed=embed, ephemeral=True)
                await vc.disconnect()
                return

            # Store connection
            self.connections[ctx.guild.id] = {
                "voice_client": vc,
                "voice_channel_id": voice.channel.id,
                "channel": ctx.channel,
                "start_time": start_time,
                "users_recorded": set(),
                "status_message": status_message,
                "status_view": status_view,
                "meeting": meeting,
            }
            # Play recording start sound
            await self._play_recording_start_sound(vc)

            # Start recording with timeout protection
            vc.start_recording(
                SafeWaveSink(),
                self.recording_finished_callback,
                ctx.channel,
                ctx.guild.id,
                sync_start=True,
            )

            # Set up automatic timeout
            timeout_task = asyncio.create_task(
                self._auto_stop_recording(ctx.guild.id, self.max_recording_duration)
            )
            self.recording_tasks[ctx.guild.id] = timeout_task

            logger.info(
                f"Started recording in guild {ctx.guild.id}, channel {voice.channel.name}"
            )

        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="Connection Timeout",
                description="Failed to connect to voice channel (timeout)",
                color=discord.Color.red(),
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            logger.error(f"Timeout connecting to voice channel in guild {ctx.guild.id}")
        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            logger.error(traceback.format_exc())
            embed = discord.Embed(
                title="Recording Failed",
                description=f"Failed to start recording: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.followup.send(embed=embed, ephemeral=True)
            # Clean up on error
            await self._cleanup_recording(ctx.guild.id)

    async def recording_finished_callback(self, sink, channel, guild_id):
        """Callback when recording finishes"""
        try:
            logger.info(f"Recording finished for guild {guild_id}")

            # Cancel timeout task if it exists
            if guild_id in self.recording_tasks:
                self.recording_tasks[guild_id].cancel()
                del self.recording_tasks[guild_id]

            connection_info = self.connections.get(guild_id)
            if not connection_info:
                logger.warning(f"No connection info found for guild {guild_id}")
                return

            meeting: Meeting = self.connections[guild_id]["meeting"]

            # Check if we have any audio data
            if not hasattr(sink, "audio_data") or not sink.audio_data:
                embed = discord.Embed(
                    title="Recording Complete",
                    description="Recording finished, but no audio was captured. Make sure users are speaking!",
                    color=discord.Color.orange(),
                )
                await channel.send(embed=embed)
                logger.info(f"No audio data captured for guild {guild_id}")
                await delete_meeting(
                    meeting.id
                )  # Delete meeting as nothing was recorded
                return

            # Process audio files
            files = []
            recorded_users = []

            for user_id, audio_data in sink.audio_data.items():
                try:
                    if audio_data and hasattr(audio_data, "file") and audio_data.file:
                        # Reset file position
                        audio_data.file.seek(0)

                        # Check if file has content
                        file_size = len(audio_data.file.read())
                        audio_data.file.seek(0)

                        if file_size > 0:
                            file_name = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{sink.encoding}"
                            try:
                                file_id = await create_recording(
                                    file_name, audio_data.file
                                )
                                files.append(file_id)
                                recorded_users.append(user_id)
                                logger.info(
                                    f"Created audio file for user {user_id}, size: {file_size} bytes"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error creating audio file for user {user_id}: {e}"
                                )
                        else:
                            logger.warning(f"Empty audio file for user {user_id}")

                except Exception as e:
                    logger.error(f"Error processing audio for user {user_id}: {e}")
                    continue

            # Send results
            if files:
                message: discord.Message = await channel.send(
                    embed=discord.Embed(
                        title="Processing recordings and saving files...",
                        color=discord.Color.blurple(),
                    )
                )

                # Add meeting metadata when complete
                meeting.recordings = files
                meeting.participants = recorded_users
                meeting.end = datetime.now()

                await update_meeting(meeting.id, meeting)

                duration = datetime.now() - connection_info["start_time"]
                duration_str = str(duration).split(".")[0]

                embed = discord.Embed(
                    title="Recording Complete!", color=discord.Color.green()
                )
                embed.add_field(name="Meeting ID", value=f"`{meeting.id}`")
                embed.add_field(name="Duration", value=duration_str)
                embed.add_field(
                    name="Recorded Users",
                    value=", ".join([f"<@{user}>" for user in recorded_users]),
                    inline=False,
                )
                embed.set_footer(
                    text=f"Recording finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

                await message.edit(embed=embed)
                await self._cleanup_recording(guild_id)
                ts_result = await start_transcription(meeting=meeting)
                if ts_result:
                    await channel.send(
                        embed=discord.Embed(
                            title="Transcription success!",
                            description="A copy of the transcription has been saved successfully.",
                            color=discord.Color.green(),
                        )
                    )

                return

            else:
                embed = discord.Embed(
                    title="Recording Complete",
                    description="Recording finished, but no valid audio files were created. "
                    "This might happen if users weren't speaking or there were connection issues.",
                    color=discord.Color.orange(),
                )
                await channel.send(embed=embed)
                logger.warning(f"No valid audio files created for guild {guild_id}")

        except Exception as e:
            logger.error(f"Error in recording callback for guild {guild_id}: {e}")
            logger.error(traceback.format_exc())
            try:
                embed = discord.Embed(
                    title="Recording Error",
                    description=f"Recording finished, but there was an error processing the audio: {str(e)}",
                    color=discord.Color.red(),
                )
                await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to send error message to channel: {e}")
        finally:
            # Always clean up
            await self._cleanup_recording(guild_id)

    @commands.slash_command(name="stop", description="Stop the current recording")
    @commands.guild_only()
    async def stop(self, ctx: discord.ApplicationContext):
        try:
            if ctx.guild.id not in self.connections:
                embed = discord.Embed(
                    title="Not Recording",
                    description="Not currently recording in this server.",
                    color=discord.Color.red(),
                )
                await ctx.respond(embed=embed, ephemeral=True)
                return

            await self._stop_recording(ctx.guild.id)
            await ctx.delete()
        except Exception as e:
            logger.error(f"Error stopping recording in guild {ctx.guild.id}: {e}")
            embed = discord.Embed(
                title="Stop Error",
                description=f"Error stopping recording: {str(e)}",
                color=discord.Color.red(),
            )
            await ctx.respond(embed=embed)
            # Force cleanup even if there was an error
            await self._cleanup_recording(ctx.guild.id)

    async def _stop_recording(self, guild_id: int):
        if guild_id not in self.connections:
            return
        connection_info = self.connections[guild_id]
        vc: discord.VoiceClient = connection_info["voice_client"]

        # Update status embed and disable buttons
        await self._update_status_to_ended(guild_id)
        vc.stop_recording()
        logger.info(f"Manually stopped recording in guild {guild_id}")

    async def _update_status_to_ended(self, guild_id: int):
        """Update the status embed to show 'Recording ended.' and disable buttons"""
        try:
            connection_info = self.connections.get(guild_id)
            if not connection_info or "status_message" not in connection_info:
                return

            status_message = connection_info["status_message"]
            status_view = connection_info["status_view"]

            ended_embed = self._create_status_embed(
                connection_info["start_time"],
                connection_info["voice_channel_id"],
                ended=True,
            )

            await status_view.disable_buttons()
            await status_message.edit(embed=ended_embed, view=status_view)

        except Exception as e:
            logger.error(f"Error updating status embed for guild {guild_id}: {e}")

    async def _auto_stop_recording(self, guild_id: int, duration: int):
        """Automatically stop recording after specified duration"""
        try:
            await asyncio.sleep(duration)

            if guild_id in self.connections:
                logger.info(
                    f"Auto-stopping recording for guild {guild_id} after {duration} seconds"
                )
                connection_info = self.connections[guild_id]
                vc = connection_info["voice_client"]
                vc.stop_recording()

                # Send timeout message
                try:
                    embed = discord.Embed(
                        title="Recording Timeout",
                        description=f"Recording automatically stopped after {duration // 60} minutes (max duration reached)",
                        color=discord.Color.orange(),
                    )
                    await connection_info["channel"].send(embed=embed)
                except Exception as e:
                    logger.error(
                        f"Failed to send timeout message for guild {guild_id}: {e}"
                    )

        except asyncio.CancelledError:
            logger.info(f"Auto-stop task cancelled for guild {guild_id}")
        except Exception as e:
            logger.error(f"Error in auto-stop task for guild {guild_id}: {e}")

    async def _cleanup_recording(self, guild_id: int):
        """Clean up recording resources"""
        try:
            # Cancel timeout task
            if guild_id in self.recording_tasks:
                self.recording_tasks[guild_id].cancel()
                del self.recording_tasks[guild_id]

            # Disconnect voice client
            if guild_id in self.connections:
                connection_info = self.connections[guild_id]
                vc = connection_info["voice_client"]

                if vc and vc.is_connected():
                    await vc.disconnect()
                    logger.info(f"Disconnected voice client for guild {guild_id}")

                del self.connections[guild_id]

        except Exception as e:
            logger.error(f"Error cleaning up recording for guild {guild_id}: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state updates to manage recordings"""
        # If bot is disconnected from voice channel, clean up recording
        if member == self.bot.user and before.channel and not after.channel:
            for guild_id, connection_info in list(self.connections.items()):
                if connection_info["voice_client"].channel == before.channel:
                    logger.info(
                        f"Bot disconnected from voice channel, cleaning up recording for guild {guild_id}"
                    )
                    await self._cleanup_recording(guild_id)

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        logger.info("Cleaning up all recordings on cog unload")
        # Cancel socket keepalive task
        self.send_packet.cancel()
        # Cancel status update task only if it exists and is running
        if hasattr(self, "status_update_task") and self.status_update_task.is_running():
            self.status_update_task.cancel()
        for guild_id in list(self.connections.keys()):
            asyncio.create_task(self._cleanup_recording(guild_id))

    async def _play_recording_start_sound(self, voice_client: discord.VoiceClient):
        """Play the recording started sound effect"""
        try:
            # Get path relative to this file's location
            audio_path = (
                Path(__file__).parent.parent / "audio" / "recording_started.wav"
            )
            if audio_path.exists():
                # Create audio source
                audio_source = discord.FFmpegPCMAudio(str(audio_path))

                # Play the audio
                voice_client.play(audio_source)

                # Wait for audio to finish playing
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)

                logger.info("Played recording start sound")
            else:
                logger.warning(f"Recording start sound file not found: {audio_path}")
        except Exception as e:
            logger.error(f"Error playing recording start sound: {e}")

    def _create_status_embed(
        self, start_time: datetime, voice_channel_id: int, ended: bool = False
    ) -> discord.Embed:
        """Create a status embed for the recording"""

        if ended:
            title = "Recording ended."
            color = discord.Color.red()
        else:
            title = "🔴 Recording..."
            color = discord.Color.green()

        unix_time = round(datetime.timestamp(start_time))
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=start_time,
        )
        embed.add_field(
            name="**Started:**",
            value=f"<t:{unix_time}:T> (<t:{unix_time}:R>)",
            inline=False,
        )
        embed.add_field(
            name="**Channel:**", value=f"<#{voice_channel_id}>", inline=False
        )

        return embed

    # https://github.com/Pycord-Development/pycord/issues/2310
    # https://github.com/imayhaveborkedit/discord-ext-voice-recv/issues/8
    # @tasks.loop(seconds=10)
    # async def socket_keepalive(self):
    #     """
    #     Send silent packets to prevent Discord from closing the listening socket.
    #     This fixes Opus decoding errors caused by socket timeouts during periods of silence.
    #     Only sends packets during active recordings to avoid unnecessary traffic.
    #     """
    #     try:
    #         if self.vc:
    #             # Send silent audio packet to keep socket alive during recording
    #             self.vc.send_audio_packet(b"\xf8\xff\xfe", encode=False)
    #             logger.info("Sent keepalive packet")
    #     except Exception as e:
    #         logger.warning(f"Error sending keepalive packet for guild: {e}")
    #     return

    @tasks.loop(seconds=10)
    async def send_packet(self):
        """
        Send silent packets to all active voice connections to prevent
        Discord from closing the listening socket during periods of silence.
        """
        for conn in self.connections.values():
            try:
                vc = conn["voice_client"]
                if vc and vc.is_connected():
                    vc.send_audio_packet(b"\xf8\xff\xfe", encode=False)
            except Exception as e:
                logger.warning(f"Error sending keepalive packet: {e}")


class SafeWaveSink(discord.sinks.MP3Sink):
    """A safer version of MP3Sink with simple error handling"""

    def __init__(self):
        super().__init__()
        self.encoding = "mp3"

    def write(self, data, user):
        """Override write method with error handling"""
        try:
            if data and len(data) > 0:
                return super().write(data, user)
        except Exception as e:
            # Silently skip bad audio data to prevent crashes
            logger.debug(f"Skipped audio data for user {user}: {e}")

    def cleanup(self):
        """Override cleanup with error handling"""
        try:
            return super().cleanup()
        except Exception as e:
            logger.debug(f"Error during cleanup: {e}")


def setup(bot):
    bot.add_cog(Recording(bot))
