from app.assessment import interpret
from app.examples import _choice, _noul
from app.jev.questions import IMPACT_AREAS, ROLLOUT_ELEMENTS, build_questions
from app.jev.schema import validate_response
from app.models import Brief
from app.releases import new_release, now

AFFECTED = {"affected": 0.9, "unaffected": 0.05, "unclear": 0.05}
UNAFFECTED = {"affected": 0.05, "unaffected": 0.9, "unclear": 0.05}
UNCLEAR = {"affected": 0.2, "unaffected": 0.2, "unclear": 0.6}


def raw_response(impact=None, rollout=None, model="jev-1.13.0") -> dict:
    """A well-formed response; override per-key impact probabilities or rollout nouls."""
    impact, rollout = impact or {}, rollout or {}
    answers = {k: _choice(impact.get(k, UNAFFECTED)) for k in IMPACT_AREAS}
    answers |= {k: _noul(rollout.get(k, 0.95)) for k in ROLLOUT_ELEMENTS}
    return {"model": model, "answers": answers, "usage": {"input_tokens": 900, "output_tokens": 60}}


def assessed_release(**kwargs):
    release = new_release(Brief(title="Test", change_description="x", audience="y", rollout_plan="z"))
    response = validate_response(raw_response(**kwargs), build_questions())
    release.assessment = interpret(response, "live", release.brief_version, now())
    return release
