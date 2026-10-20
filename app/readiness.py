"""Readiness rules. Checklist completion is reported separately from readiness:
a fully signed checklist is still blocked by open decisions or rollout gaps."""

from app.assessment import rollout_coverage
from app.checklist import checklist
from app.jev.questions import IMPACT_AREAS, ROLLOUT_ELEMENTS, label
from app.models import Release


def readiness(release: Release) -> dict:
    a = release.assessment
    if a is None:
        return {
            "status": "not_assessed",
            "checklist": {"signed": 0, "total": 0},
            "rollout": {"covered": 0, "total": len(ROLLOUT_ELEMENTS)},
            "gaps": [_gap("assessment", "No assessment for the current brief. Run an assessment.")],
        }

    gaps = []
    if a.source == "illustrative":
        gaps.append(_gap("assessment", "Assessment is an illustrative example, not a live Jev result."))
    for key in IMPACT_AREAS:
        if a.decisions[key].status == "needs_review":
            gaps.append(_gap("decision", f"{label(key)}: impact is unclear and needs a human decision."))
    for key in ROLLOUT_ELEMENTS:
        status = a.decisions[key].status
        if status == "missing":
            gaps.append(_gap("rollout", f"Rollout plan does not cover {label(key).lower()}."))
        elif status == "needs_review":
            gaps.append(_gap("rollout", f"Unclear whether the rollout plan covers {label(key).lower()}."))

    entries = checklist(release)
    for e in entries:
        missing = [name for name, absent in (
            ("owner", not e.state.owner),
            ("document", e.template.requires_doc and not e.state.doc_url),
            ("sign-off", e.state.signoff is None),
        ) if absent]
        if missing:
            gaps.append(_gap("item", f"{e.template.title}: needs {', '.join(missing)}.") | {"missing": missing})

    covered, total = rollout_coverage(a)
    return {
        "status": "blocked" if gaps else "ready",
        "checklist": {"signed": sum(e.state.signoff is not None for e in entries), "total": len(entries)},
        "rollout": {"covered": covered, "total": total},
        "gaps": gaps,
    }


def _gap(kind: str, message: str) -> dict:
    return {"kind": kind, "message": message}
