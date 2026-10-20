const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
let current = null;

const STATUS_TEXT = {
  impact: { affected: "Affected — checklist items added", unaffected: "Not affected",
            needs_review: "Unclear — needs your decision" },
  rollout: { present: "Covered", missing: "Not covered", needs_review: "Unclear — needs review",
             not_applicable: "Marked not applicable" },
};
const RESOLUTION_TEXT = { affected: "Affected", unaffected: "Not affected", present: "Covered",
                          not_applicable: "Not applicable" };

async function api(method, path, body) {
  const res = await fetch(path, {
    method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ error: { message: `HTTP ${res.status}` } }));
  if (!res.ok) throw new Error(data.error?.message || `HTTP ${res.status}`);
  return data;
}

async function act(fn, errorEl) {
  try { show(await fn()); } catch (e) { (errorEl || $("#action-error")).innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

async function loadList() {
  const list = await api("GET", "/api/releases");
  $("#release-list").innerHTML = list.map((r) =>
    `<li data-id="${r.id}" class="${r.id === current?.id ? "active" : ""}">${esc(r.title)}
       <div class="muted">${r.is_example ? "Example · " : ""}<span class="${r.status}">${r.status.replace("_", " ")}</span></div></li>`).join("");
  document.querySelectorAll("#release-list li").forEach((li) =>
    li.onclick = () => act(() => api("GET", `/api/releases/${li.dataset.id}`)));
}

function show(release) {
  current = release;
  render(release);
  loadList();
}

function render(r) {
  const rd = r.readiness;
  $("#detail").innerHTML = `
    <div id="action-error"></div>
    <section>
      <div class="row"><h2>Readiness: <span class="badge ${rd.status}">${rd.status.replace("_", " ")}</span></h2></div>
      <p class="muted">Checklist signed: ${rd.checklist.signed}/${rd.checklist.total} ·
         Rollout plan coverage: ${rd.rollout.covered}/${rd.rollout.total}</p>
      ${rd.gaps.length ? `<strong>Remaining before release</strong><ul class="gaps">${rd.gaps.map((g) => `<li>${esc(g.message)}</li>`).join("")}</ul>` : "<p class='ready'>No remaining gaps.</p>"}
    </section>
    ${briefForm(r)}
    <section>
      <h2>Assessment</h2>
      ${r.assessment?.source === "illustrative" ? `<div class="banner"><strong>Illustrative example — not a Jev result.</strong> These answers are hand-written fixtures so you can explore the workflow. Run a live assessment once an API key is configured.</div>` : ""}
      <div class="row"><button class="primary" id="assess">Run Jev assessment</button>
        <span class="muted">${r.assessment ? `Last run ${esc(r.assessment.created_at)} · ${esc(r.assessment.source)} · model ${esc(r.assessment.model)}` : "Not assessed yet."}</span></div>
      <div id="assess-error"></div>
      ${decisionGroup(r, "impact", "Impact areas")}
      ${decisionGroup(r, "rollout", "Rollout plan")}
    </section>
    <section>
      <h2>Checklist</h2>
      ${r.checklist.length ? r.checklist.map(itemCard).join("") : "<p class='muted'>The checklist is built after an assessment.</p>"}
    </section>`;
  bind(r);
}

function briefForm(r) {
  const b = r.brief;
  return `<section><h2>Release brief</h2>
    <form id="brief">
      <label>Title<input name="title" value="${esc(b.title)}" required></label>
      <label>What is changing<textarea name="change_description">${esc(b.change_description)}</textarea></label>
      <label>Intended audience<textarea name="audience">${esc(b.audience)}</textarea></label>
      <label>Rollout plan<textarea name="rollout_plan">${esc(b.rollout_plan)}</textarea></label>
      <div class="row"><button>Save brief</button>
        <span class="muted">Saving a changed brief clears its assessment and every sign-off.</span></div>
    </form></section>`;
}

function decisionGroup(r, kind, title) {
  const ds = r.decisions.filter((d) => d.kind === kind);
  if (!ds.length) return "";
  return `<h3>${title}</h3>` + ds.map((d) => `
    <div class="card">
      <div class="row"><strong>${esc(d.label)}</strong>
        <span class="${d.status}">${esc(STATUS_TEXT[kind][d.status] || RESOLUTION_TEXT[d.status])}</span></div>
      ${d.resolution ? `<p class="muted">Resolved by ${esc(d.resolution.by)}: “${esc(d.resolution.reason)}”
          (model said: ${esc(STATUS_TEXT[kind][d.model_status])})</p>` : ""}
      <details><summary class="muted">Model details</summary>
        <p class="muted">Question: ${esc(d.question)}</p>
        <p class="muted">${answerText(d.model_answer)}</p>
        <pre>${esc(JSON.stringify(d.model_answer, null, 2))}</pre>
      </details>
      ${["needs_review", "missing"].includes(d.status)
        ? resolveForm(d)
        : `<details><summary class="muted">Override this decision</summary>${resolveForm(d)}</details>`}
    </div>`).join("");
}

function answerText(a) {
  if (a.type === "choice") return `Jev chose “${esc(a.choice)}” with confidence ${a.confidence.toFixed(2)} (0 = evenly split, 1 = certain).`;
  return `Jev's probability that the plan covers this: ${a.noul.toFixed(2)}.`;
}

function resolveForm(d) {
  return `<form class="resolve row" data-key="${d.key}">
    <select name="value">${d.allowed_resolutions.map((v) => `<option value="${v}">${RESOLUTION_TEXT[v]}</option>`).join("")}</select>
    <input name="reason" placeholder="Reason (required)" required>
    <input name="by" placeholder="Your name" required>
    <button>${d.resolution ? "Change decision" : "Record decision"}</button></form>`;
}

function itemCard(i) {
  const signed = i.signoff;
  return `<div class="card">
    <div class="row"><strong>${esc(i.title)}</strong>
      ${i.provisional ? `<span class="needs_review">Provisional — depends on an unresolved decision</span>` : ""}
      <span class="${signed ? "ready" : "blocked"}">${signed ? `Signed off by ${esc(signed.by)}` : "Awaiting sign-off"}</span></div>
    <p class="muted">${esc(i.description)}</p>
    <form class="item row" data-key="${i.key}">
      <input name="owner" placeholder="Owner" value="${esc(i.owner)}">
      <input name="doc_url" placeholder="${i.requires_doc ? "Document link (required)" : "Document link (optional)"}" value="${esc(i.doc_url)}">
      <button>Save</button></form>
    ${i.doc_url ? `<p class="muted"><a href="${esc(i.doc_url)}" target="_blank" rel="noopener">Open document</a></p>` : ""}
    ${signed
      ? `<p class="muted">${esc(signed.at)}${signed.note ? ` · “${esc(signed.note)}”` : ""} <button class="revoke" data-key="${i.key}">Revoke</button></p>`
      : `<form class="signoff row" data-key="${i.key}">
           <input name="by" placeholder="Signer name" required><input name="note" placeholder="Note (optional)">
           <button>Sign off</button></form>`}
  </div>`;
}

const formData = (form) => Object.fromEntries(new FormData(form));
const errorSlot = (form) => {
  if (!form.nextElementSibling?.classList.contains("form-error")) form.insertAdjacentHTML("afterend", "<div class='form-error'></div>");
  return form.nextElementSibling;
};

function bind(r) {
  const base = `/api/releases/${r.id}`;
  $("#brief").onsubmit = (e) => { e.preventDefault(); act(() => api("PATCH", base, formData(e.target)), errorSlot(e.target)); };
  $("#assess").onclick = async (e) => {
    e.target.disabled = true; e.target.textContent = "Assessing…"; $("#assess-error").innerHTML = "";
    await act(() => api("POST", `${base}/assess`), $("#assess-error"));
    e.target.disabled = false; e.target.textContent = "Run Jev assessment";
  };
  const on = (sel, fn) => document.querySelectorAll(sel).forEach((f) => f.onsubmit = (e) => { e.preventDefault(); act(() => fn(f), errorSlot(f)); });
  on("form.resolve", (f) => api("POST", `${base}/decisions/${f.dataset.key}/resolve`, formData(f)));
  on("form.item", (f) => api("PATCH", `${base}/items/${f.dataset.key}`, formData(f)));
  on("form.signoff", (f) => api("POST", `${base}/items/${f.dataset.key}/signoff`, formData(f)));
  document.querySelectorAll("button.revoke").forEach((b) =>
    b.onclick = () => act(() => api("DELETE", `${base}/items/${b.dataset.key}/signoff`)));
}

$("#new-release").onclick = () => act(() => api("POST", "/api/releases", { title: "Untitled release" }));

(async () => {
  const s = await api("GET", "/api/status");
  $("#live-status").textContent = s.live_assessments
    ? `Live assessments enabled (${s.model})`
    : "No API key configured: live assessments disabled, illustrative examples only";
  $("#example-buttons").innerHTML = s.examples.map((n) =>
    `<button data-name="${n}">Load example: ${n.replace("-", " ")}</button>`).join("");
  document.querySelectorAll("#example-buttons button").forEach((b) =>
    b.onclick = () => act(() => api("POST", `/api/examples/${b.dataset.name}`)));
  loadList();
})();
