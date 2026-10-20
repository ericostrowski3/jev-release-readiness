import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Brief
from app.releases import update_brief
from app.store import Store
from tests.helpers import UNCLEAR, raw_response

BRIEF = {"title": "Edit display name", "change_description": "Users can rename themselves.",
         "audience": "All users", "rollout_plan": "Ship Nov 12."}


@pytest.fixture
def make_client(tmp_path):
    def make(handler=None, api_key="test-key"):
        settings = Settings(api_key=api_key, model="jev-latest", timeout_seconds=1,
                            data_path=str(tmp_path / "releases.json"))
        transport = httpx.MockTransport(handler) if handler else None
        return TestClient(create_app(settings, transport)), settings
    return make


def ok(_request):
    return httpx.Response(200, json=raw_response(impact={"legal_copy": UNCLEAR}))


def test_full_workflow(make_client):
    client, _ = make_client(ok)
    rid = client.post("/api/releases", json=BRIEF).json()["id"]
    assert client.get(f"/api/releases/{rid}").json()["readiness"]["status"] == "not_assessed"

    r = client.post(f"/api/releases/{rid}/assess").json()
    assert r["assessment"]["source"] == "live" and r["assessment"]["model"] == "jev-1.13.0"
    legal = next(d for d in r["decisions"] if d["key"] == "legal_copy")
    assert legal["status"] == "needs_review" and legal["label"] == "Legal copy"
    assert any(i["key"] == "legal_review" and i["provisional"] for i in r["checklist"])

    r = client.post(f"/api/releases/{rid}/decisions/legal_copy/resolve",
                    json={"value": "affected", "reason": "Names appear publicly.", "by": "Ana"}).json()
    for item in r["checklist"]:
        client.patch(f"/api/releases/{rid}/items/{item['key']}", json={"owner": "Sam", "doc_url": "https://d.example"})
        r = client.post(f"/api/releases/{rid}/items/{item['key']}/signoff", json={"by": "Sam"}).json()
    assert r["readiness"] == {"status": "ready", "checklist": {"signed": 3, "total": 3},
                              "rollout": {"covered": 5, "total": 5}, "gaps": []}

    r = client.patch(f"/api/releases/{rid}", json={**BRIEF, "rollout_plan": "Ship Nov 19."}).json()
    assert r["assessment"] is None and r["checklist"] == [] and r["readiness"]["status"] == "not_assessed"


def test_progress_persists_across_app_restarts(make_client):
    client, _ = make_client(ok)
    rid = client.post("/api/releases", json=BRIEF).json()["id"]
    client.post(f"/api/releases/{rid}/assess")
    client.patch(f"/api/releases/{rid}/items/brief_review", json={"owner": "Sam"})
    client2, _ = make_client(ok)
    assert client2.get(f"/api/releases/{rid}").json()["checklist"][0]["owner"] == "Sam"


@pytest.mark.parametrize("handler, code, status", [
    (lambda r: httpx.Response(401), "auth_failed", 502),
    (lambda r: httpx.Response(429), "rate_limited", 429),
    (lambda r: httpx.Response(200, text="not json"), "malformed_response", 502),
    (lambda r: httpx.Response(200, json={"model": "x", "answers": {}}), "malformed_response", 502),
])
def test_live_failures_leave_saved_state_unchanged(make_client, handler, code, status, monkeypatch):
    monkeypatch.setattr("app.jev.client.time.sleep", lambda s: None)
    client, _ = make_client(handler)
    rid = client.post("/api/examples/email-verification").json()["id"]
    before = client.get(f"/api/releases/{rid}").json()
    resp = client.post(f"/api/releases/{rid}/assess")
    assert resp.status_code == status and resp.json()["error"]["code"] == code
    assert client.get(f"/api/releases/{rid}").json() == before  # illustrative result untouched, not replaced


def test_missing_key_never_substitutes_demo(make_client):
    client, _ = make_client(ok, api_key=None)
    assert client.get("/api/status").json()["live_assessments"] is False
    rid = client.post("/api/releases", json=BRIEF).json()["id"]
    resp = client.post(f"/api/releases/{rid}/assess")
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "missing_credentials"
    assert client.get(f"/api/releases/{rid}").json()["assessment"] is None


def test_brief_edited_during_assessment_discards_result(make_client):
    holder = {}

    def edit_then_answer(request):
        store = Store(holder["settings"].data_path)
        release = store.get(holder["rid"])
        update_brief(release, Brief(title="Changed mid-flight"))
        store.save(release)
        return ok(request)

    client, holder["settings"] = make_client(edit_then_answer)
    holder["rid"] = client.post("/api/releases", json=BRIEF).json()["id"]
    resp = client.post(f"/api/releases/{holder['rid']}/assess")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "stale_assessment"
    assert client.get(f"/api/releases/{holder['rid']}").json()["assessment"] is None


def test_examples_are_labeled_illustrative(make_client):
    client, _ = make_client()
    r = client.post("/api/examples/display-name").json()
    assert r["is_example"] and r["assessment"]["source"] == "illustrative"
    assert r["readiness"]["gaps"][0]["message"].startswith("Assessment is an illustrative example")


def test_input_validation_errors(make_client):
    client, _ = make_client()
    resp = client.post("/api/releases", json={"title": ""})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "invalid_input"
    assert client.get("/api/releases/nope").status_code == 404
    rid = client.post("/api/examples/display-name").json()["id"]
    resp = client.post(f"/api/releases/{rid}/items/rollout_approval/signoff", json={"by": "Sam"})
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "missing_owner"
