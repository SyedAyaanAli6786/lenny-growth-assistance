from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ErrorBody(BaseModel):
    code: str
    message: str
    component: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class SessionCreate(BaseModel):
    title: str | None = None
    user_ref: str | None = None


class SessionSummary(BaseModel):
    id: UUID
    title: str | None
    llm_provider: str
    llm_model: str
    created_at: datetime
    updated_at: datetime


class Citation(BaseModel):
    source_id: str
    chunk_id: str
    title: str
    guest: str | None = None
    url: str | None = None
    score: float


class ArtifactOut(BaseModel):
    id: UUID | None = None
    type: Literal["markdown", "html"]
    title: str | None = None
    content: str


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    provider: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime

    @field_validator("citations", mode="before")
    @classmethod
    def _null_citations_to_empty_list(cls, value: list | None) -> list:
        # citations is a nullable JSONB column (older/user-role rows may
        # never have it set) — treat a NULL row the same as "no citations".
        return value if value is not None else []


class SessionDetail(SessionSummary):
    messages: list[MessageOut]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class ChatTurnResponse(BaseModel):
    message: MessageOut
    artifact: ArtifactOut | None = None


class ProviderUpdate(BaseModel):
    provider: Literal["anthropic", "ollama"]
    model: str | None = None


class SourceSummary(BaseModel):
    slug: str
    title: str
    guest: str | None
    published_at: str | None
    chunk_count: int
    ingested_at: datetime


class ComponentHealth(BaseModel):
    status: Literal["ok", "degraded", "down"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    db: ComponentHealth
    ollama: ComponentHealth
    anthropic: ComponentHealth
