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
    if (step1.notice && !document.querySelector("#llm-notice")) {
      const notice = document.createElement("p");
      notice.id = "llm-notice";
      notice.className = "llm-notice";
      notice.append(createIconSafe("info"), ` ${step1.notice}`);
      document.querySelector(".context-values")?.after(notice);
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

  const hospitals = routingResult.recommendation_result?.status === "success"
    ? (routingResult.recommendation_result.results || []).map((hospital, index) => ({
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
        rank: Number.isInteger(hospital.final_rank) ? hospital.final_rank : index + 1
      }))
    : [];

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

    const main = createElement("div", "hospital-main");
    const rankCaption = `Backend rank #${hospital.rank || index + 1}`;
    main.append(
      createElement("span", "rank-badge", rankCaption),
      createElement("h3", "hospital-name", hospital.name),
      createElement("p", "hospital-location", `${hospital.city}${hospital.state ? `, ${hospital.state}` : ""}`)
    );

    if (hospital.specialties.length) {
      const specialties = createElement("div", "hospital-specialties");
      hospital.specialties.forEach((specialty) => specialties.append(createElement("span", "", specialty)));
      main.append(specialties);
    }

    const accreditation = [];
    if (isPositiveStatus(hospital.nabhStatus)) accreditation.push("NABH status: positive in hospital record");
    if (isPositiveStatus(hospital.jciStatus)) accreditation.push("JCI status: positive in hospital record");
    if (accreditation.length) main.append(createElement("p", "accreditation-badge", accreditation.join(" • ")));

    const extra = createElement("div", "hospital-extra");
    if (hospital.procedures.length) {
      const label = hospital.detailSource ? "Procedures (team list, not verified)" : "Relevant procedures";
      extra.append(createInfoRow(label, hospital.procedures.join(", ")));
    }
    extra.append(createInfoRow("International patient service", hospital.internationalPatientService));
    extra.append(createInfoRow("Cost band", hospital.costBand));
    extra.append(createInfoRow("NABH status", hospital.nabhStatus));
    extra.append(createInfoRow("JCI status", hospital.jciStatus));

    if (hospital.rankingReasons.length) {
      extra.append(createElement("h4", "", "Why the backend ranked this hospital"));
      const reasons = createElement("ul", "relevance-list");
      hospital.rankingReasons.forEach((reason) => {
        const item = createElement("li");
        item.append(createIcon("check"), document.createTextNode(reason));
        reasons.append(item);
      });
      extra.append(reasons);
    }

    if (typeof hospital.semanticScore === "number" || typeof hospital.finalScore === "number") {
      const labels = [];
      if (typeof hospital.semanticScore === "number") labels.push(`Semantic development score: ${hospital.semanticScore}`);
      if (typeof hospital.finalScore === "number") labels.push(`Final development score: ${hospital.finalScore}`);
      extra.append(createElement("p", "development-score-note", labels.join(" • ") + " — not a probability of treatment success."));
    }

    if (hospital.website) {
      const link = createElement("a", "official-hospital-link", "Visit official hospital website");
      link.href = hospital.website;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      extra.append(link);
    }

    const actions = createElement("div", "hospital-actions");
    const detailsButton = createElement("button", "button button-primary details-button", "View Hospital Details ");
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
    card.append(main, extra, actions, message);
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
    upload.href = "patient.html";
    const home = createElement("a", "button button-secondary", "Review Hospital Search Input");
    home.href = "patient.html";
    actions.append(upload, home);
    card.append(actions);
    recommendationSection.insertBefore(card, hospitalList);
  };

  if (routingResult.workflow_status === "waiting_for_clarification" || routingResult.clarification_required) {
    showClarification();
  } else if (hospitals.length > 0) {
    setText("#result-count", `${hospitals.length} hospitals found`);
    hospitalList.replaceChildren();
    hospitals.forEach((hospital, index) => hospitalList.append(createHospitalCard(hospital, index)));
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
