"use strict";

const $ = (id) => document.getElementById(id);
const money = (n) => "$" + Math.round(Number(n) || 0).toLocaleString("en-US");
const money2 = (n) => "$" + (Number(n) || 0).toLocaleString("en-US", {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let selectedListingId = null;
let imageDataUrl = null;

/* ------------------------------------------------------------ map */
let map = null;
let markerLayer = null;
const markers = new Map();   // listing id -> leaflet marker

function ensureMap() {
  if (map) return map;
  map = L.map("map", { scrollWheelZoom: false, zoomControl: true })
    .setView([41.3083, -72.9279], 13);           // New Haven
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  markerLayer = L.layerGroup().addTo(map);
  return map;
}

function rankIcon(rank, overBudget, selected) {
  const cls = `rank-marker ${overBudget ? "over" : "good"}${selected ? " selected" : ""}`;
  return L.divIcon({
    className: "",
    html: `<div class="${cls}"><span>${rank}</span></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -26],
  });
}

function highlightMarker(id) {
  markers.forEach((entry, key) => {
    entry.marker.setIcon(rankIcon(entry.rank, entry.over, key === id));
  });
}

function drawMap(result) {
  ensureMap();
  markerLayer.clearLayers();
  markers.clear();

  const bounds = [];
  const d = result.destination;
  if (d) {
    L.marker([d.lat, d.lng], {
      icon: L.divIcon({ className: "", html: '<div class="dest-marker"></div>',
                        iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -12] }),
      zIndexOffset: 1000,
    }).addTo(markerLayer)
      .bindPopup(`<b>${esc(d.label)}</b><div class="pop-fig">where you need to get to</div>`);
    bounds.push([d.lat, d.lng]);
  }

  result.recommendations.forEach((x, i) => {
    if (x.lat == null || x.lng == null) return;
    const over = !x.within_budget;
    const marker = L.marker([x.lat, x.lng], { icon: rankIcon(i + 1, over, false) })
      .addTo(markerLayer)
      .bindPopup(
        `<b>${esc(x.address)}</b>` +
        `<div class="pop-fig"><strong>${money(x.real_monthly_usd)}</strong>/mo all in ` +
        `&middot; ad ${money(x.advertised_rent_usd)}</div>` +
        `<div class="pop-fig">${x.walk_minutes ?? "?"} min walk &middot; ` +
        `${x.fair_price_delta_pct === null ? "&mdash;" :
           (x.fair_price_delta_pct > 0 ? "+" : "") + x.fair_price_delta_pct + "% vs tract"}</div>`
      );
    marker.on("click", () => selectListing(x.listing_id));
    markers.set(x.listing_id, { marker, rank: i + 1, over });
    bounds.push([x.lat, x.lng]);
  });

  if (bounds.length) map.fitBounds(bounds, { padding: [34, 34], maxZoom: 15 });
  setTimeout(() => map.invalidateSize(), 60);
}

function selectListing(id) {
  selectedListingId = id;
  document.querySelectorAll(".rec-card").forEach((c) =>
    c.classList.toggle("selected", Number(c.dataset.id) === id));
  highlightMarker(id);
  const card = document.querySelector(`.rec-card[data-id="${id}"]`);
  if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const entry = markers.get(id);
  if (entry) entry.marker.openPopup();
}

/* ------------------------------------------------------------ setup */
async function loadStatus() {
  try {
    const r = await fetch("/api/status");
    const d = await r.json();
    const k = d.keys || {};
    const bits = [];

    if (k.has_portkey_key) {
      bits.push(`<span class="pill pill-ok">${esc(k.model)} ready</span>`);
    } else if (k.has_openai_key) {
      bits.push(`<span class="pill pill-ok">OpenAI key found</span>`);
    } else {
      bits.push(`<span class="pill pill-bad">no API key found</span>`);
    }

    if (d.dataset) {
      bits.push(`<span class="pill pill-accent">${d.dataset.listings} listings</span>`);
      bits.push(`<span class="pill pill-muted">${d.dataset.tracts} census tracts</span>`);
      $("footer-data").textContent =
        `${d.dataset.listings} listings captured ${d.dataset.listings_captured} from the Yale off-campus marketplace. ` +
        `Rent baseline: ACS ${d.dataset.acs_vintage}, ${d.dataset.tracts} tracts. ` +
        `New Haven median gross rent ${money(d.dataset.city_median_gross_rent)}, of which ` +
        `${money(d.dataset.city_implied_utilities)} is utilities.`;
    }
    $("status").innerHTML = bits.join("");

    if (!k.has_portkey_key && !k.has_openai_key) {
      showError(
        "No API key found.\n\nLooked in:\n" +
        (k.searched || []).map((p) => "  - " + p).join("\n") +
        "\n\nCopy .env.example to .env and set PORTKEY_API_KEY, or put the .env one folder above this repo."
      );
    }
  } catch (e) {
    $("status").innerHTML = `<span class="pill pill-bad">server unreachable</span>`;
  }
}

/* ------------------------------------------------------------ tabs */
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tabpane").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $("pane-" + tab.dataset.tab).classList.add("active");
  });
});

/* ------------------------------------------------------------ destinations */
async function loadDestinations() {
  try {
    const d = await (await fetch("/api/destinations")).json();
    $("destination-list").innerHTML = d.destinations
      .map((x) => `<option value="${esc(x.label)}">${esc(x.address)}</option>`).join("");
  } catch (e) { /* the box still accepts a typed address */ }
}

/* ------------------------------------------------------------ ranking */
async function rankListings() {
  const box = $("listing-list");
  const note = $("rank-note");
  box.innerHTML = `<p class="muted"><span class="spinner spinner-dark"></span>Ranking the snapshot&hellip;</p>`;
  note.textContent = "";

  const body = {
    destination: $("destination").value.trim(),
    profile: readProfile(),
    limit: 12,
  };
  if ($("f-rent").value) body.max_rent = Number($("f-rent").value);
  if ($("f-beds").value) body.min_bedrooms = Number($("f-beds").value);

  try {
    const r = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`);

    if (d.destination_error) {
      box.innerHTML = `<p class="muted">${esc(d.destination_error)}</p>`;
      return;
    }
    if (!d.recommendations.length) {
      box.innerHTML = `<p class="muted">Nothing in the snapshot matches those filters.</p>`;
      return;
    }

    const dest = d.destination;
    note.innerHTML =
      `Ranked <strong>${d.considered}</strong> listings against your constraints and ` +
      `<strong>${esc(dest.label)}</strong>` +
      (dest.resolved_by === "geocoder" && dest.matched_address
        ? ` <span class="muted">(matched ${esc(dest.matched_address)})</span>` : "") +
      ` &mdash; <strong>${d.model_calls} model calls</strong>, so this is free and instant. ` +
      `Open one to run the full analysis.`;

    box.innerHTML = d.recommendations.map((x, i) => {
      const over = x.real_monthly_usd - x.advertised_rent_usd;
      const beds = x.bedrooms_min === x.bedrooms_max
        ? `${x.bedrooms_min ?? "?"} bed`
        : `${x.bedrooms_min ?? "?"}&ndash;${x.bedrooms_max ?? "?"} bed`;
      return `<button class="rec-card${x.within_budget ? "" : " over"}" data-id="${x.listing_id}">
        <div class="rec-top">
          <span class="rec-rank">${i + 1}</span>
          <span class="rec-addr">${esc(x.address)}</span>
          ${x.rent_change_usd ? `<span class="rec-flag ${x.rent_change_usd < 0 ? "drop" : "rise"}">${
            x.rent_change_usd < 0 ? "&darr;" : "&uarr;"} ${money(Math.abs(x.rent_change_usd))}</span>` : ""}
          ${x.days_advertised !== null && x.days_advertised >= 30
            ? `<span class="rec-flag stale">${x.days_advertised}d listed</span>` : ""}
          <span class="rec-score" title="fit score">${x.score}</span>
        </div>
        <div class="rec-figures">
          <div><span class="k">Real monthly</span><span class="v">${money(x.real_monthly_usd)}</span>
            <span class="s">ad ${money(x.advertised_rent_usd)}${over > 0 ? ` &middot; +${money(over)} hidden` : ""}</span></div>
          <div><span class="k">First year</span><span class="v">${money(x.first_year_total_usd)}</span>
            <span class="s">${beds}</span></div>
          <div><span class="k">To your destination</span><span class="v">${x.walk_minutes ?? "?"} min</span>
            <span class="s">walk &middot; ${x.bike_minutes ?? "?"} min bike</span></div>
          <div><span class="k">Vs neighbourhood</span><span class="v ${x.fair_price_delta_pct > 0 ? "up" : "down"}">${
            x.fair_price_delta_pct === null ? "&mdash;"
            : (x.fair_price_delta_pct > 0 ? "+" : "") + x.fair_price_delta_pct + "%"}</span>
            <span class="s">census tract</span></div>
        </div>
        ${x.reasons.length ? `<ul class="rec-why">${x.reasons.map((s) =>
          `<li class="good">${esc(s)}</li>`).join("")}</ul>` : ""}
        ${x.warnings.length ? `<ul class="rec-why">${x.warnings.map((s) =>
          `<li class="bad">${esc(s)}</li>`).join("")}</ul>` : ""}
      </button>`;
    }).join("");

    drawMap(d);

    box.querySelectorAll(".rec-card").forEach((card) => {
      card.addEventListener("click", () => selectListing(Number(card.dataset.id)));
    });
  } catch (e) {
    box.innerHTML = `<p class="muted">Could not rank listings: ${esc(e.message)}</p>`;
  }
}
$("f-apply").addEventListener("click", rankListings);
$("destination").addEventListener("change", rankListings);

/* ------------------------------------------------------------ image */
$("ad-image").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    imageDataUrl = reader.result;
    $("image-preview").innerHTML = `<img src="${imageDataUrl}" alt="Uploaded listing screenshot">`;
  };
  reader.readAsDataURL(file);
});

/* ------------------------------------------------------------ run */
function readProfile() {
  return {
    monthly_budget_usd: Number($("budget").value) || null,
    arrival_month: $("arrival").value,
    household_size: Number($("household").value) || 1,
    max_walk_minutes: Number($("walk").value) || null,
    destination: $("destination").value.trim() || "Yale campus",
    is_international: $("intl").checked,
    has_car: $("car").checked,
    needs_in_unit_laundry: $("laundry").checked,
    needs_furnished: $("furnished").checked,
  };
}

function showError(msg) {
  $("error").hidden = false;
  $("error").textContent = msg;
}

$("run").addEventListener("click", async () => {
  const btn = $("run");
  const activeTab = document.querySelector(".tab.active").dataset.tab;
  const adText = $("ad-text").value.trim();

  const body = { profile: readProfile(), ad_text: "", listing_id: null, image_data_url: null };
  if (activeTab === "browse") {
    if (!selectedListingId) return showError("Pick a listing from the snapshot first.");
    body.listing_id = selectedListingId;
  } else if (activeTab === "paste") {
    if (!adText) return showError("Paste the advertisement text first.");
    body.ad_text = adText;
  } else {
    if (!imageDataUrl) return showError("Choose a screenshot first.");
    body.image_data_url = imageDataUrl;
    body.ad_text = adText;
  }

  $("error").hidden = true;
  $("results").hidden = true;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>Working it out&hellip;`;

  try {
    const r = await fetch("/api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `Request failed (${r.status})`);
    render(d);
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Work out the real cost";
  }
});

/* ------------------------------------------------------------ render */
function render(d) {
  const L = d.listing, c = d.cost, fp = d.fair_price, fit = d.fit, adv = d.advice;

  $("verdict-address").textContent = L.address || "This listing";
  const pill = $("verdict-pill");
  if (d.injection_blocked) {
    pill.className = "pill pill-bad";
    pill.textContent = "manipulation attempt blocked";
  } else if (fit && fit.score >= 70) {
    pill.className = "pill pill-ok";
    pill.textContent = `fit ${fit.score}/100`;
  } else {
    pill.className = "pill pill-accent";
    pill.textContent = `fit ${fit ? fit.score : "?"}/100`;
  }

  $("headline").textContent = adv ? adv.headline : "";
  $("n-advertised").textContent = money(c.monthly_rent_usd);
  $("n-real").textContent = money(c.monthly_total_usd);
  const diff = c.monthly_total_usd - c.monthly_rent_usd;
  $("n-real-sub").textContent = diff > 0
    ? `${money(diff)} more than advertised` : "per month";
  $("n-year").textContent = money(c.first_year_total_usd);
  if (c.upfront_is_floor) {
    $("n-upfront").innerHTML = `${money(c.upfront_cash_usd)}<span style="font-size:18px;color:var(--amber)">+</span>`;
    $("n-upfront-sub").textContent = "first month; deposit never stated";
  } else {
    $("n-upfront").textContent = money(c.upfront_cash_usd);
    $("n-upfront-sub").textContent =
      `first month + ${c.deposit_months} month deposit`;
  }

  const gap = $("gap-banner");
  if (c.gap_months > 0 && c.gap_explanation) {
    gap.hidden = false;
    gap.textContent = c.gap_explanation;
  } else gap.hidden = true;

  // ---- costs
  const measured = (b) => b === "stated" || b === "census_estimate";
  $("cost-table").innerHTML =
    `<tr><td class="label-cell"><i class="dot dot-measured"></i>
        <span>Rent as advertised<span class="src">stated in the listing</span></span></td>
      <td class="amount">${money2(c.monthly_rent_usd)}</td></tr>` +
    c.lines.map((l) => `<tr><td class="label-cell">
        <i class="dot ${measured(l.basis) ? "dot-measured" : "dot-assumed"}"></i>
        <span>${esc(l.label)}<span class="src">${esc(l.source)}</span></span></td>
      <td class="amount">${money2(l.monthly_usd)}</td></tr>`).join("") +
    `<tr class="total"><td>Real monthly cost</td>
      <td class="amount">${money2(c.monthly_total_usd)}</td></tr>`;

  $("assumptions").innerHTML =
    `<strong>Confidence: ${esc(c.confidence)}.</strong>` +
    (c.assumptions || []).map((a) => `<p>${esc(a)}</p>`).join("");

  // ---- fair price
  if (fp && fp.delta_pct !== null && fp.delta_pct !== undefined) {
    const cls = fp.verdict === "above_market" ? "above" : fp.verdict === "below_market" ? "below" : "at";
    const pct = Math.max(0, Math.min(100, 50 + fp.delta_pct));
    $("fairprice").innerHTML = `
      <div class="delta ${cls}">${fp.delta_pct > 0 ? "+" : ""}${fp.delta_pct}%</div>
      <div class="delta-sub">${esc(fp.verdict.replace("_", " "))} for this census tract</div>
      <div class="bar"><div class="fill" style="width:${pct}%"></div><div class="mid"></div></div>
      <div class="fp-rows">
        <div><span>This listing, utilities included</span><span>${money(fp.listing_gross_rent_usd)}</span></div>
        <div><span>Local baseline</span><span>${money(fp.baseline_used_usd)}</span></div>
        <div><span>Difference</span><span>${fp.delta_usd > 0 ? "+" : ""}${money(fp.delta_usd)}/mo</span></div>
        <div><span>Source</span><span>${esc(fp.baseline_source || "")}</span></div>
        ${fp.tract_name ? `<div><span>Tract</span><span>${esc(fp.tract_name.split(";")[0])}</span></div>` : ""}
      </div>
      ${fp.caveat ? `<p class="caveat">${esc(fp.caveat)}</p>` : ""}`;
  } else {
    $("fairprice").innerHTML = `<p class="muted">${esc((fp && fp.caveat) || "No comparison available.")}</p>`;
  }

  // ---- risk
  const findings = (d.risk && d.risk.findings) || [];
  const order = { illegal: 0, risky: 1, info: 2 };
  findings.sort((a, b) => order[a.severity] - order[b.severity]);
  $("risk-list").innerHTML = findings.length
    ? findings.map((f) => `<div class="finding ${f.severity}">
        <div class="finding-head">
          <span class="sev ${f.severity}">${esc(f.severity)}</span>
          <strong>${esc(f.title)}</strong>
          <span class="rule-id">${esc(f.rule_id)}</span>
        </div>
        <p>${esc(f.explanation)}</p>
        ${f.evidence ? `<div class="evidence">${esc(f.evidence)}</div>` : ""}
        ${f.what_to_do ? `<div class="todo">&rarr; ${esc(f.what_to_do)}</div>` : ""}
      </div>`).join("")
    : `<p class="no-findings">${esc((d.risk && d.risk.nothing_found_note) || "Nothing flagged.")}</p>`;

  // ---- fit
  if (fit) {
    $("fit").innerHTML = `
      <div class="fit-score"><span class="num">${fit.score}</span><span class="den">/ 100</span></div>
      <ul class="fit-list">
        ${fit.meets.map((m) => `<li><span class="tick">&#10003;</span><span>${esc(m)}</span></li>`).join("")}
        ${fit.fails.map((m) => `<li><span class="cross">&#10007;</span><span>${esc(m)}</span></li>`).join("")}
      </ul>
      ${fit.commute_note ? `<p class="note">${esc(fit.commute_note)}</p>` : ""}`;
  }

  // ---- unknowns
  $("unknowns").innerHTML =
    (L.unknown_fields || []).length
      ? `<div class="chips">${L.unknown_fields.map((u) =>
          `<span class="chip">${esc(u.replace(/_/g, " "))}</span>`).join("")}</div>`
        + (L.parser_notes ? `<p class="parser-note">${esc(L.parser_notes)}</p>` : "")
      : `<p class="muted">This advertisement states everything the app looks for. That is rare.</p>`;

  // ---- questions
  $("questions").innerHTML = ((adv && adv.viewing_questions) || []).map((q) =>
    `<li><div><strong>${esc(q.question)}</strong>
      <span class="why">${esc(q.why_it_matters)}</span>
      ${q.dollar_impact ? `<span class="impact">${esc(q.dollar_impact)}</span>` : ""}
    </div></li>`).join("");

  $("walkaway").innerHTML = (adv && adv.walk_away_if && adv.walk_away_if.length)
    ? `<div class="walkaway"><h3>Walk away if</h3><ul>${
        adv.walk_away_if.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>`
    : "";

  // ---- agent trace
  const fmtVal = (v) => Array.isArray(v)
    ? (v.length ? v.map((x) => `<code>${esc(x)}</code>`).join(" ") : "<em>none</em>")
    : (v === null || v === undefined || v === "" ? "<em>none</em>" : esc(v));

  $("trace").innerHTML = d.steps.map((s, i) => `
    <details class="trace-step"${i === 0 ? " open" : ""}>
      <summary>
        <span class="trace-n">${i + 1}</span>
        <span class="trace-name">${esc(s.agent)}</span>
        <span class="trace-sum">${esc(s.summary)}</span>
        <span class="trace-tools ${s.tools_available.length ? "has" : "none"}">${
          s.tools_available.length
            ? (s.tools_called.length ? `called ${esc(s.tools_called.join(", "))}` :
               `${s.tools_available.length} tool available`)
            : "no tools"}</span>
      </summary>
      <div class="trace-body">
        <div class="trace-meta">
          <span>tools available: ${fmtVal(s.tools_available)}</span>
          <span>tools called: ${fmtVal(s.tools_called)}</span>
          <span>${s.usage.total_tokens.toLocaleString()} tokens &middot; ${s.seconds}s &middot; $${s.usage.estimated_cost_usd.toFixed(6)}</span>
        </div>
        ${s.output_preview ? `<dl class="trace-out">${
          Object.entries(s.output_preview).map(([k, v]) =>
            `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${fmtVal(v)}</dd>`).join("")
        }</dl>` : ""}
      </div>
    </details>`).join("");

  // ---- usage
  const u = d.usage;
  $("usage-table").innerHTML =
    `<tr><th>Agent</th><th>Input</th><th>Cached</th><th>Output</th><th>Cost</th><th>Time</th></tr>` +
    d.steps.map((s) => `<tr>
      <td>${esc(s.agent)}<span class="agent-note">${esc(s.summary)}</span></td>
      <td>${s.usage.input_tokens.toLocaleString()}</td>
      <td>${s.usage.cached_input_tokens.toLocaleString()}</td>
      <td>${s.usage.output_tokens.toLocaleString()}</td>
      <td>$${s.usage.estimated_cost_usd.toFixed(6)}</td>
      <td>${s.seconds}s</td></tr>`).join("") +
    `<tr><td>Total &mdash; ${d.steps.length} model calls</td>
      <td>${u.input_tokens.toLocaleString()}</td>
      <td>${u.cached_input_tokens.toLocaleString()}</td>
      <td>${u.output_tokens.toLocaleString()}</td>
      <td>$${u.estimated_cost_usd.toFixed(6)}</td>
      <td>${d.seconds}s</td></tr>`;

  $("results").hidden = false;
  $("verdict-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

loadStatus();
loadDestinations().then(rankListings);
