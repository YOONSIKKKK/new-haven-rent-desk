"use strict";

const $ = (id) => document.getElementById(id);
const money = (n) => "$" + Math.round(Number(n) || 0).toLocaleString("en-US");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const TOKEN_KEY = "rentdesk.admin.token";
let filter = "pending";
let serviceLabels = {};

function token() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
}

function headers() {
  const t = token();
  return t ? { "Content-Type": "application/json", "X-Admin-Token": t }
           : { "Content-Type": "application/json" };
}

async function loadServiceLabels() {
  try {
    const d = await (await fetch("/api/viewers")).json();
    (d.service_types || []).forEach((t) => { serviceLabels[t.code] = t.label; });
  } catch (e) { /* codes will show instead of labels */ }
}

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString();
}

function card(a) {
  const status = a.status || "pending";
  const v = a.verified || {};
  return `<article class="adm-card adm-${esc(status)}" data-id="${esc(a.id)}">
    <div class="adm-top">
      <div>
        <span class="adm-name">${esc(a.name)}</span>
        <span class="adm-pill adm-pill-${esc(status)}">${esc(status)}</span>
        <span class="adm-id">${esc(a.id)}</span>
      </div>
      <span class="adm-when">submitted ${esc(when(a.submitted_at))}</span>
    </div>

    <p class="adm-headline">${esc(a.headline)}</p>
    <p class="adm-about">${esc(a.about)}</p>

    <dl class="adm-facts">
      <dt>Contact</dt><dd><strong>${esc(a.contact || "not given")}</strong></dd>
      <dt>Based in</dt><dd>${esc(a.based_in)} &middot; ${a.years_in_new_haven} year(s) in New Haven</dd>
      <dt>Languages</dt><dd>${(a.languages || []).map(esc).join(", ")}</dd>
      ${a.affiliation ? `<dt>Affiliation</dt><dd>${esc(a.affiliation)}</dd>` : ""}
      ${a.availability ? `<dt>Available</dt><dd>${esc(a.availability)}</dd>` : ""}
      <dt>Replies</dt><dd>${esc(a.responds_in || "not stated")}</dd>
      <dt>Services</dt><dd>${(a.services || []).map((s) =>
        `${esc(serviceLabels[s.code] || s.code)} &mdash; <strong>${money(s.price_usd)}</strong>` +
        (s.duration ? ` (${esc(s.duration)})` : "")).join("<br>")}</dd>
    </dl>

    ${a.reviewed_at ? `<p class="adm-reviewed">Reviewed ${esc(when(a.reviewed_at))}${
      a.review_note ? ` &mdash; ${esc(a.review_note)}` : ""}</p>` : ""}

    <div class="adm-verify">
      <span class="adm-verify-label">Tick only what you actually checked:</span>
      <label class="check"><input type="checkbox" data-v="identity" ${v.identity ? "checked" : ""}><span>Identity</span></label>
      <label class="check"><input type="checkbox" data-v="yale_email" ${v.yale_email ? "checked" : ""}><span>Yale email</span></label>
      <label class="check"><input type="checkbox" data-v="background_check" ${v.background_check ? "checked" : ""}><span>Background check</span></label>
    </div>

    <div class="adm-actions">
      <input class="adm-note" placeholder="Note for the record (optional)"
             maxlength="300" value="${esc(a.review_note || "")}">
      <button class="btn btn-ghost adm-reject">Reject</button>
      <button class="btn btn-primary adm-approve">Approve</button>
    </div>
    <p class="adm-error" hidden></p>
  </article>`;
}

async function decide(el, status) {
  const id = el.dataset.id;
  const err = el.querySelector(".adm-error");
  const body = {
    status,
    note: el.querySelector(".adm-note").value.trim(),
    identity: el.querySelector('[data-v="identity"]').checked,
    yale_email: el.querySelector('[data-v="yale_email"]').checked,
    background_check: el.querySelector('[data-v="background_check"]').checked,
  };
  el.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  try {
    const r = await fetch(`/api/admin/applications/${encodeURIComponent(id)}`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `Failed (${r.status})`);
    await load();
  } catch (e) {
    err.hidden = false;
    err.textContent = e.message;
    el.querySelectorAll("button").forEach((b) => { b.disabled = false; });
  }
}

function renderTabs(counts) {
  const tabs = [
    ["pending", `Pending ${counts.pending || 0}`],
    ["approved", `Approved ${counts.approved || 0}`],
    ["rejected", `Rejected ${counts.rejected || 0}`],
    ["all", `All ${counts.total || 0}`],
  ];
  $("admin-tabs").innerHTML = tabs.map(([k, label]) =>
    `<button class="tab${filter === k ? " active" : ""}" data-f="${k}">${esc(label)}</button>`).join("");
  $("admin-tabs").querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => { filter = t.dataset.f; load(); }));
}

async function load() {
  try {
    const r = await fetch("/api/admin/applications", { headers: headers() });
    if (r.status === 401) {
      const d = await r.json();
      $("admin-list").innerHTML =
        `<div class="adm-auth">
           <p>${esc(d.detail)}</p>
           <label>Admin token<input type="password" id="tok"></label>
           <button class="btn btn-primary" id="tok-save">Unlock</button>
         </div>`;
      $("tok-save").addEventListener("click", () => {
        try { localStorage.setItem(TOKEN_KEY, $("tok").value.trim()); } catch (e) {}
        load();
      });
      return;
    }
    const d = await r.json();

    $("admin-status").innerHTML = d.protected
      ? `<span class="pill pill-ok">token required</span>`
      : `<span class="pill pill-bad">no token set</span>`;
    const warn = $("admin-warn");
    warn.hidden = d.protected;
    if (!d.protected) {
      warn.innerHTML =
        `<strong>This screen has no authentication.</strong> That is fine while the app
         runs on localhost, and not fine anywhere else. Set <code>ADMIN_TOKEN</code> in
         your <code>.env</code> before exposing this app on a network.`;
    }

    renderTabs(d.counts);
    const rows = filter === "all"
      ? d.applications
      : d.applications.filter((a) => (a.status || "pending") === filter);

    if (!rows.length) {
      const nothingAtAll = (d.counts.total || 0) === 0;
      $("admin-list").innerHTML = nothingAtAll
        ? `<div class="adm-empty">
             <p><strong>The queue is empty, and that is the expected state.</strong>
             Nobody has submitted a profile yet, so there is nothing to review.</p>
             <p class="muted">The screen itself is working: it reached the server and
             got back a count of zero. Submissions are stored in
             <code>${esc(d.store_path || "output/viewer_applications.json")}</code>, which
             is created on the first one.</p>
             <a class="btn btn-primary" href="/?list-yourself=1">Submit a test profile</a>
           </div>`
        : `<p class="muted">Nothing is ${esc(filter)} right now. Try another tab.</p>`;
      return;
    }

    $("admin-list").innerHTML = rows.map(card).join("");
    $("admin-list").querySelectorAll(".adm-card").forEach((el) => {
      el.querySelector(".adm-approve").addEventListener("click", () => decide(el, "approved"));
      el.querySelector(".adm-reject").addEventListener("click", () => decide(el, "rejected"));
    });
  } catch (e) {
    $("admin-list").innerHTML = `<p class="muted">Could not load: ${esc(e.message)}</p>`;
  }
}

loadServiceLabels().then(load);
