"use strict";

// Hospital page: header, four at-a-glance tiles and tabs (no long scrolling). Everything comes from
// the routing result kept in sessionStorage by the patient page; nothing is fetched here.
document.addEventListener("DOMContentLoaded", () => {
  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const icon = (name) => {
    const i = document.createElement("i");
    i.setAttribute("data-lucide", name);
    i.setAttribute("aria-hidden", "true");
    return i;
  };
  const split = (value) => (typeof value === "string" ? value.split(/[;|]/) : Array.isArray(value) ? value : [])
    .map((x) => String(x).trim()).filter((x) => x && x.toUpperCase() !== "NA");
  const positive = (value) => /accredited|certified|^yes|^verified|available/i.test(String(value || "")) &&
    !/not |partially/i.test(String(value || ""));
  const read = (key) => { try { return JSON.parse(window.sessionStorage.getItem(key) || "null"); } catch (e) { return null; } };

  const routing = read("mediroute_routing_result");
  const request = read("mediroute_patient_request") || {};
  let selectedId = null;
  try { selectedId = window.sessionStorage.getItem("mediroute_selected_hospital"); } catch (e) { selectedId = null; }
  const records = routing?.recommendation_result?.status === "success"
    ? [...(routing.recommendation_result.related_results || []), ...(routing.recommendation_result.results || [])] : [];
  const h = records.find((r) => String(r.hospital_id) === String(selectedId)) || null;

  if (!h) {
    $("#hospital-error-state").hidden = false;
    if (window.lucide) window.lucide.createIcons();
    return;
  }
  $("#hospital-content").hidden = false;
  document.title = `${h.hospital_name} | MediRoute`;

  const wanted = String(h.related_specialty || routing.recommendation_result.primary_specialty || routing.step1?.suggested_specialty || "").trim();
  const website = split(h.verified_specialties);
  const team = split(h.team_claimed_specialties);
  const evidence = h.specialty_evidence || (website.includes(wanted) ? "website" : team.includes(wanted) ? "team list" : "");
  const procedures = split(h.procedures);
  const matched = new Set((h.matched_procedures || []).map((x) => x.toLowerCase()));

  // ---------------------------------------------------------------- header
  $("#hospital-rank").textContent = `#${h.final_rank || 1}`;
  $("#hospital-name").textContent = h.hospital_name;
  $("#hospital-location").textContent = [h.city, h.state].filter(Boolean).join(", ");
  if (h.related_specialty) {
    $("#hospital-outside").hidden = false;
    $("#hospital-outside").textContent = `Related speciality · ${h.related_specialty} (please confirm your treatment with the hospital)`;
  } else if (h.outside_area) {
    $("#hospital-outside").hidden = false;
    $("#hospital-outside").textContent = `Outside your area · ${h.area_group || ""}`;
  }
  const badges = $("#hero-badges");
  if (positive(h.nabh_status)) badges.append(el("span", "hp-badge", "NABH accredited"));
  if (positive(h.jci_status)) badges.append(el("span", "hp-badge", "JCI accredited"));
  if (h.verification_status) badges.append(el("span", "hp-badge hp-badge-soft", h.verification_status));
  const site = $("#hospital-website");
  if (h.official_source_url) site.href = h.official_source_url; else site.hidden = true;

  // ---------------------------------------------------------------- tiles
  const tiles = $("#hp-tiles");
  const tile = (iconName, label, value, note, state) => {
    const t = el("article", `hp-tile is-${state}`);
    const top = el("div", "hp-tile-top");
    top.append(el("span", "hp-tile-icon"), el("span", "hp-tile-label", label));
    top.firstChild.append(icon(iconName));
    t.append(top, el("strong", "hp-tile-value", value), el("small", "hp-tile-note", note));
    tiles.append(t);
  };
  tile("stethoscope", "Your speciality", wanted || "—",
       evidence === "website" ? "Confirmed on the hospital's website" : evidence === "team list" ? "Team list only, not verified" : "Not listed",
       evidence === "website" ? "good" : evidence ? "warn" : "neutral");
  // Three different situations, each said plainly:
  //   your message names no treatment / the hospital has no treatment list / its list does not include it
  const firstMatch = procedures.find((p) => matched.has(p.toLowerCase()));
  const asked = (routing.step1?.evidence_detail?.procedures || []).filter(Boolean);
  let tValue, tNote, tState;
  if (firstMatch) {
    [tValue, tNote, tState] = [firstMatch, h.detail_source ? "Listed (team list, not verified)" : "Listed by the hospital", "good"];
  } else if (!asked.length) {
    [tValue, tNote, tState] = ["No treatment named", "Your message names no procedure, so the search is by speciality", "neutral"];
  } else if (!procedures.length) {
    [tValue, tNote, tState] = ["No treatment list yet", `We have no procedure list for this hospital. Ask them about ${asked[0]}`, "neutral"];
  } else {
    [tValue, tNote, tState] = ["Not in their list", `Their list is short and unverified. Ask them about ${asked[0]}`, "warn"];
  }
  tile("activity", "Your treatment", tValue, tNote, tState);
  const acc = [positive(h.nabh_status) && "NABH", positive(h.jci_status) && "JCI"].filter(Boolean);
  tile("badge-check", "Accreditation", acc.length ? acc.join(" + ") : "None listed",
       acc.length ? "Checked in the NABH / JCI directories" : "Not found in NABH / JCI directories", acc.length ? "good" : "neutral");
  const intl = positive(h.international_patient_service);
  tile("globe", "International patients", intl ? "Available" : "Not found",
       intl ? "Service mentioned on the website" : "Not mentioned on the website", intl ? "good" : "neutral");

  // ---------------------------------------------------------------- why this hospital
  const reasons = $("#match-reasons");
  (h.ranking_reasons || []).forEach((reason) => {
    const card = el("div", "hp-reason");
    card.append(icon("check-circle-2"), el("span", "", reason));
    reasons.append(card);
  });
  if (!reasons.children.length) reasons.append(el("p", "hp-note", "No ranking reasons were returned for this hospital."));

  // ---------------------------------------------------------------- specialities
  const specs = [...new Set([...website, ...team])].sort((a, b) => (b === wanted) - (a === wanted));
  const specGrid = $("#specialties-grid");
  specs.forEach((name) => {
    const chip = el("span", `hp-chip ${website.includes(name) ? "is-web" : "is-team"}${name === wanted ? " is-match" : ""}`, name);
    chip.title = website.includes(name) ? "Found on the hospital's own website" : "Listed by the team sheet only (not verified)";
    specGrid.append(chip);
  });
  $("#count-spec").textContent = specs.length;

  // ---------------------------------------------------------------- treatments
  const treat = [...procedures].sort((a, b) => matched.has(b.toLowerCase()) - matched.has(a.toLowerCase()));
  const treatGrid = $("#facilities-grid");
  treat.forEach((name) => treatGrid.append(el("span", `hp-chip${matched.has(name.toLowerCase()) ? " is-match" : ""}`, name)));
  split(h.facilities).forEach((name) => treatGrid.append(el("span", "hp-chip is-facility", name)));
  $("#count-treat").textContent = treat.length || "";
  $("#treat-note").textContent = treat.length
    ? `${h.detail_source ? "From the team's hospital sheet (not verified). " : ""}Highlighted: matches your request. Please confirm with the hospital.`
    : "No treatment list is available for this hospital yet. Please ask the hospital directly.";

  // ---------------------------------------------------------------- your request
  $("#patient-requirement").textContent = request.requirement || "Not provided";
  $("#patient-speciality").textContent = wanted || "—";
  $("#patient-location").textContent = request.location || "No preference";

  // ---------------------------------------------------------------- data & verification
  const data = $("#hp-data");
  const row = (label, value, ok) => {
    const card = el("div", `hp-data-row${ok === true ? " is-good" : ok === false ? " is-warn" : ""}`);
    card.append(el("span", "", label), el("strong", "", value || "Not available"));
    data.append(card);
  };
  row("Overall verification", h.verification_status, /^verified/i.test(h.verification_status || ""));
  row("NABH", h.nabh_status, positive(h.nabh_status));
  row("JCI", h.jci_status, positive(h.jci_status));
  row("Speciality evidence", evidence === "website" ? "Hospital's own website" : evidence === "team list" ? "Team sheet only" : "—",
      evidence === "website");
  row("Treatment list", h.detail_source ? "Team sheet (not verified)" : procedures.length ? "Hospital record" : "Not available",
      h.detail_source ? false : undefined);
  row("Official website", h.official_source_url ? new URL(h.official_source_url).hostname : "", Boolean(h.official_source_url));

  // ---------------------------------------------------------------- select this hospital + next steps
  const selectBtn = $("#select-hospital-button");
  const next = $("#hp-next");
  $("#hp-next-name").textContent = h.hospital_name;
  const nextSite = $("#hp-next-website");
  if (h.official_source_url) nextSite.href = h.official_source_url; else nextSite.hidden = true;
  if (h.url_Internantional_patients) {
    $("#hp-intl-wrap").hidden = false;
    $("#hp-intl-link").href = h.url_Internantional_patients;
  }
  const chosenKey = "mediroute_chosen_hospital";
  const setSelected = (on) => {
    selectBtn.classList.toggle("is-selected", on);
    selectBtn.setAttribute("aria-pressed", String(on));
    selectBtn.querySelector("span").textContent = on ? "Selected" : "Select this hospital";
    next.hidden = !on;
    try { if (on) window.sessionStorage.setItem(chosenKey, String(h.hospital_id)); else window.sessionStorage.removeItem(chosenKey); } catch (e) { /* not remembered */ }
  };
  let alreadyChosen = false;
  try { alreadyChosen = window.sessionStorage.getItem(chosenKey) === String(h.hospital_id); } catch (e) { alreadyChosen = false; }
  setSelected(alreadyChosen);
  selectBtn.addEventListener("click", () => {
    setSelected(true);
    next.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  $("#hp-unselect").addEventListener("click", () => setSelected(false));
  $("#hp-copy").addEventListener("click", async () => {
    const summary = [
      `Hospital: ${h.hospital_name}, ${[h.city, h.state].filter(Boolean).join(", ")}`,
      `My request: ${request.requirement || "-"}`,
      `Suggested speciality to search: ${wanted || "-"}`,
      `Preferred location: ${request.location || "No preference"}`,
      "(Prepared with MediRoute, an academic hospital-discovery project; not medical advice.)",
    ].join("\n");
    const label = $("#hp-copy span");
    try {
      await navigator.clipboard.writeText(summary);
      label.textContent = "Copied";
    } catch (e) {
      window.prompt("Copy this summary:", summary);
    }
    setTimeout(() => { label.textContent = "Copy summary"; }, 2000);
  });

  // ---------------------------------------------------------------- tabs (click + arrow keys)
  const tabs = [...document.querySelectorAll(".hp-tab")];
  const show = (tab) => {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => show(tab));
    tab.addEventListener("keydown", (event) => {
      const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      const next = tabs[(i + step + tabs.length) % tabs.length];
      next.focus();
      show(next);
    });
  });

  if (window.lucide) window.lucide.createIcons();
});
