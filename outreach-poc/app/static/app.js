// SalesAssist Outreach Assist - light front end (vanilla JS, no build step).
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
const initials = (name) => name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

const state = { userId: null, users: [], data: null, advisor: null, active: 0, edits: {}, done: {} };

const STEPS = [
  ["access", "Checking region access"],
  ["assemble", "Pulling CRM activity, sales, holdings, fund data and documents"],
  ["signals", "Detecting outreach signals"],
  ["intents", "Classifying intent"],
  ["evidence", "Applying evidence rules (share class, audience, approval)"],
  ["draft", "Drafting emails and admin actions"],
  ["verify", "Verifying every claim against source data"],
];

const MAIL_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>';

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(body.detail || res.statusText); e.status = res.status; throw e; }
  return body;
}

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3200);
}

// ------------------------------------------------------------------ advisor list
async function init() {
  const [health, users] = await Promise.all([api("/api/health"), api("/api/users")]);
  $("mode").textContent = health.agents ? `CrewAI agents · ${health.mode.replace("crew · ", "")}` : `Drafting: ${health.mode}`;
  $("mode").title = health.agents ? "CrewAI multi-agent orchestration over SalesAssist MCP servers" : "Single drafter";
  $("refDate").textContent = fmtDate(health.reference_date);
  state.users = users;
  $("userSelect").innerHTML = users.map((u) => `<option value="${u.user_id}">${esc(u.display_name)} · ${u.region_identifier}</option>`).join("");
  state.userId = users[0].user_id;
  $("userSelect").addEventListener("change", (e) => { state.userId = e.target.value; loadAdvisors(); });
  $("allRegions").addEventListener("change", loadAdvisors);
  loadAdvisors();
}

async function loadAdvisors() {
  const user = state.users.find((u) => u.user_id === state.userId);
  $("regionChip").textContent = `Region ${user.region_identifier}`;
  const rows = await api(`/api/advisors?user_id=${state.userId}&all_regions=${$("allRegions").checked}`);
  $("advisorRows").innerHTML = rows.map((r) => `
    <tr class="${r.in_region ? "" : "out"}">
      <td><div class="who"><span class="avatar">${initials(r.name)}</span><div><div class="name">${esc(r.name)}</div><div class="email">${esc(r.email)}</div></div></div></td>
      <td>${esc(r.firm)}</td>
      <td>${r.region}${r.in_region ? "" : ' <span class="muted small">(not yours)</span>'}</td>
      <td>${r.last_contact ? `${fmtDate(r.last_contact.date)} <span class="muted small">· ${esc(r.last_contact.channel)}</span>` : '<span class="muted">—</span>'}</td>
      <td>${r.signals.map((s) => `<span class="sig ${s.type}">${esc(s.title)}</span>`).join("") || '<span class="muted small">—</span>'}</td>
      <td class="right"><button class="mail-btn" data-id="${r.advisor_id}" data-name="${esc(r.name)}" data-firm="${esc(r.firm)}" aria-label="Prepare email to ${esc(r.name)}" title="Prepare email">${MAIL_ICON}</button></td>
    </tr>`).join("") || '<tr><td colspan="6" class="muted">No advisors in your region.</td></tr>';
  document.querySelectorAll(".mail-btn").forEach((b) => b.addEventListener("click", () => openComposer(b.dataset)));
}

// ------------------------------------------------------------------ composer
async function openComposer({ id, name, firm }) {
  state.advisor = id; state.active = 0; state.edits = {}; state.done = {};
  $("composer").hidden = false;
  $("dlgTitle").textContent = `New outreach · ${name}`;
  $("dlgSub").textContent = firm;
  $("dlgAvatar").textContent = initials(name);
  $("progress").hidden = false; $("dlgBody").hidden = true; $("blocked").hidden = true;
  $("actionResults").innerHTML = "";

  const list = $("progressSteps");
  list.innerHTML = STEPS.map(([k, l]) => `<li data-k="${k}"><span class="dot"></span><span>${l}</span><span class="ms"></span></li>`).join("");
  const items = [...list.children];
  let i = 0;
  const tick = setInterval(() => {               // animated while the request is in flight
    if (i > 0) items[i - 1].className = "done";
    if (i < items.length) items[i].className = "run";
    i = Math.min(i + 1, items.length - 1);
  }, 350);

  try {
    const data = await api(`/api/outreach/${id}?user_id=${state.userId}`);
    clearInterval(tick);
    state.data = data;
    for (const t of data.trace) {
      const li = list.querySelector(`[data-k="${t.key}"]`);
      if (li) { li.className = "done"; li.querySelector(".ms").textContent = data.cache === "hit" ? "cached" : `${t.ms} ms`; }
    }
    items.forEach((li) => (li.className = "done"));
    setTimeout(() => { $("progress").hidden = true; $("dlgBody").hidden = false; render(); }, 450);
  } catch (e) {
    clearInterval(tick);
    $("progress").hidden = true;
    if (e.status === 403) { $("blocked").hidden = false; $("blockedMsg").textContent = e.message; }
    else { $("blocked").hidden = false; $("blockedMsg").textContent = `Something went wrong: ${e.message}`; }
  }
}

function closeComposer() { $("composer").hidden = true; state.data = null; }

function option() { return state.data.options[state.active]; }

function linkify(text) {
  return esc(text).replace(/https?:\/\/[^\s<]+/g, (u) => `<a href="${u}" target="_blank" rel="noopener">${u}</a>`);
}

function render() {
  const d = state.data;
  if (!d.options.length) {
    $("intentTabs").innerHTML = "";
    $("banners").innerHTML = '<div class="banner info">No timely reason to contact this advisor was found in the data.</div>';
    return;
  }
  $("intentTabs").innerHTML = d.options.map((o, i) => `
    <button class="tab" role="tab" aria-selected="${i === state.active}" data-i="${i}">
      <span class="badge">${i === 0 ? "Recommended" : "Alternative"}</span>
      <span class="t">${esc(o.pack.intent.label)}</span>
      <span class="s">score ${o.pack.intent.score.toFixed(2)}</span>
    </button>`).join("");
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => { saveEdits(); state.active = +t.dataset.i; render(); }));
  renderOption();
}

function renderOption() {
  const o = option(), p = o.pack, d = state.data;
  const edit = state.edits[p.intent.id];

  // banners: gaps, model notes, compliance-review notes
  const banners = [];
  p.gaps.forEach((g) => banners.push(`<div class="banner warn">⚠ ${esc(g)}</div>`));
  if (o.draft.note) banners.push(`<div class="banner info">ℹ ${esc(o.draft.note)}</div>`);
  if (o.draft.review_issues?.length) banners.push(`<div class="banner info">Compliance reviewer adjusted: ${esc(o.draft.review_issues.join("; "))}</div>`);
  $("banners").innerHTML = banners.join("");

  const sender = d.user.DISPLAY_NAME ?? d.user.display_name;  // source records serialise with feed aliases
  $("fromField").textContent = `${sender} (Franklin Templeton)`;
  $("toField").textContent = `${d.advisor.name} <${d.advisor.email}>`;
  $("subject").value = edit?.subject ?? o.draft.subject;
  $("bodyEditor").innerHTML = linkify(edit?.body ?? o.draft.body);
  $("toneSelect").value = p.tone.style;

  // data links
  $("linksCard").hidden = !p.links.length;
  $("links").innerHTML = p.links.map((l) => `
    <a class="link" href="${l.url}" target="_blank" rel="noopener">
      <span class="t">${esc(l.content_type)} · ${esc(l.share_class_id)}</span>
      <span class="m"><span class="ok-pill">${esc(l.review_status)}</span><span class="ok-pill">${esc(l.audience)}</span> ${esc(l.content_id)} · released ${fmtDate(l.release_date)}</span>
    </a>`).join("");

  // verification
  const v = o.verification;
  $("verifyBadge").className = `verify ${v.passed ? "pass" : "fail"}`;
  $("verifyBadge").innerHTML = v.passed
    ? `✓ ${v.checked ? `${v.checked} claim${v.checked === 1 ? "" : "s"} checked against source data` : "No figures or links to check · wording only"} · ${esc(o.draft.generator)}${o.draft.reviewed_by ? " · reviewed" : ""}`
    : `✕ ${esc(v.issues.join("; "))}`;
  if (v.warnings.length) $("verifyBadge").innerHTML += ` <span class="muted small">(${esc(v.warnings.join("; "))})</span>`;

  // summary: why
  const sigById = Object.fromEntries(d.signals.map((s) => [s.id, s]));
  // Rationale = agent's reason + "[rules: …]" cross-check; show them separately.
  const m = p.intent.rationale.match(/^(.*?)\s*\[(?:rules: )?(.*)\]$/s);
  $("whyText").innerHTML = m
    ? `${esc(m[1])}<br><span class="muted small">Rule check: ${esc(m[2])}</span>`
    : esc(p.intent.rationale);
  const sigs = [p.intent.primary_signal_id, ...p.intent.supporting_signal_ids].map((id) => sigById[id]).filter(Boolean);
  const evidence = [...new Set(sigs.flatMap((s) => s.evidence_ids))];
  $("signalChips").innerHTML = evidence.map((e) => `<span class="chip" title="${esc(evidenceTitle(e))}">${esc(e)}</span>`).join("");

  // facts
  $("facts").innerHTML = p.facts.filter((f) => f.kind !== "caveat").map((f) => `
    <li><label>
      <input type="checkbox" data-f="${f.id}" ${f.included ? "checked" : ""} ${f.optional || f.kind === "document" ? "" : "disabled"}>
      <span>${esc(f.statement)}<br><span class="src">${esc(f.source)}${f.evidence_id ? " · " + esc(f.evidence_id) : ""}</span>
      ${f.warning ? `<br><span class="w">⚠ ${esc(f.warning)}</span>` : ""}</span>
    </label></li>`).join("");
  $("applyFacts").hidden = true;
  document.querySelectorAll("#facts input").forEach((c) => c.addEventListener("change", () => ($("applyFacts").hidden = false)));

  // exclusions
  $("exclusions").innerHTML = p.exclusions.map((e) => `<li><div class="i">${esc(e.item)}</div><div class="r">${esc(e.reason)}</div></li>`).join("")
    || '<li class="muted">Nothing excluded.</li>';
  if (d.rejected_intents?.length) {
    $("exclusions").innerHTML += d.rejected_intents.map((r) => `<li><div class="i">Agent suggestion: ${esc(r.intent_type)}</div><div class="r">${esc(r.reason)}</div></li>`).join("");
  }

  // snapshot
  const a = d.advisor;
  $("snapshot").innerHTML = [
    a.relationship_comments ? `<div class="muted">“${esc(a.relationship_comments)}”</div>` : "",
    a.recent_sale ? `<div class="row"><span>Latest business (${fmtDate(a.recent_sale.MOST_RECENT_TRANSACTION_DATE)})</span><b>${money(a.recent_sale.MOST_RECENT_TRANSACTION_AMOUNT)} ${esc(a.recent_sale.RECENT_TRANSACTION_DIRECTION)}</b></div>` : '<div class="muted">No recent sales record (unknown)</div>',
    ...(a.holdings.length ? a.holdings.map((h) => `<div class="row"><span>${esc(h.PRODUCT_NAME)} <span class="muted">${esc(h.PRODUCT_SHARE_CLASS_ID)}</span></span><span>${money(h.CURRENT_HOLDING_VALUE)} <span class="muted">(${h.HOLDING_VALUE_CHANGE >= 0 ? "+" : ""}${money(h.HOLDING_VALUE_CHANGE)})</span></span></div>`)
      : ['<div class="muted">No holdings records (unknown)</div>']),
    a.holdings.length ? `<div class="muted small">Holdings as of ${fmtDate(a.holdings[0].REFERENCE_DATE)}. Not quoted to the advisor.</div>` : "",
  ].join("");

  // trace
  $("trace").innerHTML = d.trace.map((t) => `<li><span><span class="actor ${t.actor}">${t.actor}</span>${esc(t.label)}</span><span class="ms">${t.ms} ms</span><span class="d">${esc(t.detail)}</span></li>`).join("")
    + `<li><span class="d">Engine: ${esc(d.orchestrator)} · ${d.cache === "hit" ? "served from pre-computed cache" : "computed on click"}</span></li>`;

  renderActions();
  updateMailto();
}

function evidenceTitle(id) {
  const d = state.data;
  const req = d.signals.flatMap((s) => s.details?.requests || []).find((r) => r.id === id);
  if (req) return `${req.channel} ${req.date}: ${req.text}`;
  if (id.startsWith("SALE:")) return "Recent sales record (04_recent_sales)";
  if (id.startsWith("PROFILE:")) return "Advisor profile (01_advisors)";
  return id;
}

function renderActions() {
  const p = option().pack;
  const done = state.done[p.intent.id] || {};
  $("actions").innerHTML = p.actions.map((a) => `
    <label class="action ${done[a.id] ? "done" : ""}">
      <input type="checkbox" data-a="${a.id}" ${a.recommended && !done[a.id] ? "checked" : ""} ${done[a.id] ? "disabled" : ""}>
      <span><div class="t">${esc(a.label)}${done[a.id] ? " ✓" : ""}</div><div class="d">${esc(a.description)}</div>
      ${a.payload.slots?.length ? `<div class="d">${a.payload.slots.map(esc).join(" · ")}</div>` : ""}
      ${a.agent_note ? `<div class="n">Agent: ${esc(a.agent_note)}</div>` : ""}</span>
    </label>`).join("") || '<p class="muted small">No follow-up actions suggested.</p>';
  document.querySelectorAll("#actions input").forEach((c) => c.addEventListener("change", updateRunBtn));
  updateRunBtn();
}

function selectedActions() { return [...document.querySelectorAll("#actions input:checked")].map((c) => c.dataset.a); }

function updateRunBtn() {
  const n = selectedActions().length;
  $("runActions").disabled = n === 0;
  $("runActions").textContent = n ? `Run selected actions (${n})` : "Run selected actions";
}

function saveEdits() {
  if (!state.data?.options.length) return;
  state.edits[option().pack.intent.id] = { subject: $("subject").value, body: $("bodyEditor").innerText };
}

function updateMailto() {
  const subj = encodeURIComponent($("subject").value);
  const body = encodeURIComponent($("bodyEditor").innerText);
  $("mailtoBtn").href = `mailto:${state.data.advisor.email}?subject=${subj}&body=${body}`;
}

async function regenerate(useFacts) {
  const p = option().pack;
  const body = { user_id: state.userId, intent_id: p.intent.id, tone: $("toneSelect").value };
  if (useFacts) body.included_fact_ids = [...document.querySelectorAll("#facts input:checked")].map((c) => c.dataset.f);
  else body.included_fact_ids = p.facts.filter((f) => f.included).map((f) => f.id);
  $("bodyEditor").classList.add("loading"); $("regenBtn").disabled = true;
  try {
    const opt = await api(`/api/outreach/${state.advisor}/regenerate`, { method: "POST", body: JSON.stringify(body) });
    state.data.options[state.active] = opt;
    delete state.edits[p.intent.id];
    renderOption();
    toast("Draft regenerated");
  } catch (e) { toast(`Could not regenerate: ${e.message}`); }
  finally { $("bodyEditor").classList.remove("loading"); $("regenBtn").disabled = false; }
}

// ------------------------------------------------------------------ admin actions with confirmation
function askConfirm() {
  if (!state.data?.options.length) return;
  const p = option().pack;
  const ids = selectedActions();
  if (!ids.length) { toast("Select at least one action"); return; }
  const acts = p.actions.filter((a) => ids.includes(a.id));
  $("cfSub").textContent = `${acts.length} action${acts.length === 1 ? "" : "s"} for ${state.data.advisor.name}. Nothing is sent to the advisor.`;
  $("cfList").innerHTML = acts.map((a) => `<li><b>${esc(a.label)}</b><div class="d">${esc(a.description)}</div></li>`).join("");
  $("confirm").hidden = false;
  $("cfOk").focus();
}

async function runActions() {
  if (!state.data?.options.length || $("cfOk").disabled) return;
  const p = option().pack;
  const ids = selectedActions();
  $("cfOk").disabled = true;
  $("cfOk").textContent = "Running…";
  try {
    const res = await api("/api/actions/execute", {
      method: "POST",
      body: JSON.stringify({ user_id: state.userId, advisor_id: state.advisor, intent_id: p.intent.id, action_ids: ids, confirmed: true }),
    });
    state.done[p.intent.id] = { ...(state.done[p.intent.id] || {}), ...Object.fromEntries(ids.map((i) => [i, true])) };
    $("actionResults").innerHTML += res.results.map((r) => `<li>✓ ${esc(r.message)}</li>`).join("");
    renderActions();
    toast(`${res.results.length} action${res.results.length === 1 ? "" : "s"} completed`);
    refreshLog();
  } catch (e) { toast(`Actions failed: ${e.message}`); }
  finally { $("confirm").hidden = true; $("cfOk").disabled = false; $("cfOk").textContent = "Confirm and run"; }
}

async function refreshLog() {
  const log = await api("/api/actions/log");
  $("logCard").hidden = !log.length;
  $("actionLog").innerHTML = log.slice().reverse().map((l) => `<li><span class="ref">${esc(l.ref)}</span><span>${esc(l.message)}</span><span class="muted small">${esc(l.advisor_id)}</span></li>`).join("");
}

// ------------------------------------------------------------------ wiring
$("closeComposer").addEventListener("click", closeComposer);
$("composer").addEventListener("click", (e) => { if (e.target.id === "composer") closeComposer(); });
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("confirm").hidden) $("confirm").hidden = true; else if (!$("composer").hidden) closeComposer();
});
$("subject").addEventListener("input", updateMailto);
$("bodyEditor").addEventListener("input", updateMailto);
$("regenBtn").addEventListener("click", () => regenerate(false));
$("toneSelect").addEventListener("change", () => regenerate(false));
$("applyFacts").addEventListener("click", () => regenerate(true));
$("copyBtn").addEventListener("click", async () => {
  const text = `Subject: ${$("subject").value}\n\n${$("bodyEditor").innerText}`;
  try { await navigator.clipboard.writeText(text); toast("Email copied to clipboard"); }
  catch { toast("Copy failed - select the text and copy manually"); }
});
$("runActions").addEventListener("click", askConfirm);
$("cfCancel").addEventListener("click", () => ($("confirm").hidden = true));
$("cfOk").addEventListener("click", runActions);

// Demo deep link: /?user=U101&open=A101[&tab=1] opens that advisor's email dialog directly.
async function deepLink() {
  const q = new URLSearchParams(location.search);
  if (q.get("user") && state.users.some((u) => u.user_id === q.get("user"))) {
    state.userId = q.get("user"); $("userSelect").value = state.userId; await loadAdvisors();
  }
  const id = q.get("open");
  if (!id) return;
  const rows = await api(`/api/advisors?user_id=${state.userId}&all_regions=true`);
  const r = rows.find((x) => x.advisor_id === id);
  if (!r) return;
  await openComposer({ id, name: r.name, firm: r.firm });
  const tab = +(q.get("tab") || 0);
  if (tab && state.data?.options[tab]) setTimeout(() => { state.active = tab; render(); }, 500);
}

init().then(refreshLog).then(deepLink).catch((e) => { $("advisorRows").innerHTML = `<tr><td colspan="6">Could not load: ${esc(e.message)}</td></tr>`; });
