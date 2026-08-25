import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.agent.base import ChatMessage, ProviderTimeoutError, ProviderUnavailableError
from app.agent.orchestrator import (
    StreamDelta,
    StreamDone,
    StreamRestart,
    get_provider,
    respond,
    respond_stream,
    run_ship30_stream,
)
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
from app.db.session import async_session_factory, get_db
from app.logging import get_logger
from app.rag.embeddings import EmbeddingError

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = get_logger(__name__)

# In-memory only, one entry per session with a stream currently in flight —
# fine at this app's single-process scale (same assumption as the rest of
# the app's state), not durable across a restart. Lets POST .../stop signal
# an in-progress generator without needing to cancel the request/task (see
# respond_stream's docstring for why cooperative checking is used instead).
_active_streams: dict[UUID, asyncio.Event] = {}


def _default_model_for(provider: str) -> str:
    settings = get_settings()
    return settings.anthropic_model if provider == "anthropic" else settings.ollama_model


def _derive_title(content: str) -> str:
    """Auto-name a session from its first user message, ChatGPT-style, so the
    sidebar doesn't show "Untitled session" forever. Collapses newlines since
    a pasted multi-line question shouldn't wrap the sidebar row.
    """
    collapsed = " ".join(content.split())
    if not collapsed:
        return "New chat"
    if len(collapsed) <= 60:
        return collapsed
    truncated = collapsed[:60].rsplit(" ", 1)[0] or collapsed[:60]
    return f"{truncated}…"


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


async def _messages_with_artifacts(db: AsyncSession, messages: list[Message]) -> list[MessageOut]:
    """Attach each message's artifact (if it produced one), so a past turn's
    artifact can be reopened after closing it, switching sessions, or
    reloading — not just visible once from the immediate turn response.
    """
    message_ids = [m.id for m in messages]
    artifact_rows = (
        (await db.execute(select(ArtifactModel).where(ArtifactModel.message_id.in_(message_ids)))).scalars().all()
        if message_ids
        else []
    )
    artifacts_by_message = {a.message_id: a for a in artifact_rows}

    out = []
    for m in messages:
        message_out = MessageOut.model_validate(m, from_attributes=True)
        artifact_row = artifacts_by_message.get(m.id)
        if artifact_row:
            message_out = message_out.model_copy(
                update={"artifact": ArtifactOut.model_validate(artifact_row, from_attributes=True)}
            )
        out.append(message_out)
    return out


def _build_turn_response(assistant_message: Message, artifact_row: ArtifactModel | None) -> ChatTurnResponse:
    artifact_out = ArtifactOut.model_validate(artifact_row, from_attributes=True) if artifact_row else None
    message_out = MessageOut.model_validate(assistant_message, from_attributes=True)
    if artifact_out:
        message_out = message_out.model_copy(update={"artifact": artifact_out})
    return ChatTurnResponse(message=message_out, artifact=artifact_out)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: UUID, db: AsyncSession = Depends(get_db)) -> SessionDetail:
    session = await _get_session_or_404(db, session_id)
    stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    messages = (await db.execute(stmt)).scalars().all()
    return SessionDetail(
        **SessionSummary.model_validate(session, from_attributes=True).model_dump(),
        messages=await _messages_with_artifacts(db, messages),
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    session = await _get_session_or_404(db, session_id)
    # ORM-level cascade="all, delete-orphan" on Session.messages/artifacts (and
    # the FKs' ondelete="CASCADE" as a DB-level backstop) take care of the
    # session's messages and artifacts — nothing else to clean up here.
    await db.delete(session)
    await db.commit()


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


async def _persist_user_message(db: AsyncSession, session: SessionModel, user_text: str) -> Message:
    user_message = Message(session_id=session.id, role="user", content=user_text, citations=[])
    db.add(user_message)
    await db.commit()
    return user_message


async def _persist_assistant_message(
    db: AsyncSession, session: SessionModel, result
) -> tuple[Message, ArtifactModel | None]:
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
    if session.title is None:
        session.title = _derive_title(payload.content)

    stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    prior_messages = (await db.execute(stmt)).scalars().all()
    history = [ChatMessage(role=m.role, content=m.content) for m in prior_messages if m.role in ("user", "assistant")]
    history.append(ChatMessage(role="user", content=payload.content))

    await _persist_user_message(db, session, payload.content)
    result = await respond(db, session.llm_provider, history)
    assistant_message, artifact_row = await _persist_assistant_message(db, session, result)

    return _build_turn_response(assistant_message, artifact_row)


@router.post("/{session_id}/messages/stream")
async def send_message_stream(session_id: UUID, payload: MessageCreate, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Newline-delimited-JSON version of POST /messages: one {"type": "delta", ...}
    line per chunk of text as the model produces it, then a single terminal
    {"type": "done", ...} line carrying the same payload the non-streaming
    endpoint returns (persisted message + citations + artifact).

    NDJSON over a plain POST body rather than a native EventSource: this
    request needs a JSON body (the message content), and EventSource only
    supports GET. A fetch() reader on the frontend parses this the same way
    either framing would require.

    HTTP 200 and the streaming body start before the model call even begins
    (StreamingResponse commits the response headers on the first yield), so a
    failure that happens mid-generation can't change the HTTP status anymore
    — main.py's exception handlers never run for this endpoint. Every error
    case that respond_stream() can raise is instead caught here and reported
    as a {"type": "error", ...} line so the frontend always gets an explicit
    signal instead of a silently dropped connection.

    The user's message (and the title derived from it) is persisted before
    generation starts, not alongside the assistant reply at the end: Ollama
    generation legitimately runs 30-120+s on CPU-only hardware, and Starlette
    cancels this generator outright on client disconnect (tab closed, laptop
    slept, network dropped) — a real risk over a window that long. Without
    this, a disconnect mid-stream would silently lose the user's own message
    and leave the session untitled, with no trace it was ever sent.
    """
    # Registered synchronously, before any awaits below, so there's no window
    # where a client's POST .../stop could arrive before this session_id is
    # in the registry and silently no-op — a real (if narrow) race when this
    # was created later, inside event_stream(), after its own await on a DB
    # lookup. A client physically can't call the stop endpoint before this
    # request has even started sending its response, so registering first
    # thing here closes the gap entirely rather than just narrowing it.
    stop_event = asyncio.Event()
    _active_streams[session_id] = stop_event

    try:
        session = await _get_session_or_404(db, session_id)
        provider_name = session.llm_provider

        stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
        prior_messages = (await db.execute(stmt)).scalars().all()
    except Exception:
        # Never reached event_stream()'s own cleanup below — this request is
        # failing before any StreamingResponse gets returned at all.
        _active_streams.pop(session_id, None)
        raise
    history = [ChatMessage(role=m.role, content=m.content) for m in prior_messages if m.role in ("user", "assistant")]
    history.append(ChatMessage(role="user", content=payload.content))

    async def event_stream():
        # A dedicated DB session for the streamed portion, independent of the
        # one injected via Depends(get_db) above: whether a yield-dependency
        # stays open for the full lifetime of a StreamingResponse body isn't
        # something to lean on, so this generator manages its own session
        # rather than reusing one whose teardown timing relative to the
        # response is ambiguous.
        #
        # The outer try/finally guarantees _active_streams gets cleaned up
        # exactly once no matter which path this takes — the early
        # session-not-found return, a normal completion, or one of the
        # specific error branches below.
        try:
            async with async_session_factory() as stream_db:
                stream_session = await stream_db.get(SessionModel, session_id)
                if stream_session is None:
                    yield json.dumps({"type": "error", "code": "session_not_found", "message": f"No session {session_id}"}) + "\n"
                    return
                if stream_session.title is None:
                    stream_session.title = _derive_title(payload.content)

                try:
                    await _persist_user_message(stream_db, stream_session, payload.content)

                    async for event in respond_stream(stream_db, provider_name, history, stop_event=stop_event):
                        if isinstance(event, StreamDelta):
                            yield json.dumps({"type": "delta", "text": event.text}) + "\n"
                        elif isinstance(event, StreamDone):
                            assistant_message, artifact_row = await _persist_assistant_message(
                                stream_db, stream_session, event.result
                            )
                            turn = _build_turn_response(assistant_message, artifact_row)
                            yield json.dumps({"type": "done", "turn": turn.model_dump(mode="json")}) + "\n"
                except ProviderUnavailableError as exc:
                    logger.error("stream_provider_unavailable", error=str(exc))
                    yield json.dumps({"type": "error", "code": "provider_unavailable", "message": str(exc)}) + "\n"
                except ProviderTimeoutError as exc:
                    logger.error("stream_provider_timeout", error=str(exc))
                    yield json.dumps({"type": "error", "code": "provider_timeout", "message": str(exc)}) + "\n"
                except EmbeddingError as exc:
                    logger.error("stream_embedding_error", error=str(exc))
                    yield json.dumps({"type": "error", "code": "embedding_unavailable", "message": str(exc)}) + "\n"
                except Exception as exc:
                    logger.error("stream_unhandled_exception", error=str(exc), exc_info=True)
                    yield json.dumps({"type": "error", "code": "internal_error", "message": "An unexpected error occurred"}) + "\n"
        finally:
            _active_streams.pop(session_id, None)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/{session_id}/messages/stop", status_code=204)
async def stop_message_stream(session_id: UUID) -> None:
    """Signals an in-progress .../messages/stream generation for this session
    to wrap up early — see respond_stream's stop_event docstring for why this
    is cooperative rather than cancelling the request. A stopped reply is
    persisted exactly like a completed one, just shorter, so it survives a
    reload the same way. No-op (not an error) if nothing is currently
    generating for this session — most likely it already finished right as
    the user clicked stop.
    """
    stop_event = _active_streams.get(session_id)
    if stop_event is not None:
        stop_event.set()


@router.post("/{session_id}/ship30/stream")
async def ship30_stream(session_id: UUID, payload: MessageCreate, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Streaming counterpart to what used to be a plain POST /ship30: same
    NDJSON framing as /messages/stream, plus one extra event type —
    {"type": "restart"} — emitted if the draft fails validation and a repair
    pass is starting, telling the frontend to clear the in-progress bubble
    rather than appending the repair's text after the discarded draft's.

    Replaces the non-streaming version outright rather than keeping both:
    a full Ship 30 essay plus a possible repair pass measured 200-400+s on
    CPU-only hardware, and confirmed live, something in the stack (proxy,
    browser, or OS idle-timeout) will drop a connection sitting that idle —
    the reply still persisted correctly since non-streaming requests aren't
    cancelled on disconnect, but the user's tab had no way to know that. See
    run_ship30_stream()'s docstring for the full account.
    """
    # Registered synchronously, before any awaits below — see the matching
    # comment in send_message_stream for why (closes a real, if narrow, race
    # where a stop request could arrive before this session_id is in the
    # registry and silently no-op).
    stop_event = asyncio.Event()
    _active_streams[session_id] = stop_event

    try:
        session = await _get_session_or_404(db, session_id)
        provider_name = session.llm_provider
    except Exception:
        _active_streams.pop(session_id, None)
        raise

    async def event_stream():
        try:
            async with async_session_factory() as stream_db:
                stream_session = await stream_db.get(SessionModel, session_id)
                if stream_session is None:
                    yield json.dumps({"type": "error", "code": "session_not_found", "message": f"No session {session_id}"}) + "\n"
                    return
                if stream_session.title is None:
                    stream_session.title = _derive_title(payload.content)

                try:
                    await _persist_user_message(stream_db, stream_session, f"[Ship 30/30] {payload.content}")

                    topic_message = ChatMessage(role="user", content=payload.content)
                    async for event in run_ship30_stream(stream_db, provider_name, topic_message, stop_event=stop_event):
                        if isinstance(event, StreamDelta):
                            yield json.dumps({"type": "delta", "text": event.text}) + "\n"
                        elif isinstance(event, StreamRestart):
                            yield json.dumps({"type": "restart"}) + "\n"
                        elif isinstance(event, StreamDone):
                            assistant_message, artifact_row = await _persist_assistant_message(
                                stream_db, stream_session, event.result
                            )
                            turn = _build_turn_response(assistant_message, artifact_row)
                            yield json.dumps({"type": "done", "turn": turn.model_dump(mode="json")}) + "\n"
                except ProviderUnavailableError as exc:
                    logger.error("ship30_stream_provider_unavailable", error=str(exc))
                    yield json.dumps({"type": "error", "code": "provider_unavailable", "message": str(exc)}) + "\n"
                except ProviderTimeoutError as exc:
                    logger.error("ship30_stream_provider_timeout", error=str(exc))
                    yield json.dumps({"type": "error", "code": "provider_timeout", "message": str(exc)}) + "\n"
                except EmbeddingError as exc:
                    logger.error("ship30_stream_embedding_error", error=str(exc))
                    yield json.dumps({"type": "error", "code": "embedding_unavailable", "message": str(exc)}) + "\n"
                except Exception as exc:
                    logger.error("ship30_stream_unhandled_exception", error=str(exc), exc_info=True)
                    yield json.dumps({"type": "error", "code": "internal_error", "message": "An unexpected error occurred"}) + "\n"
        finally:
            _active_streams.pop(session_id, None)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
