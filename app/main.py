from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import releases as ops
from app.assessment import allowed_resolutions, interpret
from app.checklist import checklist
from app.config import Settings, load_settings
from app.examples import EXAMPLES, load_example
from app.jev import client as jev
from app.jev.questions import IMPACT_AREAS, ROLLOUT_ELEMENTS, build_questions, build_state, label
from app.models import Brief, Release
from app.readiness import readiness
from app.store import Store


class ResolveBody(BaseModel):
    value: str
    reason: str
    by: str


class ItemBody(BaseModel):
    owner: str = ""
    doc_url: str = ""


class SignOffBody(BaseModel):
    by: str
    note: str = ""


def view(release: Release) -> dict:
    a = release.assessment
    decisions = []
    if a:
        for key, d in a.decisions.items():
            question = (IMPACT_AREAS.get(key) or ROLLOUT_ELEMENTS[key])[1]
            decisions.append({**d.model_dump(), "label": label(key), "question": question,
                              "status": d.status, "allowed_resolutions": allowed_resolutions(d)})
    return {
        "id": release.id,
        "brief": release.brief.model_dump(),
        "brief_version": release.brief_version,
        "is_example": release.is_example,
        "updated_at": release.updated_at,
        "assessment": a and {k: v for k, v in a.model_dump().items() if k != "decisions"},
        "decisions": decisions,
        "checklist": [{"key": e.template.key, "title": e.template.title, "description": e.template.description,
                       "requires_doc": e.template.requires_doc, "area": e.template.area,
                       "provisional": e.provisional, **e.state.model_dump()} for e in checklist(release)],
        "readiness": readiness(release),
    }


def create_app(settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = Store(settings.data_path)
    app = FastAPI(title="Release Readiness Tracker")

    @app.exception_handler(ops.DomainError)
    @app.exception_handler(jev.JevError)
    def domain_error(_: Request, e):
        return JSONResponse({"error": {"code": e.code, "message": e.message}}, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    def invalid_input(_: Request, e: RequestValidationError):
        err = e.errors()[0]
        field = ".".join(str(p) for p in err["loc"][1:]) or "body"
        return JSONResponse({"error": {"code": "invalid_input", "message": f"{field}: {err['msg']}"}}, 422)

    def mutate(release_id: str, change) -> dict:
        with store.lock:
            release = store.get(release_id)
            change(release)
            store.save(release)
        return view(release)

    @app.get("/api/status")
    def status():
        return {"live_assessments": bool(settings.api_key), "model": settings.model,
                "examples": list(EXAMPLES)}

    @app.get("/api/releases")
    def list_releases():
        return [{"id": r.id, "title": r.brief.title, "is_example": r.is_example, "updated_at": r.updated_at,
                 "status": readiness(r)["status"]}
                for r in sorted(store.all(), key=lambda r: r.updated_at, reverse=True)]

    @app.post("/api/releases", status_code=201)
    def create_release(brief: Brief):
        release = ops.new_release(brief)
        store.save(release)
        return view(release)

    @app.post("/api/examples/{name}", status_code=201)
    def create_example(name: str):
        if name not in EXAMPLES:
            raise ops.DomainError("not_found", "Unknown example.", 404)
        release = load_example(name)
        store.save(release)
        return view(release)

    @app.get("/api/releases/{release_id}")
    def get_release(release_id: str):
        return view(store.get(release_id))

    @app.patch("/api/releases/{release_id}")
    def edit_brief(release_id: str, brief: Brief):
        return mutate(release_id, lambda r: ops.update_brief(r, brief))

    @app.post("/api/releases/{release_id}/assess")
    def assess(release_id: str):
        release = store.get(release_id)
        version, questions = release.brief_version, build_questions()
        response = jev.ask(build_state(release.brief), questions, settings, transport=transport)
        assessment = interpret(response, "live", version, ops.now())
        return mutate(release_id, lambda r: ops.apply_assessment(r, assessment))

    @app.post("/api/releases/{release_id}/decisions/{key}/resolve")
    def resolve(release_id: str, key: str, body: ResolveBody):
        return mutate(release_id, lambda r: ops.resolve_decision(r, key, body.value, body.reason, body.by))

    @app.patch("/api/releases/{release_id}/items/{key}")
    def edit_item(release_id: str, key: str, body: ItemBody):
        return mutate(release_id, lambda r: ops.update_item(r, key, body.owner, body.doc_url))

    @app.post("/api/releases/{release_id}/items/{key}/signoff")
    def sign_off(release_id: str, key: str, body: SignOffBody):
        return mutate(release_id, lambda r: ops.sign_off(r, key, body.by, body.note))

    @app.delete("/api/releases/{release_id}/items/{key}/signoff")
    def revoke(release_id: str, key: str):
        return mutate(release_id, lambda r: ops.revoke_sign_off(r, key))

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
    return app


app = create_app()
