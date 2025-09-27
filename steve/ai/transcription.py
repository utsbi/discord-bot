import asyncio
import os
import tempfile
from typing import Optional

import assemblyai as aai
from db import Meeting, get_meeting, update_meeting
from db.database import storage
from utils import get_logger
from utils.config import APPWRITE_BUCKET_ID_MEETINGS, ASSEMBLYAI_API_KEY

aai.settings.api_key = ASSEMBLYAI_API_KEY
logger = get_logger(__name__)

"""
This is the best AMONG US!!!!!!!!!!!
Input troll cmds here: rm all
even more trolling
"""

async def start_transcription(meeting: Meeting) -> bool:
    """
    Combine multiple audio recordings into one track and start transcription.

    Args:
        meeting (Meeting): Meeting object containing audio recordings

    Returns:
        bool: True if transcription started successfully, False otherwise
    """
    if not meeting.recordings:
        logger.warning(f"No recordings found for meeting {meeting.id}")
        return False

    if not meeting.id:
        logger.error("Meeting must have an ID to start transcription")
        return False

    try:
        # Download all audio files from storage
        temp_files = []
        for recording_id in meeting.recordings:
            temp_file = await _download_recording(recording_id)
            if temp_file:
                temp_files.append(temp_file)
            else:
                logger.error(f"Failed to download recording {recording_id}")
                return False

        if not temp_files:
            logger.error("No audio files downloaded successfully")
            return False

        # Combine audio files using ffmpeg
        combined_file = await _combine_audio_files(temp_files)
        if not combined_file:
            logger.error("Failed to combine audio files")
            return False

        # Upload to AssemblyAI and start transcription
        config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.nano)
        transcriber = aai.Transcriber(config=config)
        transcript = await asyncio.to_thread(transcriber.transcribe, combined_file)

        if transcript.error:
            logger.error(f"Transcription failed: {transcript.error}")
            return False

        # Update meeting with transcription URL
        meeting.transcription_id = transcript.id
        meeting.transcription = transcript.text

        # Save updated meeting
        success = await update_meeting(meeting.id, meeting)
        if success:
            logger.info(f"Transcription started for meeting {meeting.id}")
        else:
            logger.error(
                f"Failed to update meeting {meeting.id} with transcription data"
            )

        return success

    except Exception as e:
        logger.error(f"Error starting transcription for meeting {meeting.id}: {e}")
        return False
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except OSError:
                pass
        if "combined_file" in locals() and combined_file:
            try:
                os.unlink(combined_file)
            except OSError:
                pass


async def _download_recording(recording_id: str) -> Optional[str]:
    """
    Download a recording from storage to a temporary file.

    Args:
        recording_id (str): ID of the recording to download

    Returns:
        Optional[str]: Path to temporary file if successful, None otherwise
    """
    try:
        # Get file from storage
        file_data = await asyncio.to_thread(
            storage.get_file_download,
            bucket_id=APPWRITE_BUCKET_ID_MEETINGS,
            file_id=recording_id,
        )

        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        with os.fdopen(temp_fd, "wb") as temp_file:
            temp_file.write(file_data)

        return temp_path

    except Exception as e:
        logger.error(f"Error downloading recording {recording_id}: {e}")
        return None


async def _combine_audio_files(file_paths: list[str]) -> Optional[str]:
    """
    Combine multiple audio files into one using ffmpeg.

    Args:
        file_paths (list[str]): List of paths to audio files to combine

    Returns:
        Optional[str]: Path to combined audio file if successful, None otherwise
    """
    if not file_paths:
        return None

    if len(file_paths) == 1:
        # Only one file, just return its path
        return file_paths[0]

    try:
        # Create temporary output file
        temp_fd, output_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)

        # Build ffmpeg command for combining audio files
        # Format: ffmpeg -i file1.mp3 -i file2.mp3 -i file3.mp3 -filter_complex "[0:a][1:a][2:a]amix=3[aud]" -map "[aud]" -c:a mp3 output.mp3

        cmd = ["ffmpeg", "-y"]  # -y to overwrite output file

        # Add input files
        for file_path in file_paths:
            cmd.extend(["-i", file_path])

        # Build filter complex for mixing
        inputs = []
        for i in range(len(file_paths)):
            inputs.append(f"[{i}:a]")

        filter_complex = f"{''.join(inputs)}amix={len(file_paths)}[aud]"

        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "[aud]",
                "-c:a",
                "mp3",
                output_path,
            ]
        )

        # Run ffmpeg command
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"ffmpeg failed with return code {process.returncode}")
            logger.error(f"ffmpeg stderr: {stderr.decode()}")
            return None

        return output_path

    except Exception as e:
        logger.error(f"Error combining audio files: {e}")
        return None


async def get_transcription(id: str) -> str | None:
    """
    Get the transcription text for a meeting by ID.

    Args:
        id (str): The ID of the meeting to get transcription for

    Returns:
        str | None: The transcription text if available, None otherwise
    """
    meeting = await get_meeting(id)
    return meeting.transcription if meeting else None
