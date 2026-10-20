"""Illustrative examples. These answers are hand-written fixtures in Jev's
documented response shape, NOT results from Jev. They pass through the same
validator and interpreter as live responses and are always labeled."""

from app.assessment import interpret
from app.jev.questions import build_questions
from app.jev.schema import validate_response
from app.models import Brief, Release
from app.releases import new_release, now

FIXTURE_MODEL = "illustrative-fixture"


def _choice(probs: dict[str, float]) -> dict:
    # Same confidence formula the docs describe for Choice: top probability's
    # distance above an even split, rescaled to 0..1.
    n = len(probs)
    top = max(probs, key=probs.get)
    return {"type": "choice", "choice": top, "probabilities": probs,
            "confidence": round((probs[top] - 1 / n) / (1 - 1 / n), 3)}


def _noul(p: float) -> dict:
    return {"type": "noul", "noul": p}


EXAMPLES = {
    "email-verification": (
        Brief(
            title="Email verification for new accounts",
            change_description="New accounts must confirm their email address via a link before they can sign in. "
                               "Unverified accounts can resend the link and are deleted after 14 days.",
            audience="All new sign-ups on web and mobile.",
            rollout_plan="Behind the verify_email flag: 10% of new sign-ups on Nov 3, 100% by Nov 10 if the "
                         "verification completion rate stays above 85% on the signup dashboard. Turn the flag off "
                         "to roll back.",
        ),
        {
            "account_access": _choice({"affected": 0.94, "unaffected": 0.03, "unclear": 0.03}),
            "legal_copy": _choice({"affected": 0.18, "unaffected": 0.74, "unclear": 0.08}),
            "support_guidance": _choice({"affected": 0.88, "unaffected": 0.05, "unclear": 0.07}),
            "feature_guide": _choice({"affected": 0.81, "unaffected": 0.12, "unclear": 0.07}),
            "rollout_states_phasing": _noul(0.96),
            "rollout_states_schedule": _noul(0.93),
            "rollout_has_rollback": _noul(0.91),
            "rollout_has_monitoring": _noul(0.84),
            "rollout_has_communication": _noul(0.12),
        },
    ),
    "display-name": (
        Brief(
            title="Let users edit their display name",
            change_description="Users can change their display name from profile settings. Display names are "
                               "shown publicly on comments.",
            audience="All signed-in users.",
            rollout_plan="Ship to everyone in the Nov 12 release. Watch support ticket volume.",
        ),
        {
            "account_access": _choice({"affected": 0.08, "unaffected": 0.86, "unclear": 0.06}),
            "legal_copy": _choice({"affected": 0.38, "unaffected": 0.22, "unclear": 0.40}),
            "support_guidance": _choice({"affected": 0.72, "unaffected": 0.18, "unclear": 0.10}),
            "feature_guide": _choice({"affected": 0.83, "unaffected": 0.10, "unclear": 0.07}),
            "rollout_states_phasing": _noul(0.81),
            "rollout_states_schedule": _noul(0.92),
            "rollout_has_rollback": _noul(0.06),
            "rollout_has_monitoring": _noul(0.55),
            "rollout_has_communication": _noul(0.09),
        },
    ),
}


def load_example(name: str) -> Release:
    brief, answers = EXAMPLES[name]
    release = new_release(brief.model_copy(), is_example=True)
    response = validate_response({"model": FIXTURE_MODEL, "answers": answers}, build_questions())
    release.assessment = interpret(response, "illustrative", release.brief_version, now())
    return release
