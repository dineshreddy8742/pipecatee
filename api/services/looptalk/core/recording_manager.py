"""Recording management for LoopTalk sessions."""

import wave
from pathlib import Path
from typing import Dict, Optional, Tuple

from loguru import logger

from api.enums import StorageBackend
from api.services.storage import storage_fs


class RecordingManager:
    """Manages audio recording and transcript files for LoopTalk sessions."""

    def __init__(self, base_dir: Path):
        """Initialize the recording manager.

        Args:
            base_dir: Base directory for temporary recordings
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_recording_paths(self, test_session_id: int, role: str) -> Dict[str, Path]:
        """Get file paths for recordings.

        Args:
            test_session_id: ID of the test session
            role: Either "actor" or "adversary"

        Returns:
            Dictionary with paths for audio, transcript, and temp audio files
        """
        session_dir = self.base_dir / f"session_{test_session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)

        return {
            "audio": session_dir / f"{role}_audio.wav",
            "transcript": session_dir / f"{role}_transcript.txt",
            "temp_audio": session_dir / f"{role}_audio_temp.pcm",
        }

    def convert_pcm_to_wav(
        self,
        test_session_id: int,
        role: str,
        sample_rate: int = 16000,
        num_channels: int = 1,
    ) -> Optional[Path]:
        """Convert PCM audio file to WAV format.

        Args:
            test_session_id: ID of the test session
            role: Either "actor" or "adversary"
            sample_rate: Sample rate of the audio
            num_channels: Number of audio channels

        Returns:
            Path to the WAV file if successful, None otherwise
        """
        paths = self.get_recording_paths(test_session_id, role)

        # Check if PCM file exists
        if not paths["temp_audio"].exists():
            logger.warning(f"No audio recorded for {role} in session {test_session_id}")
            return None

        try:
            # Read PCM data
            with open(paths["temp_audio"], "rb") as f:
                pcm_data = f.read()

            # Write WAV file
            with wave.open(str(paths["audio"]), "wb") as wav_file:
                wav_file.setnchannels(num_channels)
                wav_file.setsampwidth(2)  # 16-bit audio
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_data)

            # Remove temporary PCM file
            paths["temp_audio"].unlink()

            logger.info(
                f"Converted audio to WAV for {role} in session {test_session_id}: {paths['audio']}"
            )
            return paths["audio"]

        except Exception as e:
            logger.error(
                f"Failed to convert audio to WAV for {role} in session {test_session_id}: {e}"
            )
            return None

    async def upload_recording_to_s3(
        self, test_session_id: int, role: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Upload recording and transcript to S3.

        Args:
            test_session_id: ID of the test session
            role: Either "actor" or "adversary"

        Returns:
            Tuple of (audio_url, transcript_url) or (None, None) if failed
        """
        paths = self.get_recording_paths(test_session_id, role)
        audio_url = None
        transcript_url = None

        # Import here to avoid circular imports

        current_backend = StorageBackend.get_current_backend()
        logger.info(
            f"LOOPTALK UPLOAD: Using {current_backend.label} (code: {current_backend.code}) for session {test_session_id}, role: {role}"
        )

        # Upload audio if exists
        if paths["audio"].exists():
            audio_key = f"looptalk/recordings/{test_session_id}/{role}_audio.wav"
            try:
                success = await storage_fs.aupload_file(str(paths["audio"]), audio_key)
                if success:
                    audio_url = audio_key
                    logger.info(
                        f"Uploaded {role} audio to {current_backend.label}: {audio_key}"
                    )
                else:
                    logger.error(
                        f"Failed to upload {role} audio to {current_backend.label}"
                    )
            except Exception as e:
                logger.error(
                    f"Error uploading {role} audio to {current_backend.label}: {e}"
                )

        # Upload transcript if exists
        if paths["transcript"].exists():
            transcript_key = (
                f"looptalk/transcripts/{test_session_id}/{role}_transcript.txt"
            )
            try:
                success = await storage_fs.aupload_file(
                    str(paths["transcript"]), transcript_key
                )
                if success:
                    transcript_url = transcript_key
                    logger.info(
                        f"Uploaded {role} transcript to {current_backend.label}: {transcript_key}"
                    )
                else:
                    logger.error(
                        f"Failed to upload {role} transcript to {current_backend.label}"
                    )
            except Exception as e:
                logger.error(
                    f"Error uploading {role} transcript to {current_backend.label}: {e}"
                )

        return audio_url, transcript_url

    def cleanup_session_files(self, test_session_id: int):
        """Clean up local files for a session.

        Args:
            test_session_id: ID of the test session
        """
        session_dir = self.base_dir / f"session_{test_session_id}"
        if session_dir.exists():
            try:
                import shutil

                shutil.rmtree(session_dir)
                logger.debug(f"Cleaned up local files for session {test_session_id}")
            except Exception as e:
                logger.error(f"Failed to clean up session files: {e}")

    def get_recording_info(self, test_session_id: int) -> Dict[str, any]:
        """Get information about recordings for a test session.

        Args:
            test_session_id: ID of the test session

        Returns:
            Dictionary with recording information
        """
        session_dir = self.base_dir / f"session_{test_session_id}"

        info = {
            "test_session_id": test_session_id,
            "recording_dir": str(session_dir),
            "files": {},
        }

        for role in ["actor", "adversary"]:
            paths = self.get_recording_paths(test_session_id, role)
            role_info = {}

            # Check audio file
            if paths["audio"].exists():
                role_info["audio"] = {
                    "path": str(paths["audio"]),
                    "size_bytes": paths["audio"].stat().st_size,
                }

            # Check transcript file
            if paths["transcript"].exists():
                role_info["transcript"] = {
                    "path": str(paths["transcript"]),
                    "size_bytes": paths["transcript"].stat().st_size,
                }

            if role_info:
                info["files"][role] = role_info

        return info
