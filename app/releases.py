"""Workflow rules for changing a release. Pure functions on Release records."""

import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.assessment import allowed_resolutions
from app.checklist import checklist
from app.models import Assessment, Brief, ItemState, Release, Resolution, SignOff


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_release(brief: Brief, is_example: bool = False) -> Release:
    t = now()
    return Release(id=uuid.uuid4().hex[:12], brief=brief, is_example=is_example, created_at=t, updated_at=t)


def update_brief(release: Release, brief: Brief) -> None:
    """Any brief change invalidates the assessment, its resolutions, and every sign-off."""
    if brief == release.brief:
        return
    release.brief = brief
    release.brief_version += 1
    release.assessment = None
    for item in release.items.values():
        item.signoff = None
    release.updated_at = now()


def apply_assessment(release: Release, assessment: Assessment) -> None:
    if assessment.brief_version != release.brief_version:
        raise DomainError("stale_assessment", "The brief changed while the assessment ran. Run it again.", 409)
    release.assessment = assessment
    release.updated_at = now()


def resolve_decision(release: Release, key: str, value: str, reason: str, by: str) -> None:
    if release.assessment is None:
        raise DomainError("not_assessed", "Run an assessment before resolving decisions.", 409)
    decision = release.assessment.decisions.get(key)
    if decision is None:
        raise DomainError("not_found", f"Unknown decision '{key}'.", 404)
    if value not in allowed_resolutions(decision):
        raise DomainError("invalid_value", f"'{value}' is not a valid resolution for '{key}'.")
    if not reason.strip() or not by.strip():
        raise DomainError("missing_reason", "A resolution needs a reason and the name of who decided.")
    decision.resolution = Resolution(value=value, reason=reason.strip(), by=by.strip(), at=now())
    release.updated_at = now()


def update_item(release: Release, key: str, owner: str, doc_url: str) -> None:
    """Changing an item's owner or document clears that item's sign-off."""
    _require_applicable(release, key)
    owner, doc_url = owner.strip(), doc_url.strip()
    if doc_url and urlparse(doc_url).scheme not in ("http", "https"):
        raise DomainError("invalid_url", "Document link must start with http:// or https://.")
    item = release.items.setdefault(key, ItemState())
    if (item.owner, item.doc_url) != (owner, doc_url):
        item.owner, item.doc_url, item.signoff = owner, doc_url, None
        release.updated_at = now()


def sign_off(release: Release, key: str, by: str, note: str = "") -> None:
    entry = _require_applicable(release, key)
    if not by.strip():
        raise DomainError("missing_signer", "Sign-off needs the name of who is signing.")
    if not entry.state.owner:
        raise DomainError("missing_owner", "Assign an owner before signing off.", 409)
    if entry.template.requires_doc and not entry.state.doc_url:
        raise DomainError("missing_document", "Add the supporting document before signing off.", 409)
    item = release.items.setdefault(key, ItemState())
    item.signoff = SignOff(by=by.strip(), note=note.strip(), at=now())
    release.updated_at = now()


def revoke_sign_off(release: Release, key: str) -> None:
    _require_applicable(release, key)
    if key in release.items:
        release.items[key].signoff = None
        release.updated_at = now()


def _require_applicable(release: Release, key: str):
    for entry in checklist(release):
        if entry.template.key == key:
            return entry
    raise DomainError("not_found", f"'{key}' is not on this release's checklist.", 404)
