"""Turn validated Jev answers into decisions. All thresholds live in config."""

from app import config
from app.jev.questions import IMPACT_AREAS, ROLLOUT_ELEMENTS
from app.jev.schema import ChoiceAnswer, JevResponse, NoulAnswer
from app.models import Assessment, Decision

IMPACT_RESOLUTIONS = ("affected", "unaffected")
ROLLOUT_RESOLUTIONS = ("present", "not_applicable")


def impact_status(answer: ChoiceAnswer) -> str:
    if answer.choice != "unclear" and answer.confidence >= config.IMPACT_MIN_CONFIDENCE:
        return answer.choice
    return "needs_review"


def rollout_status(answer: NoulAnswer) -> str:
    if answer.noul >= config.ROLLOUT_PRESENT_AT:
        return "present"
    if answer.noul <= config.ROLLOUT_MISSING_AT:
        return "missing"
    return "needs_review"


def interpret(response: JevResponse, source: str, brief_version: int, now: str) -> Assessment:
    decisions = {
        key: Decision(key=key, kind="impact", model_status=impact_status(response.answers[key]),
                      model_answer=response.answers[key].model_dump())
        for key in IMPACT_AREAS
    } | {
        key: Decision(key=key, kind="rollout", model_status=rollout_status(response.answers[key]),
                      model_answer=response.answers[key].model_dump())
        for key in ROLLOUT_ELEMENTS
    }
    return Assessment(source=source, model=response.model, brief_version=brief_version,
                      created_at=now, decisions=decisions)


def allowed_resolutions(decision: Decision) -> tuple[str, ...]:
    return IMPACT_RESOLUTIONS if decision.kind == "impact" else ROLLOUT_RESOLUTIONS


def rollout_coverage(assessment: Assessment) -> tuple[int, int]:
    """(elements covered or marked not applicable, total elements)."""
    covered = sum(assessment.decisions[k].status in ROLLOUT_RESOLUTIONS for k in ROLLOUT_ELEMENTS)
    return covered, len(ROLLOUT_ELEMENTS)
