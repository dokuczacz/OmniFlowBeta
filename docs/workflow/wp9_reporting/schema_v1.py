from __future__ import annotations

import datetime as _dt
import uuid as _uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, root_validator, validator


SCHEMA_VERSION_V1 = "omniflow.wp9.report.v1"


def utc_now_iso() -> str:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat().replace("+00:00", "Z")


class PlanRefV1(BaseModel):
    wp: str = Field(..., description="Work package identifier, e.g. WP1, WP9.")
    item: str = Field(..., description="Plan item identifier, stable short name.")
    note: Optional[str] = Field(None, description="Optional short note about the plan mapping.")

    @validator("wp", "item")
    def _non_empty(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("must be non-empty")
        return v


class ChangeV1(BaseModel):
    kind: Literal["code", "config", "doc", "data", "ops"] = Field(..., description="What type of change was made.")
    path: str = Field(..., description="Repo-relative path or external system reference.")
    summary: str = Field(..., description="Short 1-line summary of the change.")

    @validator("path", "summary")
    def _non_empty(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("must be non-empty")
        return v


class ExecutionV1(BaseModel):
    runtime_used: Optional[Literal["assistants", "responses", "auto"]] = None
    thread_id: Optional[str] = None
    tool_calls_count: Optional[int] = Field(None, ge=0)
    timings_ms: Optional[Dict[str, int]] = Field(None, description="Milliseconds breakdown, e.g. total_ms/tools_ms.")
    commit: Optional[str] = Field(None, description="Git commit hash if applicable.")
    status: Literal["success", "error"] = "success"
    error: Optional[str] = None

    @root_validator
    def _error_required_when_failed(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values.get("status") == "error" and not values.get("error"):
            raise ValueError("execution.error required when execution.status=error")
        return values


class BestPracticeItemV1(BaseModel):
    title: str
    rationale: str
    evidence: Optional[str] = None
    action: str

    @validator("title", "rationale", "action")
    def _non_empty(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("must be non-empty")
        return v


class BestPracticeV1(BaseModel):
    source_entry_id: str = Field(..., description="The execution entry_id this best practice refers to.")
    items: List[BestPracticeItemV1] = Field(default_factory=list)

    @validator("source_entry_id")
    def _source_non_empty(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("must be non-empty")
        return v


class ReportEntryInputV1(BaseModel):
    """Strict input shape that an agent is allowed to provide.

    The script will add timestamp/entry_id/schema_version deterministically.
    """

    entry_type: Literal["plan", "execution", "best_practice"]
    plan_ref: PlanRefV1
    subject: str = Field(..., description="What this entry is about (human/agent readable).")
    changes: List[ChangeV1] = Field(default_factory=list)
    execution: Optional[ExecutionV1] = None
    best_practice: Optional[BestPracticeV1] = None
    tags: List[str] = Field(default_factory=list)

    @validator("subject")
    def _subject_non_empty(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("must be non-empty")
        return v

    @validator("tags", each_item=True)
    def _tag_clean(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("empty tag")
        if len(v) > 64:
            raise ValueError("tag too long")
        return v

    @root_validator
    def _type_specific_blocks(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        entry_type = values.get("entry_type")
        if entry_type == "execution" and values.get("execution") is None:
            raise ValueError("execution block required for entry_type=execution")
        if entry_type == "best_practice" and values.get("best_practice") is None:
            raise ValueError("best_practice block required for entry_type=best_practice")
        return values


class ReportEntryV1(BaseModel):
    schema_version: Literal[SCHEMA_VERSION_V1]
    entry_id: str
    timestamp_utc: str
    entry_type: Literal["plan", "execution", "best_practice"]
    plan_ref: PlanRefV1
    subject: str
    changes: List[ChangeV1] = Field(default_factory=list)
    execution: Optional[ExecutionV1] = None
    best_practice: Optional[BestPracticeV1] = None
    tags: List[str] = Field(default_factory=list)

    @classmethod
    def from_input(cls, payload: ReportEntryInputV1) -> "ReportEntryV1":
        return cls(
            schema_version=SCHEMA_VERSION_V1,
            entry_id=f"rep_{_uuid.uuid4().hex}",
            timestamp_utc=utc_now_iso(),
            entry_type=payload.entry_type,
            plan_ref=payload.plan_ref,
            subject=payload.subject,
            changes=payload.changes,
            execution=payload.execution,
            best_practice=payload.best_practice,
            tags=payload.tags,
        )

