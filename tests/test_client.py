import json

import httpx
import pytest

from app.config import Settings
from app.jev.client import JevError, ask
from app.jev.questions import build_questions
from tests.helpers import raw_response

SETTINGS = Settings(api_key="test-key", model="jev-latest", timeout_seconds=1, data_path="unused")
QUESTIONS = build_questions()


def transport(*responses):
    """Mock transport returning the given responses in order; records requests."""
    queue, seen = list(responses), []

    def handler(request):
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    t = httpx.MockTransport(handler)
    t.seen = seen
    return t


def call(t, settings=SETTINGS):
    return ask({"release": {}}, QUESTIONS, settings, transport=t, sleep=lambda s: None)


def test_sends_documented_request_shape():
    t = transport(httpx.Response(200, json=raw_response()))
    result = call(t)
    req = t.seen[0]
    assert req.url == "https://api.typesafe.ai/v1/systemone"
    assert req.headers["authorization"] == "Bearer test-key"
    body = json.loads(req.content)
    assert set(body) == {"state", "model", "questions"} and body["model"] == "jev-latest"
    assert result.model == "jev-1.13.0"


def test_missing_key_fails_before_any_request():
    t = transport()
    with pytest.raises(JevError) as e:
        call(t, Settings(api_key=None, model="jev-latest", timeout_seconds=1, data_path="x"))
    assert e.value.code == "missing_credentials" and not t.seen


@pytest.mark.parametrize("status, code", [(401, "auth_failed"), (403, "auth_failed"), (422, "bad_request"),
                                          (400, "bad_request"), (500, "upstream_error")])
def test_http_errors_map_to_codes(status, code):
    with pytest.raises(JevError) as e:
        call(transport(httpx.Response(status, json={"error": "nope"})))
    assert e.value.code == code


def test_bad_request_shows_api_error_message():
    body = {"detail": {"error_type": "invalid_request_error", "message": "questions.a.criteria is required"}}
    with pytest.raises(JevError) as e:
        call(transport(httpx.Response(422, json=body)))
    assert e.value.message == "Jev rejected the request (422): questions.a.criteria is required"


def test_auth_error_message_does_not_leak_key():
    with pytest.raises(JevError) as e:
        call(transport(httpx.Response(401, text="bad key test-key")))
    assert "test-key" not in e.value.message


def test_rate_limit_retries_then_succeeds():
    t = transport(httpx.Response(429, headers={"retry-after": "1"}), httpx.Response(200, json=raw_response()))
    assert call(t).model == "jev-1.13.0" and len(t.seen) == 2


@pytest.mark.parametrize("status, code", [(429, "rate_limited"), (529, "overloaded")])
def test_rate_limit_gives_up_after_retries(status, code):
    t = transport(*[httpx.Response(status)] * 3)
    with pytest.raises(JevError) as e:
        call(t)
    assert e.value.code == code and len(t.seen) == 3


def test_timeout():
    with pytest.raises(JevError) as e:
        call(transport(httpx.ReadTimeout("slow")))
    assert e.value.code == "timeout" and e.value.status == 504


def test_network_error():
    with pytest.raises(JevError) as e:
        call(transport(httpx.ConnectError("down")))
    assert e.value.code == "network"


def test_non_json_body():
    with pytest.raises(JevError) as e:
        call(transport(httpx.Response(200, text="<html>oops</html>")))
    assert e.value.code == "malformed_response"


def test_schema_mismatch():
    raw = raw_response()
    raw["answers"].pop("feature_guide")
    with pytest.raises(JevError) as e:
        call(transport(httpx.Response(200, json=raw)))
    assert e.value.code == "malformed_response" and "feature_guide" in e.value.message
