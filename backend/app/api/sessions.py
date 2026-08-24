from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.agent.base import ChatMessage
from app.agent.orchestrator import get_provider, respond, run_ship30
from app.api.schemas import (
    ArtifactOut,
    ChatTurnResponse,
    MessageCreate,
    MessageOut,
    ProviderUpdate,
    SessionCreate,
    SessionDetail,
    SessionSummary,
)
from app.config import get_settings
from app.db.models import Artifact as ArtifactModel
from app.db.models import Message
from app.db.models import Session as SessionModel
from app.db.session import get_db
from app.logging import get_logger

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = get_logger(__name__)


def _default_model_for(provider: str) -> str:
    settings = get_settings()
    return settings.anthropic_model if provider == "anthropic" else settings.ollama_model


@router.post("", response_model=SessionSummary)
async def create_session(payload: SessionCreate, db: AsyncSession = Depends(get_db)) -> SessionSummary:
    settings = get_settings()
    session = SessionModel(
        title=payload.title,
        user_ref=payload.user_ref,
        llm_provider=settings.llm_provider,
        llm_model=_default_model_for(settings.llm_provider),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionSummary.model_validate(session, from_attributes=True)


@router.get("", response_model=list[SessionSummary])
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[SessionSummary]:
    stmt = select(SessionModel).order_by(SessionModel.updated_at.desc())
    sessions = (await db.execute(stmt)).scalars().all()
    return [SessionSummary.model_validate(s, from_attributes=True) for s in sessions]


async def _get_session_or_404(db: AsyncSession, session_id: UUID) -> SessionModel:
    session = await db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "session_not_found", "message": f"No session {session_id}", "component": "sessions"}},
        )
    return session


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: UUID, db: AsyncSession = Depends(get_db)) -> SessionDetail:
    session = await _get_session_or_404(db, session_id)
    stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    messages = (await db.execute(stmt)).scalars().all()
    return SessionDetail(
        **SessionSummary.model_validate(session, from_attributes=True).model_dump(),
        messages=[MessageOut.model_validate(m, from_attributes=True) for m in messages],
    )


@router.patch("/{session_id}/provider", response_model=SessionSummary)
async def update_provider(session_id: UUID, payload: ProviderUpdate, db: AsyncSession = Depends(get_db)) -> SessionSummary:
    session = await _get_session_or_404(db, session_id)

    provider = get_provider(payload.provider)
    if not await provider.is_available():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "provider_unavailable",
                    "message": f"{payload.provider} is not currently reachable",
                    "component": payload.provider,
                }
            },
        )

    session.llm_provider = payload.provider
    session.llm_model = payload.model or _default_model_for(payload.provider)
    await db.commit()
    await db.refresh(session)
    return SessionSummary.model_validate(session, from_attributes=True)


async def _persist_turn(
    db: AsyncSession, session: SessionModel, user_text: str, result
) -> tuple[Message, ArtifactModel | None]:
    user_message = Message(session_id=session.id, role="user", content=user_text, citations=[])
    db.add(user_message)

    assistant_message = Message(
        session_id=session.id,
        role="assistant",
        # display_text, not the raw response: when the reply carries a fenced
        # artifact block, the artifact panel already renders that content —
        # showing it a second time, unrendered, in the chat bubble is
        # redundant and (for HTML) looks broken inline.
        content=result.display_text,
        provider=result.response.provider,
        citations=result.citations,
    )
    db.add(assistant_message)
    await db.flush()

    artifact_row = None
    if result.artifact is not None:
        artifact_row = ArtifactModel(
            session_id=session.id,
            message_id=assistant_message.id,
            type=result.artifact.type,
            title=result.artifact.title,
            content=result.artifact.content,
        )
        db.add(artifact_row)

    session.updated_at = func.now()
    await db.commit()
    await db.refresh(assistant_message)
    return assistant_message, artifact_row


@router.post("/{session_id}/messages", response_model=ChatTurnResponse)
async def send_message(session_id: UUID, payload: MessageCreate, db: AsyncSession = Depends(get_db)) -> ChatTurnResponse:
    session = await _get_session_or_404(db, session_id)

    stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    prior_messages = (await db.execute(stmt)).scalars().all()
    history = [ChatMessage(role=m.role, content=m.content) for m in prior_messages if m.role in ("user", "assistant")]
    history.append(ChatMessage(role="user", content=payload.content))

    result = await respond(db, session.llm_provider, history)
    assistant_message, artifact_row = await _persist_turn(db, session, payload.content, result)

    return ChatTurnResponse(
        message=MessageOut.model_validate(assistant_message, from_attributes=True),
        artifact=ArtifactOut.model_validate(artifact_row, from_attributes=True) if artifact_row else None,
    )


@router.post("/{session_id}/ship30", response_model=ChatTurnResponse)
async def ship30(session_id: UUID, payload: MessageCreate, db: AsyncSession = Depends(get_db)) -> ChatTurnResponse:
    session = await _get_session_or_404(db, session_id)

    result = await run_ship30(db, session.llm_provider, ChatMessage(role="user", content=payload.content))
    assistant_message, artifact_row = await _persist_turn(db, session, f"[Ship 30/30] {payload.content}", result)

    return ChatTurnResponse(
        message=MessageOut.model_validate(assistant_message, from_attributes=True),
        artifact=ArtifactOut.model_validate(artifact_row, from_attributes=True) if artifact_row else None,
    )
