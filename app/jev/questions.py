"""The narrow questions Jev answers about a release brief.

User-written brief text goes only into `state`. Instructions and criteria are
fixed application text, so a brief cannot rewrite the questions.
"""

from app.models import Brief

IMPACT_OPTIONS = ("affected", "unaffected", "unclear")

# key -> (plain-language label, question, what counts as affected, what does not, examples of affected)
IMPACT_AREAS = {
    "account_access": (
        "Account access",
        "Does the change in `release.change_description` alter how users get into or keep access to their accounts?",
        "Sign-up, sign-in, email or phone verification, password reset, account recovery, sessions, lockouts, or permissions",
        "Changes to profile content, settings, or features used after a user is already signed in",
        ["Require users to verify their email before signing in", "Add two-factor authentication"],
    ),
    "legal_copy": (
        "Legal copy",
        "Does the change in `release.change_description` require new or changed legal text shown to users?",
        "Terms of service, privacy notices, consent wording, data-use disclosures, or content policies",
        "Ordinary UI labels, help text, or marketing copy with no legal meaning",
        ["Start collecting phone numbers for marketing", "Let users publish content visible to others"],
    ),
    "support_guidance": (
        "Support guidance",
        "Will support agents need new or updated guidance to answer user questions about the change in `release.change_description`?",
        "New user questions, new failure cases, changed troubleshooting steps, or new requests support must handle",
        "Internal or invisible changes that users will not notice or ask about",
        ["Users may not receive a verification email", "A changed limit users may hit"],
    ),
    "feature_guide": (
        "Feature guide",
        "Does the change in `release.change_description` add or change user-facing behavior that a feature guide should explain?",
        "A new feature, a new setting, or a changed workflow users must learn",
        "Bug fixes, performance work, or changes with no visible behavior change",
        ["Users can now edit their display name", "A new step in onboarding"],
    ),
}

# key -> (plain-language label, yes/no question about the rollout plan)
ROLLOUT_ELEMENTS = {
    "rollout_states_phasing": (
        "Phasing",
        "Does `release.rollout_plan` state how the change will be released, such as all at once, by percentage, by cohort, or behind a feature flag?",
    ),
    "rollout_states_schedule": (
        "Schedule",
        "Does `release.rollout_plan` state a target date, date range, or release window?",
    ),
    "rollout_has_rollback": (
        "Rollback",
        "Does `release.rollout_plan` describe how to disable or revert the change if something goes wrong?",
    ),
    "rollout_has_monitoring": (
        "Monitoring",
        "Does `release.rollout_plan` name metrics, dashboards, or alerts that will be watched during the release?",
    ),
    "rollout_has_communication": (
        "Communication",
        "Does `release.rollout_plan` say who will be told about the release, such as users, support, or other teams?",
    ),
}


def build_state(brief: Brief) -> dict:
    return {
        "release": {
            "title": brief.title,
            "change_description": brief.change_description,
            "audience": brief.audience,
            "rollout_plan": brief.rollout_plan,
        }
    }


def _impact_question(question: str, affected: str, not_affected: str, examples: list[str]) -> dict:
    return {
        "type": "choice",
        "instructions": {
            "question": question,
            "context": "`release.audience` describes who receives the change.",
        },
        "criteria": {
            "affected": {"what": affected, "not_for": not_affected, "examples": examples},
            "unaffected": {"what": f"The change does not involve: {affected}", "not_for": "Changes that do involve these"},
            "unclear": {"what": "The description does not say enough to decide either way"},
        },
    }


def _rollout_question(question: str) -> dict:
    return {
        "type": "noul",
        "instructions": question,
        "criteria": {
            "true": "The plan explicitly states this",
            "false": "The plan does not state this, or the plan is empty",
        },
    }


def build_questions() -> dict:
    questions = {key: _impact_question(*spec[1:]) for key, spec in IMPACT_AREAS.items()}
    questions |= {key: _rollout_question(q) for key, (_, q) in ROLLOUT_ELEMENTS.items()}
    return questions


def label(key: str) -> str:
    return (IMPACT_AREAS.get(key) or ROLLOUT_ELEMENTS[key])[0]
