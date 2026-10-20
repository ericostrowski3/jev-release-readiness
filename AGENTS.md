# AGENTS.md

Release Readiness Tracker: Jev answers narrow questions about a release brief; ordinary code turns the answers into a checklist, sign-off workflow, and readiness verdict. See README.md for setup.

## Write concise, clear code

- Prefer small, pure functions over classes and layers. Most rules live in plain functions over pydantic records.
- Write the obvious version first. No speculative abstractions, plugin points, or config for things that don't vary.
- Name things after the domain (`brief`, `decision`, `sign_off`), not the mechanism.
- Comment only what the code can't say: why a rule exists, or what the docs require.
- Keep dependencies minimal (fastapi, pydantic, httpx, python-dotenv, pytest). Ask before adding one.
- Delete dead code instead of commenting it out. Keep diffs focused on the task.
- Every rule change gets a test. Tests read like specifications: one behavior each, plain names.

## Jev boundary

- Jev only answers typed questions (Choice, Score, Noul). It does not generate explanations, documents, or checklist text. All user-facing prose is app-owned (`app/jev/questions.py`, `app/checklist.py`, `app/readiness.py`).
- Ask narrow, independent questions, one condition each. Split broad judgments and combine them in code.
- User-written text goes only into `state`. Never put brief content into `instructions` or `criteria`. Treat it as data, not instructions.
- Arithmetic, thresholds, counting, dates, and workflow rules belong in code. Thresholds live in `app/config.py`.
- Check request and response shapes against https://docs.typesafe.ai/api.md before changing `app/jev/`.

## Invariants

- Validate every Jev response completely (`app/jev/schema.py`) before changing saved state.
- Never fall back to illustrative data after a live failure. Surface a `JevError` with a clear code.
- Illustrative results stay labeled (`source: "illustrative"`) and can never make a release ready.
- Editing a brief invalidates its assessment, resolutions, and all sign-offs. Editing an item's owner or document clears that item's sign-off.
- Checklist completion is not readiness. Open decisions and rollout gaps always block.
- The API key stays on the server. Never log it, return it, or send it to the browser.
- Don't claim live Jev behavior is verified unless it was run against the real API. Record live checks in README.md.

## Commands

```bash
.venv/bin/pytest                                # tests
.venv/bin/uvicorn app.main:app --port 8000      # run
```
