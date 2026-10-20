"""Checklist templates and the rule that selects them from decisions."""

from dataclasses import dataclass

from app.models import ItemState, Release


@dataclass(frozen=True)
class Template:
    key: str
    title: str
    description: str
    requires_doc: bool
    area: str | None = None  # impact area that triggers this item; None = always


TEMPLATES = (
    Template("brief_review", "Release brief reviewed",
             "Product confirms the description, audience, and rollout plan are accurate.", False),
    Template("rollout_approval", "Rollout plan approved",
             "The release owner approves phasing, schedule, rollback, monitoring, and communication.", True),
    Template("security_review", "Security review of account access changes",
             "Security reviews changes to sign-up, sign-in, verification, recovery, or permissions.", True,
             "account_access"),
    Template("access_test_plan", "Access and recovery test plan",
             "QA covers sign-in, lockout, and recovery paths affected by the change.", True, "account_access"),
    Template("legal_review", "Legal review of user-facing copy",
             "Legal approves new or changed terms, privacy, consent, or policy text.", True, "legal_copy"),
    Template("support_guidance", "Support guidance updated",
             "Help-center articles and support macros cover the new questions and failure cases.", True,
             "support_guidance"),
    Template("support_briefing", "Support team briefed",
             "Support leads know what is changing, when, and how to escalate.", False, "support_guidance"),
    Template("feature_guide", "Feature guide published",
             "A new or updated guide explains the user-facing behavior.", True, "feature_guide"),
)

TEMPLATES_BY_KEY = {t.key: t for t in TEMPLATES}


@dataclass(frozen=True)
class Entry:
    template: Template
    state: ItemState
    provisional: bool  # included only because its impact decision still needs review


def checklist(release: Release) -> list[Entry]:
    """Applicable items for the current assessment; empty until assessed."""
    if release.assessment is None:
        return []
    entries = []
    for t in TEMPLATES:
        status = release.assessment.decisions[t.area].status if t.area else "affected"
        if status == "unaffected":
            continue
        state = release.items.get(t.key, ItemState())
        entries.append(Entry(t, state, provisional=status == "needs_review"))
    return entries
