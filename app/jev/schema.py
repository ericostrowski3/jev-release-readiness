"""Validation of Jev responses against the questions we asked (docs: /api)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, ValidationError

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ChoiceAnswer(BaseModel):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, Probability]
    confidence: Probability


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: Probability


Answer = Annotated[ChoiceAnswer | NoulAnswer, Field(discriminator="type")]


class JevResponse(BaseModel):
    model: str
    answers: dict[str, Answer]
    usage: dict | None = None


class MalformedResponse(Exception):
    pass


def validate_response(raw: object, questions: dict) -> JevResponse:
    """Parse a raw response and check it answers exactly what was asked."""
    try:
        response = JevResponse.model_validate(raw)
    except ValidationError as e:
        raise MalformedResponse(f"Response does not match the documented shape: {e.errors()[0]['msg']}") from e

    for key, question in questions.items():
        answer = response.answers.get(key)
        if answer is None:
            raise MalformedResponse(f"Missing answer for '{key}'.")
        if answer.type != question["type"]:
            raise MalformedResponse(f"Answer for '{key}' has type '{answer.type}', expected '{question['type']}'.")
        if isinstance(answer, ChoiceAnswer):
            options = set(question["criteria"])
            if answer.choice not in options or set(answer.probabilities) != options:
                raise MalformedResponse(f"Answer for '{key}' uses options outside the ones asked.")
            if abs(sum(answer.probabilities.values()) - 1) > 0.02:
                raise MalformedResponse(f"Probabilities for '{key}' do not sum to 1.")
    return response
