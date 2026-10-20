"""Persisted domain records."""

from typing import Literal

from pydantic import BaseModel, Field

ImpactStatus = Literal["affected", "unaffected", "needs_review"]
RolloutStatus = Literal["present", "missing", "needs_review"]


class Brief(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    change_description: str = Field(default="", max_length=10_000)
    audience: str = Field(default="", max_length=2_000)
    rollout_plan: str = Field(default="", max_length=10_000)


class Resolution(BaseModel):
    value: str
    reason: str
    by: str
    at: str


class Decision(BaseModel):
    key: str
    kind: Literal["impact", "rollout"]
    model_status: str  # what code concluded from Jev's answer
    model_answer: dict  # the validated Jev answer, kept for inspection
    resolution: Resolution | None = None

    @property
    def status(self) -> str:
        return self.resolution.value if self.resolution else self.model_status


class Assessment(BaseModel):
    source: Literal["live", "illustrative"]
    model: str
    brief_version: int
    created_at: str
    decisions: dict[str, Decision]


class SignOff(BaseModel):
    by: str
    note: str = ""
    at: str


class ItemState(BaseModel):
    owner: str = ""
    doc_url: str = ""
    signoff: SignOff | None = None


class Release(BaseModel):
    id: str
    brief: Brief
    brief_version: int = 1
    is_example: bool = False
    assessment: Assessment | None = None
    items: dict[str, ItemState] = {}  # keyed by checklist template key
    created_at: str
    updated_at: str
