import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

JEV_URL = "https://api.typesafe.ai/v1/systemone"

# Decision thresholds. Code owns these; tune them against labeled releases.
IMPACT_MIN_CONFIDENCE = 0.6  # below this, an impact decision needs human review
ROLLOUT_PRESENT_AT = 0.75  # noul at or above: the rollout plan covers the element
ROLLOUT_MISSING_AT = 0.25  # noul at or below: the rollout plan omits the element


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    model: str
    timeout_seconds: float
    data_path: str


def load_settings() -> Settings:
    return Settings(
        api_key=os.getenv("TYPESAFE_API_KEY") or None,
        model=os.getenv("JEV_MODEL", "jev-latest"),
        timeout_seconds=float(os.getenv("JEV_TIMEOUT_SECONDS", "10")),
        data_path=os.getenv("DATA_PATH", "data/releases.json"),
    )
