from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    WebSocket,
)
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.looptalk.orchestrator import LoopTalkTestOrchestrator

router = APIRouter(prefix="/looptalk")


# Request/Response Models
class CreateTestSessionRequest(BaseModel):
    name: str
    actor_workflow_id: int
    adversary_workflow_id: int
    config: Dict[str, Any] = Field(default_factory=dict)


class StartTestSessionRequest(BaseModel):
    test_session_id: int


class CreateLoadTestRequest(BaseModel):
    name_prefix: str
    actor_workflow_id: int
    adversary_workflow_id: int
    test_count: int = Field(ge=1, le=10)
    config: Dict[str, Any] = Field(default_factory=dict)


class TestSessionResponse(BaseModel):
    id: int
    name: str
    status: str
    actor_workflow_id: int
    adversary_workflow_id: int
    load_test_group_id: Optional[str]
    test_index: Optional[int]
    config: Dict[str, Any]
    results: Optional[Dict[str, Any]]
    error: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class ConversationResponse(BaseModel):
    id: int
    test_session_id: int
    duration_seconds: Optional[int]
    actor_recording_url: Optional[str]
    adversary_recording_url: Optional[str]
    combined_recording_url: Optional[str]
    transcript: Optional[Dict[str, Any]]
    metrics: Optional[Dict[str, Any]]
    created_at: datetime
    ended_at: Optional[datetime]


# Note: Turn tracking is handled by Langfuse, not exposed via API


class LoadTestStatsResponse(BaseModel):
    total: int
    pending: int
    running: int
    completed: int
    failed: int
    sessions: List[Dict[str, Any]]


# Singleton orchestrator instance
_orchestrator: Optional[LoopTalkTestOrchestrator] = None


def get_orchestrator() -> LoopTalkTestOrchestrator:
    """Get or create the LoopTalk orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LoopTalkTestOrchestrator(db_client=db_client)
    return _orchestrator


@router.post("/test-sessions", response_model=TestSessionResponse)
async def create_test_session(
    request: CreateTestSessionRequest, user: UserModel = Depends(get_user)
):
    """Create a new LoopTalk test session."""

    # Verify user has access to both workflows
    actor_workflow = await db_client.get_workflow(request.actor_workflow_id, user.id)
    if not actor_workflow:
        raise HTTPException(status_code=404, detail="Actor workflow not found")

    adversary_workflow = await db_client.get_workflow(
        request.adversary_workflow_id, user.id
    )
    if not adversary_workflow:
        raise HTTPException(status_code=404, detail="Adversary workflow not found")

    # Create test session
    test_session = await db_client.create_test_session(
        organization_id=user.selected_organization_id,
        name=request.name,
        actor_workflow_id=request.actor_workflow_id,
        adversary_workflow_id=request.adversary_workflow_id,
        config=request.config,
    )

    return test_session


@router.get("/test-sessions", response_model=List[TestSessionResponse])
async def list_test_sessions(
    status: Optional[str] = None,
    load_test_group_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    user: UserModel = Depends(get_user),
):
    """List LoopTalk test sessions."""

    test_sessions = await db_client.list_test_sessions(
        organization_id=user.selected_organization_id,
        status=status,
        load_test_group_id=load_test_group_id,
        limit=limit,
        offset=offset,
    )

    return test_sessions


@router.get("/test-sessions/{test_session_id}", response_model=TestSessionResponse)
async def get_test_session(test_session_id: int, user: UserModel = Depends(get_user)):
    """Get a specific test session."""

    test_session = await db_client.get_test_session(
        test_session_id=test_session_id, organization_id=user.selected_organization_id
    )

    if not test_session:
        raise HTTPException(status_code=404, detail="Test session not found")

    return test_session


@router.post("/test-sessions/{test_session_id}/start")
async def start_test_session(
    test_session_id: int,
    background_tasks: BackgroundTasks,
    user: UserModel = Depends(get_user),
    orchestrator: LoopTalkTestOrchestrator = Depends(get_orchestrator),
):
    """Start a LoopTalk test session."""

    # Verify test session exists and user has access
    test_session = await db_client.get_test_session(
        test_session_id=test_session_id, organization_id=user.selected_organization_id
    )

    if not test_session:
        raise HTTPException(status_code=404, detail="Test session not found")

    if test_session.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Test session is {test_session.status}, not pending",
        )

    # Start test session in background
    background_tasks.add_task(
        orchestrator.start_test_session,
        test_session_id=test_session_id,
        organization_id=user.selected_organization_id,
    )

    return {"message": "Test session starting", "test_session_id": test_session_id}


@router.post("/test-sessions/{test_session_id}/stop")
async def stop_test_session(
    test_session_id: int,
    user: UserModel = Depends(get_user),
    orchestrator: LoopTalkTestOrchestrator = Depends(get_orchestrator),
):
    """Stop a running test session."""

    # Verify test session exists and user has access
    test_session = await db_client.get_test_session(
        test_session_id=test_session_id, organization_id=user.selected_organization_id
    )

    if not test_session:
        raise HTTPException(status_code=404, detail="Test session not found")

    if test_session.status != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Test session is {test_session.status}, not running",
        )

    # Stop test session
    result = await orchestrator.stop_test_session(test_session_id=test_session_id)

    return result


@router.get("/test-sessions/{test_session_id}/conversation")
async def get_test_session_conversation(
    test_session_id: int, user: UserModel = Depends(get_user)
):
    """Get conversation details for a test session."""

    # Verify test session exists and user has access
    test_session = await db_client.get_test_session(
        test_session_id=test_session_id, organization_id=user.selected_organization_id
    )

    if not test_session:
        raise HTTPException(status_code=404, detail="Test session not found")

    # Get conversation
    if test_session.conversations:
        conversation = test_session.conversations[
            0
        ]  # For now, one conversation per session

        # Note: Turn details are available in Langfuse, not here
        return {
            "conversation": conversation,
            "message": "Turn details are tracked in Langfuse",
        }

    return {"conversation": None}


@router.post("/load-tests", response_model=Dict[str, Any])
async def create_load_test(
    request: CreateLoadTestRequest,
    background_tasks: BackgroundTasks,
    user: UserModel = Depends(get_user),
    orchestrator: LoopTalkTestOrchestrator = Depends(get_orchestrator),
):
    """Create and start a load test."""

    # Verify user has access to both workflows
    actor_workflow = await db_client.get_workflow(request.actor_workflow_id, user.id)
    if not actor_workflow:
        raise HTTPException(status_code=404, detail="Actor workflow not found")

    adversary_workflow = await db_client.get_workflow(
        request.adversary_workflow_id, user.id
    )
    if not adversary_workflow:
        raise HTTPException(status_code=404, detail="Adversary workflow not found")

    # Start load test in background
    result = await orchestrator.start_load_test(
        organization_id=user.selected_organization_id,
        name_prefix=request.name_prefix,
        actor_workflow_id=request.actor_workflow_id,
        adversary_workflow_id=request.adversary_workflow_id,
        config=request.config,
        test_count=request.test_count,
    )

    return result


@router.get(
    "/load-tests/{load_test_group_id}/stats", response_model=LoadTestStatsResponse
)
async def get_load_test_stats(
    load_test_group_id: str, user: UserModel = Depends(get_user)
):
    """Get statistics for a load test group."""

    stats = await db_client.get_load_test_group_stats(
        load_test_group_id=load_test_group_id,
        organization_id=user.selected_organization_id,
    )

    return stats


@router.get("/active-tests")
async def get_active_tests(
    orchestrator: LoopTalkTestOrchestrator = Depends(get_orchestrator),
    user: UserModel = Depends(get_user),
):
    """Get information about currently active test sessions."""

    return orchestrator.get_active_test_info()


@router.websocket("/test-sessions/{test_session_id}/audio-stream")
async def audio_stream_websocket(
    websocket: WebSocket,
    test_session_id: int,
    role: str = "mixed",  # "actor", "adversary", or "mixed"
    token: Optional[str] = None,
):
    """WebSocket endpoint for real-time audio streaming from LoopTalk test sessions."""
    # TODO: to be implemented
    pass
