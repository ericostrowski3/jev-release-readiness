"""HTTP client for Jev (POST /v1/systemone). Every failure becomes a JevError;
there is no fallback to illustrative data."""

import time

import httpx

from app.config import JEV_URL, Settings
from app.jev.schema import JevResponse, MalformedResponse, validate_response

MAX_ATTEMPTS = 3  # first try + 2 retries on 429/529
MAX_RETRY_DELAY = 5.0


class JevError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def ask(state: dict, questions: dict, settings: Settings,
        transport: httpx.BaseTransport | None = None, sleep=time.sleep) -> JevResponse:
    if not settings.api_key:
        raise JevError("missing_credentials",
                       "TYPESAFE_API_KEY is not set on the server. Add it to .env and restart.", 503)

    body = {"state": state, "model": settings.model, "questions": questions}
    headers = {"Authorization": f"Bearer {settings.api_key}"}
    with httpx.Client(transport=transport, timeout=settings.timeout_seconds) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = client.post(JEV_URL, json=body, headers=headers)
            except httpx.TimeoutException:
                raise JevError("timeout", f"Jev did not respond within {settings.timeout_seconds:g}s.", 504)
            except httpx.HTTPError as e:
                raise JevError("network", f"Could not reach Jev: {type(e).__name__}.", 502)
            if resp.status_code in (429, 529) and attempt < MAX_ATTEMPTS - 1:
                sleep(_retry_delay(resp, attempt))
                continue
            break

    _raise_for_status(resp)
    try:
        raw = resp.json()
    except ValueError:
        raise JevError("malformed_response", "Jev returned a response that is not JSON.")
    try:
        return validate_response(raw, questions)
    except MalformedResponse as e:
        raise JevError("malformed_response", f"Jev's response was rejected: {e}")


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    try:
        return min(float(resp.headers["retry-after"]), MAX_RETRY_DELAY)
    except (KeyError, ValueError):
        return min(0.5 * 2**attempt, MAX_RETRY_DELAY)


def _error_message(resp: httpx.Response) -> str:
    # Observed live: {"detail": {"error_type": ..., "message": ...}}
    try:
        return str(resp.json()["detail"]["message"])[:300]
    except (ValueError, KeyError, TypeError):
        return resp.text[:300]


def _raise_for_status(resp: httpx.Response) -> None:
    code = resp.status_code
    if code < 400:
        return
    detail = _error_message(resp)
    if code in (401, 403):
        raise JevError("auth_failed", "Jev rejected the API key. Check TYPESAFE_API_KEY.")
    if code == 429:
        raise JevError("rate_limited", "Jev rate limit reached. Wait a moment and try again.", 429)
    if code == 529:
        raise JevError("overloaded", "Jev is temporarily overloaded. Try again shortly.", 503)
    if code in (400, 413, 415, 422):
        raise JevError("bad_request", f"Jev rejected the request ({code}): {detail}")
    raise JevError("upstream_error", f"Jev returned HTTP {code}.")
