"""Session management for LoopTalk test sessions."""

import asyncio
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from loguru import logger


class SessionManager:
    """Manages running LoopTalk test sessions."""

    def __init__(self):
        """Initialize the session manager."""
        self._running_sessions: Dict[int, Dict[str, Any]] = {}
        self._disconnect_handlers: Dict[int, asyncio.Task] = {}

    def add_session(self, test_session_id: int, session_info: Dict[str, Any]):
        """Add a new session to the manager.

        Args:
            test_session_id: ID of the test session
            session_info: Dictionary containing session information
        """
        self._running_sessions[test_session_id] = session_info

    def get_session(self, test_session_id: int) -> Optional[Dict[str, Any]]:
        """Get session information.

        Args:
            test_session_id: ID of the test session

        Returns:
            Session information dictionary or None if not found
        """
        return self._running_sessions.get(test_session_id)

    def remove_session(self, test_session_id: int):
        """Remove a session from the manager.

        Args:
            test_session_id: ID of the test session
        """
        if test_session_id in self._running_sessions:
            del self._running_sessions[test_session_id]

        # Cancel any disconnect handler for this session
        if test_session_id in self._disconnect_handlers:
            handler = self._disconnect_handlers.pop(test_session_id)
            if not handler.done():
                handler.cancel()

    def get_active_count(self) -> int:
        """Get the number of currently active sessions."""
        return len(self._running_sessions)

    def get_active_info(self) -> Dict[str, Any]:
        """Get information about all active sessions."""
        return {
            "count": len(self._running_sessions),
            "sessions": [
                {
                    "test_session_id": session_id,
                    "conversation_id": info["conversation"].id,
                    "start_time": info["start_time"],
                    "duration_seconds": int(
                        (datetime.now(UTC) - info["start_time"]).total_seconds()
                    ),
                }
                for session_id, info in self._running_sessions.items()
            ],
        }

    async def handle_agent_disconnect(
        self, test_session_id: int, disconnected_role: str, stop_callback: callable
    ):
        """Handle when one agent disconnects.

        This will cancel the other agent as well to ensure clean shutdown.

        Args:
            test_session_id: ID of the test session
            disconnected_role: Role that disconnected ("actor" or "adversary")
            stop_callback: Callback to stop the session
        """
        logger.info(
            f"Handling {disconnected_role} disconnect for session {test_session_id}"
        )

        # Check if we already have a disconnect handler running
        if test_session_id in self._disconnect_handlers:
            logger.debug(
                f"Disconnect handler already running for session {test_session_id}"
            )
            return

        # Create a task to handle the disconnect
        async def _handle_disconnect():
            try:
                # Wait a short time to avoid race conditions
                await asyncio.sleep(0.5)

                # Check if session still exists
                session_info = self.get_session(test_session_id)
                if not session_info:
                    logger.debug(f"Session {test_session_id} already stopped")
                    return

                # Stop the session (which will cancel both agents)
                logger.info(
                    f"Stopping session {test_session_id} due to {disconnected_role} disconnect"
                )
                await stop_callback(test_session_id)

            except asyncio.CancelledError:
                logger.debug(
                    f"Disconnect handler cancelled for session {test_session_id}"
                )
                raise
            except Exception as e:
                logger.error(
                    f"Error handling disconnect for session {test_session_id}: {e}"
                )

        # Store the task so we can cancel it if needed
        self._disconnect_handlers[test_session_id] = asyncio.create_task(
            _handle_disconnect()
        )

    def update_audio_metadata(
        self,
        test_session_id: int,
        role: str,
        sample_rate: Optional[int] = None,
        num_channels: Optional[int] = None,
    ):
        """Update audio metadata for a role in a session.

        Args:
            test_session_id: ID of the test session
            role: Either "actor" or "adversary"
            sample_rate: Sample rate of the audio
            num_channels: Number of audio channels
        """
        if test_session_id not in self._running_sessions:
            return

        if "audio_metadata" not in self._running_sessions[test_session_id]:
            self._running_sessions[test_session_id]["audio_metadata"] = {}

        if role not in self._running_sessions[test_session_id]["audio_metadata"]:
            self._running_sessions[test_session_id]["audio_metadata"][role] = {}

        metadata = self._running_sessions[test_session_id]["audio_metadata"][role]
        if sample_rate is not None:
            metadata["sample_rate"] = sample_rate
        if num_channels is not None:
            metadata["num_channels"] = num_channels

    def get_audio_metadata(self, test_session_id: int, role: str) -> Dict[str, Any]:
        """Get audio metadata for a role in a session.

        Args:
            test_session_id: ID of the test session
            role: Either "actor" or "adversary"

        Returns:
            Dictionary with sample_rate and num_channels
        """
        default = {"sample_rate": 16000, "num_channels": 1}

        if test_session_id not in self._running_sessions:
            return default

        metadata = (
            self._running_sessions.get(test_session_id, {})
            .get("audio_metadata", {})
            .get(role, {})
        )

        return {
            "sample_rate": metadata.get("sample_rate", 16000),
            "num_channels": metadata.get("num_channels", 1),
        }
