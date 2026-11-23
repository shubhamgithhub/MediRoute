"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const patientData = (() => {
    try {
      const raw = window.sessionStorage.getItem("mediroute_patient_request");
      const parsed = raw ? JSON.parse(raw) : null;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
    } catch (error) {
      return null;
    }
  })();

  const routingResult = (() => {
    try {
      const raw = window.sessionStorage.getItem("mediroute_routing_result");
      const parsed = raw ? JSON.parse(raw) : null;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
    } catch (error) {
      return null;
    }
  })();

  const noDataState = document.querySelector("#no-data-state");
  const resultsContent = document.querySelector("#results-content");
  const setText = (selector, value) => {
    const element = document.querySelector(selector);
    if (element) element.textContent = value;
  };

  if (!patientData || !routingResult) {
    if (noDataState) noDataState.hidden = false;
    if (resultsContent) resultsContent.hidden = true;
    if (window.lucide) window.lucide.createIcons();
    return;
  }

  document.querySelector(".demo-results-badge")?.remove();
  document.querySelector(".demo-disclaimer")?.remove();
  // the medical-context card now shows the real Step 1 result (renderMedicalContext below)
  document.querySelector(".ranking-explanation")?.remove();
  document.querySelector(".important-notice")?.remove();

  const location = typeof patientData.location === "string" && patientData.location.trim()
    ? patientData.location.trim()
    : "No preference";
  setText("#summary-requirement", patientData.requirement?.trim() || "Not provided");
  setText("#summary-location", location);
  setText("#summary-language", patientData.language?.trim() || "Not specified");
  setText("#summary-report", Array.isArray(patientData.reportName)
    ? (patientData.reportName.join(", ") || "Not uploaded")
    : "Not uploaded");
  setText("#summary-preference", patientData.additionalPreference?.trim() || "None provided");
  const unreadable = routingResult.parse_summary?.unreadable_files || [];
  if (unreadable.length) {
    const note = document.createElement("p");
    note.className = "llm-notice report-notice";
    note.setAttribute("role", "status");
    note.textContent = `Not used (could not be read): ${unreadable.map((f) => `${f.filename}: ${f.reason}`).join(" · ")}`;
    document.querySelector(".request-facts")?.after(note);
  }

  const hospitalList = document.querySelector("#hospital-list");
  const recommendationSection = document.querySelector(".hospital-results-section");
  const toolbar = document.querySelector(".recommendation-toolbar");
  const sortSelect = document.querySelector("#sort-select");
  if (sortSelect?.closest("label")) sortSelect.closest("label").hidden = true;

  const splitValues = (value) => {
    if (Array.isArray(value)) return value.filter((item) => typeof item === "string" && item.trim());
    if (typeof value === "string" && value.trim()) {
      return value.split(/[,;|]/).map((item) => item.trim()).filter(Boolean);
    }
    return [];
  };

  const isPositiveStatus = (value) => {
    const text = typeof value === "string" ? value.toLowerCase() : "";
    return text.includes("accredited") || text.includes("certified") || text.includes("yes") || text.includes("verified");
  };

  // STEP 1 RESULT: suggested speciality from the routing result (step1 block)
  const renderMedicalContext = () => {
    const createIconSafe = (name) => {
      const icon = document.createElement("i");
      icon.setAttribute("data-lucide", name);
      icon.setAttribute("aria-hidden", "true");
      return icon;
    };
    const step1 = routingResult.step1 || {};
    const specialty = typeof step1.suggested_specialty === "string" && step1.suggested_specialty.trim()
      ? step1.suggested_specialty.trim()
      : "Not determined";
    const careCategory = typeof step1.care_category === "string" && step1.care_category.trim()
      ? step1.care_category.trim()
      : "—";
    setText("#context-specialty", "");
    setText("#context-care-category", "");
    const specialtyElement = document.querySelector("#context-specialty");
    if (specialtyElement) {
      specialtyElement.append(createIconSafe("heart-pulse"), ` ${specialty}`);
    }
    const careCategoryElement = document.querySelector("#context-care-category");
    if (careCategoryElement) {
      careCategoryElement.append(createIconSafe("stethoscope"), ` ${careCategory}`);
    }
    // emergency / crisis notice first, above the request and the hospital list (it was only on the patient page)
    if (step1.emergency && step1.emergency_message && !document.querySelector("#emergency-banner")) {
      const banner = document.createElement("div");
      banner.id = "emergency-banner";
      banner.className = "emergency-banner";
      banner.setAttribute("role", "alert");
      const message = document.createElement("p");
      message.textContent = step1.emergency_message;
      banner.append(createIconSafe("siren"), message);
      document.querySelector("#results-content")?.prepend(banner);
    }
    if (step1.notice && !document.querySelector("#llm-notice")) {
      const notice = document.createElement("p");
      notice.id = "llm-notice";
      notice.className = "llm-notice";
      notice.append(createIconSafe("info"), ` ${step1.notice}`);
      document.querySelector(".request-facts")?.after(notice);
    }
    const location = typeof patientData.location === "string" && patientData.location.trim()
      ? patientData.location.trim()
      : "No preference";
    setText("#context-location", location);
    if (window.lucide) {
      window.lucide.createIcons();
    }
  };
  renderMedicalContext();

  const toCard = (hospital, index) => ({
        id: String(hospital.hospital_id || `hospital-${index + 1}`),
        name: hospital.hospital_name || "Hospital name unavailable",
        city: hospital.city || "City unavailable",
        state: hospital.state || "",
        // verified on the hospital's website first, then specialities only the team sheet lists
        specialties: [...new Set([...splitValues(hospital.verified_specialties).filter((s) => s !== "NA"),
                                  ...splitValues(hospital.team_claimed_specialties)])],
        procedures: splitValues(hospital.procedures || hospital.verified_procedures),
        detailSource: hospital.detail_source || "",
        internationalPatientService: hospital.international_patient_service || "",
        costBand: hospital.cost_band_inr || "",
        nabhStatus: hospital.nabh_status || "",
        jciStatus: hospital.jci_status || "",
        website: hospital.official_source_url || "",
        rankingReasons: Array.isArray(hospital.ranking_reasons)
          ? hospital.ranking_reasons.filter((reason) => typeof reason === "string")
          : [],
        semanticScore: hospital.semantic_score,
        finalScore: hospital.final_score,
        rank: Number.isInteger(hospital.final_rank) ? hospital.final_rank : index + 1,
        outsideArea: hospital.outside_area === true,
        matchedProcedures: Array.isArray(hospital.matched_procedures) ? hospital.matched_procedures : [],
        areaGroup: hospital.area_group || "",
        relatedSpecialty: hospital.related_specialty || ""
      });
  const recommendation = routingResult.recommendation_result || {};
  const hospitals = recommendation.status === "success" ? (recommendation.results || []).map(toCard) : [];
  // in the patient's area, a related speciality (only when no hospital there has the suggested one)
  const relatedHospitals = recommendation.status === "success" ? (recommendation.related_results || []).map(toCard) : [];

  const MAX_CHIPS = 6;
  // treatments the patient named (Step 1 evidence); used to say when a hospital's list lacks them
  const askedProcedures = (routingResult.step1?.evidence_detail?.procedures || []).filter(Boolean);
  const searchedSpecialty = String(routingResult.recommendation_result?.primary_specialty
    || routingResult.step1?.suggested_specialty || "").trim();

  const createElement = (tagName, className, text) => {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };

  const createIcon = (name) => {
    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", name);
    icon.setAttribute("aria-hidden", "true");
    return icon;
  };

  const createInfoRow = (label, value) => {
    const row = createElement("div", "routing-info-row");
    row.append(createElement("span", "", label), createElement("strong", "", value || "Not specified in the hospital record"));
    return row;
  };

  const createHospitalCard = (hospital, index) => {
    const card = createElement("article", "hospital-card");
    card.dataset.hospitalId = hospital.id;

    // header band: rank, name, place (one clear block per hospital)
    const head = createElement("header", "hospital-head");
    head.append(createElement("span", "rank-badge", `#${hospital.rank || index + 1}`));
    const title = createElement("div", "hospital-title");
    title.append(createElement("h3", "hospital-name", hospital.name),
                 createElement("p", "hospital-location", `${hospital.city}${hospital.state ? `, ${hospital.state}` : ""}`));
    head.append(title);
    const badges = createElement("div", "hospital-badges");
    if (isPositiveStatus(hospital.nabhStatus)) badges.append(createElement("span", "acc-badge", "NABH"));
    if (isPositiveStatus(hospital.jciStatus)) badges.append(createElement("span", "acc-badge", "JCI"));
    head.append(badges);
    card.append(head);

    // left: specialities (searched one first) and why this hospital
    const main = createElement("div", "hospital-main");
    if (hospital.specialties.length) {
      main.append(createElement("h4", "", "Specialities"));
      const specialties = createElement("div", "hospital-specialties");
      const wanted = (hospital.relatedSpecialty || searchedSpecialty).toLowerCase();
      const ordered = [...hospital.specialties].sort((a, b) =>
        (b.toLowerCase() === wanted) - (a.toLowerCase() === wanted));
      ordered.slice(0, MAX_CHIPS).forEach((specialty) => specialties.append(
        createElement("span", specialty.toLowerCase() === wanted ? "is-match" : "", specialty)));
      if (ordered.length > MAX_CHIPS) {
        const more = createElement("span", "chip-more", `+${ordered.length - MAX_CHIPS} more`);
        more.title = ordered.slice(MAX_CHIPS).join(", ");
        specialties.append(more);
      }
      main.append(specialties);
    }
    if (hospital.rankingReasons.length) {
      main.append(createElement("h4", "", "Why this hospital"));
      const reasons = createElement("ul", "relevance-list");
      hospital.rankingReasons.forEach((reason) => {
        const item = createElement("li");
        item.append(createIcon("check"), document.createTextNode(reason));
        reasons.append(item);
      });
      main.append(reasons);
    }

    // right: treatments (the patient's own first), services, accreditation, website. No cost for now.
    const extra = createElement("div", "hospital-extra");
    if (hospital.procedures.length || askedProcedures.length) {
      const matched = new Set(hospital.matchedProcedures.map((p) => p.toLowerCase()));
      const ordered = [...hospital.procedures].sort((a, b) =>
        matched.has(b.toLowerCase()) - matched.has(a.toLowerCase()));
      const unverified = hospital.detailSource ? " (team list, not verified)" : "";
      // the patient named a treatment that this hospital's list does not contain: say so first, so the
      // rest of the list is not read as related to the request
      const missing = askedProcedures.length && !matched.size;
      if (missing) {
        const note = createElement("p", "treatment-missing");
        note.append(createIcon("info"), document.createTextNode(
          ordered.length ? ` No “${askedProcedures[0]}” in this hospital's treatment list. Please ask the hospital.`
                         : ` No treatment list for this hospital yet. Please ask them about “${askedProcedures[0]}”.`));
        extra.append(createElement("h4", "", "Your treatment"), note);
      }
      if (ordered.length) extra.append(createElement("h4", "", (missing ? "Other treatments listed" : "Treatments & procedures") + unverified));
      const chips = createElement("div", "hospital-treatments");
      ordered.slice(0, 8).forEach((name) => chips.append(createElement("span", matched.has(name.toLowerCase()) ? "is-match" : "", name)));
      if (ordered.length > 8) {
        const more = createElement("span", "chip-more", `+${ordered.length - 8} more`);
        more.title = ordered.slice(8).join(", ");
        chips.append(more);
      }
      if (ordered.length) extra.append(chips);
    }
    extra.append(createElement("h4", "details-heading", "Hospital details"));
    extra.append(createInfoRow("International patient service", hospital.internationalPatientService));
    extra.append(createInfoRow("NABH", hospital.nabhStatus));
    extra.append(createInfoRow("JCI", hospital.jciStatus));
    if (hospital.website) {
      const link = createElement("a", "official-hospital-link", "Visit official hospital website");
      link.href = hospital.website;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      extra.append(link);
    }
    card.append(main, extra);

    const actions = createElement("div", "hospital-actions");
    const detailsButton = createElement("button", "button button-primary details-button", "Select and proceed with this hospital ");
    detailsButton.type = "button";
    detailsButton.append(createIcon("arrow-right"));
    detailsButton.addEventListener("click", () => {
      try {
        window.sessionStorage.setItem("mediroute_selected_hospital", hospital.id);
        window.location.href = "hospital.html";
      } catch (error) {
        card.querySelector(".hospital-card-message").textContent = "The hospital selection could not be saved. Please enable session storage and try again.";
      }
    });
    const message = createElement("p", "hospital-card-message");
    message.setAttribute("role", "status");
    actions.append(detailsButton);
    card.append(actions, message);
    return card;
  };

  const showClarification = () => {
    if (toolbar) toolbar.hidden = true;
    hospitalList?.replaceChildren();
    if (!recommendationSection) return;

    const type = String(routingResult.clarification_type || "").toLowerCase();
    const reason = routingResult.clarification_reason || "More information is needed before MediRoute can recommend hospitals.";
    const parseStatus = String(routingResult.parse_summary?.overall_status || "").toLowerCase();
    const card = createElement("section", "clarification-card");
    card.setAttribute("role", "alert");
    const noHospital = type === "no_hospital";
    card.append(createElement("span", "section-kicker", noHospital ? "No verified hospital yet" : "Additional information needed"));
    card.append(createElement("h2", "", noHospital ? "We could not list hospitals for this speciality" : "MediRoute needs your help"));

    let friendlyReason = reason;
    let actionText = "";
    if (noHospital) {
      // Step 1 found the speciality, but Step 2 has no verified hospital for it in our data yet
      friendlyReason = reason;
      actionText = "You can search for this speciality directly, or change your request or preferred city.";
    } else if (parseStatus === "needs_ocr") {
      friendlyReason = "The uploaded PDF was blank, unreadable, or did not contain readable report text. Upload a clearer PDF with readable text and try again.";
      actionText = "Upload a different or clearer PDF.";
    } else if (/missing|no valid medical pdf|no pdf|no report/i.test(reason) || type === "report" && /no valid/i.test(reason)) {
      if (/missing|no pdf|no report/i.test(reason)) {
        friendlyReason = "No medical report was provided. Upload a PDF or describe the treatment requirement, then review and submit again.";
        actionText = "Upload a different or clearer medical report.";
      } else {
        friendlyReason = "The uploaded PDF was blank or unreadable. Upload a clearer PDF so MediRoute can read the report.";
        actionText = "Upload a different PDF.";
      }
    } else if (/specialty|specialties|conflict|multiple/i.test(reason) || type.includes("specialty")) {
      friendlyReason = `${reason} Please identify the patient’s primary treatment priority; the reports do not make a single specialty selection automatic.`;
      actionText = "Review the reports and state the primary treatment priority in the healthcare requirement.";
    } else if (/location|no matching|no location/i.test(reason) || type.includes("location")) {
      friendlyReason = `${reason} Try a broader location preference or return to patient input to change the selected city.`;
      actionText = "Review or change the location preference.";
    } else if (type.includes("unreadable") || /readable|ocr/i.test(reason)) {
      friendlyReason = "The report could not be read. Upload a clearer PDF and try again.";
      actionText = "Upload a different or clearer PDF.";
    }

    card.append(createElement("p", "clarification-reason", friendlyReason));
    if (actionText) card.append(createElement("p", "clarification-action", actionText));

    const actions = createElement("div", "clarification-actions");
    const upload = createElement("a", "button button-primary", "Upload or Change Information");
    upload.href = "patient.html?edit=1";
    const home = createElement("a", "button button-secondary", "Review Hospital Search Input");
    home.href = "patient.html?edit=1";
    actions.append(upload, home);
    card.append(actions);
    recommendationSection.insertBefore(card, hospitalList);
  };

  if (routingResult.workflow_status === "waiting_for_clarification" || routingResult.clarification_required) {
    showClarification();
  } else if (hospitals.length > 0) {
    const inArea = hospitals.filter((hospital) => !hospital.outsideArea).length;
    setText("#result-count", inArea < hospitals.length
      ? `· ${inArea} in ${location}, ${hospitals.length - inArea} outside`
      : `· ${hospitals.length} found`);
    hospitalList.replaceChildren();
    if (inArea === 0 && relatedHospitals.length) {
      const related = relatedHospitals[0].relatedSpecialty;
      setText("#result-count", `· ${relatedHospitals.length} in ${location} (related speciality), ${hospitals.length} outside`);
      hospitalList.append(createElement("p", "area-note",
        `No hospital in ${location} lists ${searchedSpecialty || "this speciality"} in our data. First, hospitals in ${location} `
        + `with ${related}, a related department (${recommendation.related_why || "it often gives the same care"}). `
        + `Please confirm with the hospital that it offers your treatment. Below them: hospitals that list ${searchedSpecialty || "this speciality"}, outside your area.`));
      const divider = createElement("div", "area-divider");
      divider.append(createElement("h3", "", `In ${location} · related speciality: ${related}`));
      hospitalList.append(divider);
      relatedHospitals.forEach((hospital, index) => {
        const card = createHospitalCard(hospital, index);
        card.classList.add("is-related");
        hospitalList.append(card);
      });
    } else if (inArea === 0) {
      hospitalList.append(createElement("p", "area-note",
        `No hospital in ${location} offers ${searchedSpecialty || "this speciality"} in our data. These are the closest options we have.`));
    }
    let lastGroup = "";
    hospitals.forEach((hospital, index) => {
      if (hospital.outsideArea && hospital.areaGroup !== lastGroup) {
        const divider = createElement("div", "area-divider");
        divider.append(createElement("h3", "", `Outside your area · ${hospital.areaGroup}`));
        if (lastGroup === "" && inArea > 0) {
          divider.append(createElement("p", "",
            `Only ${inArea} hospital${inArea === 1 ? "" : "s"} in ${location} offer${inArea === 1 ? "s" : ""} ${searchedSpecialty || "this speciality"} in our data, so we also show these.`));
        }
        hospitalList.append(divider);
        lastGroup = hospital.areaGroup;
      }
      const card = createHospitalCard(hospital, index);
      if (hospital.outsideArea) card.classList.add("is-outside-area");
      hospitalList.append(card);
    });
  } else {
    if (toolbar) toolbar.hidden = true;
    const card = createElement("section", "clarification-card");
    card.append(createElement("h2", "", "No hospital recommendations are available"));
    card.append(createElement("p", "", "Routing was not ready and no hospital list can be displayed. Return to the patient form to review the information."));
    const actions = createElement("a", "button button-primary", "Return to Patient Input");
    actions.href = "patient.html";
    card.append(actions);
    recommendationSection.insertBefore(card, hospitalList);
  }

  if (window.lucide) window.lucide.createIcons();
});
