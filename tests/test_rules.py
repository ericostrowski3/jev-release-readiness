import pytest

from app.checklist import checklist
from app.examples import EXAMPLES, load_example
from app.jev.questions import build_questions
from app.jev.schema import MalformedResponse, validate_response
from app.models import Brief
from app.readiness import readiness
from app.releases import DomainError, apply_assessment, resolve_decision, sign_off, update_brief, update_item
from tests.helpers import AFFECTED, UNCLEAR, assessed_release, raw_response


def keys(release):
    return [e.template.key for e in checklist(release)]


def complete_all_items(release):
    for e in checklist(release):
        update_item(release, e.template.key, "Sam", "https://docs.example/x")
        sign_off(release, e.template.key, "Sam")


# Decision -> checklist mapping

def test_unaffected_everywhere_gives_only_baseline_items():
    assert keys(assessed_release()) == ["brief_review", "rollout_approval"]


def test_affected_areas_add_their_items():
    release = assessed_release(impact={"account_access": AFFECTED, "support_guidance": AFFECTED})
    assert keys(release) == ["brief_review", "rollout_approval", "security_review", "access_test_plan",
                             "support_guidance", "support_briefing"]
    assert not any(e.provisional for e in checklist(release))


def test_no_checklist_before_assessment():
    release = assessed_release()
    release.assessment = None
    assert checklist(release) == []
    assert readiness(release)["status"] == "not_assessed"


# Uncertain results

def test_unclear_choice_needs_review_and_adds_provisional_items():
    release = assessed_release(impact={"legal_copy": UNCLEAR})
    assert release.assessment.decisions["legal_copy"].status == "needs_review"
    legal = [e for e in checklist(release) if e.template.key == "legal_review"]
    assert legal and legal[0].provisional


def test_low_confidence_affected_needs_review():
    # top probability 0.5 of 3 options -> confidence 0.25, below the 0.6 threshold
    release = assessed_release(impact={"feature_guide": {"affected": 0.5, "unaffected": 0.3, "unclear": 0.2}})
    assert release.assessment.decisions["feature_guide"].status == "needs_review"


@pytest.mark.parametrize("p, status", [(0.9, "present"), (0.75, "present"), (0.5, "needs_review"),
                                       (0.25, "missing"), (0.05, "missing")])
def test_rollout_thresholds(p, status):
    release = assessed_release(rollout={"rollout_has_rollback": p})
    assert release.assessment.decisions["rollout_has_rollback"].status == status


def test_resolving_unclear_as_unaffected_removes_provisional_items_and_keeps_model_answer():
    release = assessed_release(impact={"legal_copy": UNCLEAR})
    resolve_decision(release, "legal_copy", "unaffected", "No legal text changes.", "Ana")
    decision = release.assessment.decisions["legal_copy"]
    assert decision.status == "unaffected" and decision.model_status == "needs_review"
    assert decision.model_answer["choice"] == "unclear"
    assert "legal_review" not in keys(release)


def test_resolution_requires_reason_and_valid_value():
    release = assessed_release(impact={"legal_copy": UNCLEAR})
    with pytest.raises(DomainError):
        resolve_decision(release, "legal_copy", "unaffected", " ", "Ana")
    with pytest.raises(DomainError):
        resolve_decision(release, "legal_copy", "unclear", "why", "Ana")
    with pytest.raises(DomainError):
        resolve_decision(release, "rollout_has_rollback", "missing", "why", "Ana")


# Readiness rules

def test_ready_only_when_every_gap_is_closed():
    release = assessed_release()
    assert readiness(release)["status"] == "blocked"
    complete_all_items(release)
    assert readiness(release) == {"status": "ready", "checklist": {"signed": 2, "total": 2},
                                  "rollout": {"covered": 5, "total": 5}, "gaps": []}


def test_complete_checklist_does_not_hide_unresolved_decision():
    release = assessed_release(impact={"legal_copy": UNCLEAR})
    complete_all_items(release)
    r = readiness(release)
    assert r["checklist"]["signed"] == r["checklist"]["total"]
    assert r["status"] == "blocked"
    assert [g["kind"] for g in r["gaps"]] == ["decision"]


def test_complete_checklist_does_not_hide_incomplete_rollout():
    release = assessed_release(rollout={"rollout_has_rollback": 0.1, "rollout_has_monitoring": 0.5})
    complete_all_items(release)
    r = readiness(release)
    assert r["status"] == "blocked"
    assert r["rollout"] == {"covered": 3, "total": 5}
    assert [g["kind"] for g in r["gaps"]] == ["rollout", "rollout"]


def test_rollout_marked_not_applicable_counts_as_covered():
    release = assessed_release(rollout={"rollout_has_communication": 0.1})
    resolve_decision(release, "rollout_has_communication", "not_applicable", "Internal-only change.", "Ana")
    complete_all_items(release)
    assert readiness(release)["status"] == "ready"


def test_missing_owner_document_and_sign_off_are_one_gap_per_item():
    release = assessed_release()
    assert readiness(release)["gaps"] == [
        {"kind": "item", "message": "Release brief reviewed: needs owner, sign-off.", "missing": ["owner", "sign-off"]},
        {"kind": "item", "message": "Rollout plan approved: needs owner, document, sign-off.",
         "missing": ["owner", "document", "sign-off"]},
    ]
    update_item(release, "brief_review", "Sam", "")
    assert readiness(release)["gaps"][0]["missing"] == ["sign-off"]


def test_illustrative_assessment_is_never_ready():
    release = load_example("email-verification")
    for key in release.assessment.decisions:
        if release.assessment.decisions[key].status in ("needs_review", "missing"):
            resolve_decision(release, key, "present" if key.startswith("rollout") else "affected", "ok", "Ana")
    complete_all_items(release)
    r = readiness(release)
    assert r["status"] == "blocked"
    assert r["gaps"] == [{"kind": "assessment", "message": "Assessment is an illustrative example, not a live Jev result."}]


# Sign-off rules and stale approvals

def test_sign_off_requires_owner_and_required_document():
    release = assessed_release()
    with pytest.raises(DomainError, match="owner"):
        sign_off(release, "rollout_approval", "Sam")
    update_item(release, "rollout_approval", "Sam", "")
    with pytest.raises(DomainError, match="document"):
        sign_off(release, "rollout_approval", "Sam")
    update_item(release, "brief_review", "Sam", "")
    sign_off(release, "brief_review", "Sam")  # no document required


def test_changing_item_details_clears_only_that_sign_off():
    release = assessed_release()
    complete_all_items(release)
    update_item(release, "rollout_approval", "Sam", "https://docs.example/v2")
    assert release.items["rollout_approval"].signoff is None
    assert release.items["brief_review"].signoff is not None
    update_item(release, "brief_review", "Sam", "https://docs.example/x")  # unchanged -> keeps sign-off
    assert release.items["brief_review"].signoff is not None


def test_rejects_non_http_document_links():
    with pytest.raises(DomainError):
        update_item(assessed_release(), "brief_review", "Sam", "javascript:alert(1)")


def test_brief_edit_invalidates_assessment_and_all_sign_offs_but_keeps_owners():
    release = assessed_release()
    complete_all_items(release)
    update_brief(release, release.brief.model_copy(update={"rollout_plan": "changed"}))
    assert release.assessment is None and release.brief_version == 2
    assert all(i.signoff is None for i in release.items.values())
    assert release.items["brief_review"].owner == "Sam"


def test_saving_identical_brief_changes_nothing():
    release = assessed_release()
    update_brief(release, release.brief.model_copy())
    assert release.assessment is not None and release.brief_version == 1


def test_assessment_for_old_brief_version_is_rejected():
    release = assessed_release()
    old = release.assessment
    update_brief(release, Brief(title="New title"))
    with pytest.raises(DomainError) as e:
        apply_assessment(release, old)
    assert e.value.status == 409 and release.assessment is None


# Response validation

@pytest.mark.parametrize("mutate", [
    lambda r: r["answers"].pop("legal_copy"),
    lambda r: r["answers"]["legal_copy"].update(choice="maybe"),
    lambda r: r["answers"]["legal_copy"]["probabilities"].update(maybe=0.0),
    lambda r: r["answers"]["legal_copy"].update(confidence=1.5),
    lambda r: r["answers"]["rollout_has_rollback"].update(type="choice"),
    lambda r: r["answers"]["rollout_has_rollback"].update(noul="high"),
    lambda r: r["answers"]["account_access"]["probabilities"].update(affected=0.5),
    lambda r: r.pop("model"),
])
def test_validator_rejects_malformed_answers(mutate):
    raw = raw_response()
    mutate(raw)
    with pytest.raises(MalformedResponse):
        validate_response(raw, build_questions())


def test_examples_are_valid_and_labeled():
    for name in EXAMPLES:
        release = load_example(name)
        assert release.is_example and release.assessment.source == "illustrative"


def test_display_name_example_exercises_review_paths():
    d = load_example("display-name").assessment.decisions
    assert d["legal_copy"].status == "needs_review"
    assert d["support_guidance"].status == "needs_review"  # affected, but low confidence
    assert d["rollout_has_rollback"].status == "missing"
