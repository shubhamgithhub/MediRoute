"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const splitValues = (value) => {
    if (Array.isArray(value)) return value.filter((item) => typeof item === "string" && item.trim());
    if (typeof value === "string" && value.trim()) return value.split(/[,;|]/).map((item) => item.trim()).filter(Boolean);
    return [];
  };
  const isPositiveStatus = (value) => {
    const text = typeof value === "string" ? value.toLowerCase() : "";
    return text.includes("accredited") || text.includes("certified") || text.includes("yes") || text.includes("verified");
  };
  let hospitals = [];
  try {
    const raw = window.sessionStorage.getItem("mediroute_routing_result");
    const routing = raw ? JSON.parse(raw) : null;
    const records = routing?.recommendation_result?.status === "success" ? routing.recommendation_result.results || [] : [];
    hospitals = records.map((hospital, index) => ({
      id: String(hospital.hospital_id || `hospital-${index + 1}`),
      name: hospital.hospital_name || "Hospital name unavailable",
      city: hospital.city || "City unavailable",
      state: hospital.state || "",
      accreditation: [
        isPositiveStatus(hospital.nabh_status) ? "NABH status positive" : "",
        isPositiveStatus(hospital.jci_status) ? "JCI status positive" : ""
      ].filter(Boolean).join(", ") || "Accreditation not specified in record",
      hospitalType: "Hospital record",
      patientServices: hospital.international_patient_service || "Not specified in hospital record",
      specialties: [...new Set([...splitValues(hospital.verified_specialties).filter((s) => s !== "NA"),
                                ...splitValues(hospital.team_claimed_specialties)])],
      facilities: splitValues(hospital.facilities || hospital.procedures || hospital.verified_procedures),
      medicalFit: 0,
      locationScore: 0,
      facilitiesScore: 0,
      overallScore: typeof hospital.final_score === "number" ? hospital.final_score : 0,
      reasons: Array.isArray(hospital.ranking_reasons) ? hospital.ranking_reasons : ["Backend hospital ranking result"],
      referenceCost: hospital.cost_band_inr || "Cost band not specified",
      website: hospital.official_source_url || "",
      rank: Number.isInteger(hospital.final_rank) ? hospital.final_rank : index + 1
    }));
  } catch (error) {
    hospitals = [];
  }


  const errorState = document.querySelector("#hospital-error-state");
  const hospitalContent = document.querySelector("#hospital-content");
  const patientMatchSection = document.querySelector("#patient-match-section");
  const hospitalActionMessage = document.querySelector("#hospital-action-message");
  const selectHospitalButton = document.querySelector("#select-hospital-button");

  // SESSION STORAGE
  const getStoredValue = (key) => {
    try {
      return window.sessionStorage.getItem(key);
    } catch (error) {
      console.error(`Unable to read ${key} from session storage.`, error);
      return null;
    }
  };

  // SELECTED HOSPITAL
  const getSelectedHospitalId = () => getStoredValue("mediroute_selected_hospital");

  const getHospital = (hospitalId) => hospitals.find((hospital) => hospital.id === hospitalId) || null;

  // PATIENT DATA
  const getPatientData = () => {
    const stored = getStoredValue("mediroute_patient_request");
    if (!stored) {
      return null;
    }
    try {
      const patientData = JSON.parse(stored);
      return patientData && typeof patientData === "object" && !Array.isArray(patientData)
        ? patientData
        : null;
    } catch (error) {
      console.error("Unable to parse MediRoute patient information.", error);
      return null;
    }
  };

  const patientData = getPatientData();
  const selectedHospital = getHospital(getSelectedHospitalId());

  if (!selectedHospital) {
    // ERROR HANDLING
    errorState.hidden = false;
    hospitalContent.hidden = true;
    if (window.lucide) {
      window.lucide.createIcons();
    }
    return;
  }

  const setText = (selector, value) => {
    const element = document.querySelector(selector);
    if (element) {
      element.textContent = value;
    }
  };

  const createElement = (tagName, className, text) => {
    const element = document.createElement(tagName);
    if (className) {
      element.className = className;
    }
    if (text !== undefined) {
      element.textContent = text;
    }
    return element;
  };

  const createIcon = (name) => {
    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", name);
    icon.setAttribute("aria-hidden", "true");
    return icon;
  };

  const setAnimatedBar = (bar, score) => {
    bar.style.setProperty("--match-width", `${score}%`);
    requestAnimationFrame(() => bar.classList.add("is-animated"));
  };

  // HOSPITAL HERO
  const getRecommendationRank = (hospital) => {
    const sorted = [...hospitals].sort((first, second) => second.overallScore - first.overallScore);
    return sorted.findIndex((item) => item.id === hospital.id) + 1;
  };

  const renderHospitalHero = (hospital) => {
    setText("#hospital-rank", `Recommendation #${getRecommendationRank(hospital)}`);
    setText("#hospital-name", hospital.name);
    setText("#hospital-location", `${hospital.city}, ${hospital.state}`);
    setText("#hero-score", typeof hospital.overallScore === "number" ? String(hospital.overallScore) : "N/A");
    setText("#about-hospital-name", hospital.name);
    setText("#about-hospital-type", hospital.hospitalType);
    setText("#about-location", `${hospital.city}, ${hospital.state}`);
    setText("#about-accreditation", hospital.accreditation);
    setText("#about-type", hospital.hospitalType);
    setText("#about-services", hospital.patientServices);
    setText("#reference-cost", hospital.referenceCost);
    setText("#flow-hospital-name", hospital.name);

    const heroBadges = document.querySelector("#hero-badges");
    const accreditationBadge = createElement("span", "");
    accreditationBadge.append(createIcon("badge-check"), document.createTextNode(hospital.accreditation));
    heroBadges.append(accreditationBadge);
    hospital.specialties.forEach((specialty) => {
      const badge = createElement("span", "");
      badge.append(createIcon("stethoscope"), document.createTextNode(specialty));
      heroBadges.append(badge);
    });
    if (hospital.website) {
      const website = createElement("a", "");
      website.href = hospital.website;
      website.target = "_blank";
      website.rel = "noopener noreferrer";
      website.append(createIcon("external-link"), document.createTextNode("Official website"));
      heroBadges.append(website);
    }
  };

  // MATCH EXPLANATION
  const renderMatchExplanation = (hospital) => {
    const scoreGrid = document.querySelector("#match-score-grid");
    const card = createElement("div", "match-score-card");
    card.append(
      createElement("span", "", "Development ranking score"),
      createElement("strong", "", typeof hospital.overallScore === "number" ? String(hospital.overallScore) : "N/A")
    );
    scoreGrid.append(card);

    const reasons = document.querySelector("#match-reasons");
    hospital.reasons.forEach((reason) => {
      const item = createElement("li", "");
      item.append(createIcon("check"), document.createTextNode(reason));
      reasons.append(item);
    });
  };

  const renderPatientMatch = (hospital, data) => {
    if (!data) {
      patientMatchSection.hidden = true;
      const unavailable = createElement("p", "patient-info-unavailable", "Patient requirement information is unavailable.");
      document.querySelector(".match-section").after(unavailable);
      return;
    }

    setText("#patient-requirement", typeof data.requirement === "string" && data.requirement.trim() ? data.requirement.trim() : "Not provided");
    setText("#patient-location", typeof data.location === "string" && data.location.trim() ? data.location.trim() : "No preference");
    setText("#patient-preference", typeof data.additionalPreference === "string" && data.additionalPreference.trim() ? data.additionalPreference.trim() : "None provided");

    const relevantTags = document.querySelector("#relevant-info-tags");
    [...hospital.specialties, ...hospital.facilities].forEach((name) => {
      const tag = createElement("span", "");
      tag.append(createIcon("check"), document.createTextNode(name));
      relevantTags.append(tag);
    });
  };

  // SPECIALTIES
  const renderSpecialties = (hospital) => {
    const container = document.querySelector("#specialties-grid");
    if (hospital.specialties.length === 0) {
      container.append(createElement("p", "", "Verified specialties are not specified in the hospital record."));
      return;
    }
    hospital.specialties.forEach((specialty) => {
      const card = createElement("article", "specialty-card is-relevant");
      const icon = createElement("span", "small-card-icon");
      icon.append(createIcon("stethoscope"));
      const copy = createElement("span", "");
      copy.append(createElement("strong", "", specialty));
      copy.append(createElement("small", "", "Listed in the hospital record"));
      card.append(icon, copy);
      container.append(card);
    });
  };

  // FACILITIES
  const renderFacilities = (hospital) => {
    const container = document.querySelector("#facilities-grid");
    if (hospital.facilities.length === 0) {
      container.append(createElement("p", "", "Verified procedures are not specified in the hospital record."));
      return;
    }
    hospital.facilities.forEach((facilityName) => {
      const card = createElement("article", "facility-card is-included");
      const icon = createElement("span", "small-card-icon");
      icon.append(createIcon("hospital"));
      const copy = createElement("span", "");
      copy.append(createElement("strong", "", facilityName));
      copy.append(createElement("small", "", "Listed as a verified procedure"));
      card.append(icon, copy);
      container.append(card);
    });
  };

  // COST INFORMATION
  // Cost values are fictional examples and are explicitly labeled as non-quotations in the page.

  // RANKING
  const renderRanking = (hospital) => {
    setText("#calculation-medical-fit", String(hospital.overallScore));
    setText("#calculation-location", "Backend");
    setText("#calculation-facilities", "ranking result");
  };

  const renderTransparencyFlow = (data, hospital) => {
    const requirement = typeof data?.requirement === "string" && data.requirement.trim()
      ? data.requirement.trim()
      : "Cardiac treatment";
    setText("#flow-requirement", requirement);
  };

  // ACTIONS
  const handleHospitalSelection = () => {
    hospitalActionMessage.textContent = "Hospital enquiry functionality will be added in a later MediRoute development stage.";
  };
  selectHospitalButton.addEventListener("click", handleHospitalSelection);

  // ERROR HANDLING
  const renderHospital = (hospital, data) => {
    errorState.hidden = true;
    hospitalContent.hidden = false;
    renderHospitalHero(hospital);
    renderMatchExplanation(hospital);
    renderPatientMatch(hospital, data);
    renderSpecialties(hospital);
    renderFacilities(hospital);
    renderRanking(hospital);
    renderTransparencyFlow(data, hospital);
    if (window.lucide) {
      window.lucide.createIcons();
    }
  };

  renderHospital(selectedHospital, patientData);
});
