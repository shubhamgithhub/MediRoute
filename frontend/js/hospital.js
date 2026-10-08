"use strict";

document.addEventListener("DOMContentLoaded", () => {
  // DEMO HOSPITAL DATA
  const hospitals = [
    {
      id: "DEMO001",
      name: "Example Multispecialty Hospital",
      city: "Mumbai",
      state: "Maharashtra",
      accreditation: "NABH Accredited",
      hospitalType: "Multispecialty Hospital",
      patientServices: "International Patient Support — Demo",
      specialties: ["Cardiology", "Cardiac Surgery", "Internal Medicine"],
      facilities: ["Cardiac ICU", "Cath Lab", "Emergency Cardiac Care", "Intensive Care Unit", "Diagnostic Imaging", "24/7 Emergency Department"],
      medicalFit: 96,
      locationScore: 92,
      facilitiesScore: 88,
      overallScore: 94,
      reasons: [
        "Relevant cardiology and cardiac surgery services",
        "Matches your preferred treatment location",
        "Relevant cardiac care facilities"
      ],
      referenceCost: "₹2,00,000 – ₹3,50,000"
    },
    {
      id: "DEMO002",
      name: "Example Heart Institute",
      city: "Mumbai",
      state: "Maharashtra",
      accreditation: "NABH Accredited",
      hospitalType: "Cardiac Specialty Hospital",
      patientServices: "International Patient Support — Demo",
      specialties: ["Cardiology"],
      facilities: ["Cardiac ICU", "Diagnostic Cardiology"],
      medicalFit: 91,
      locationScore: 92,
      facilitiesScore: 85,
      overallScore: 89,
      reasons: [
        "Relevant cardiology specialization",
        "Matches your preferred treatment location",
        "Relevant diagnostic facilities"
      ],
      referenceCost: "₹1,80,000 – ₹3,20,000"
    },
    {
      id: "DEMO003",
      name: "Example Medical Centre",
      city: "Pune",
      state: "Maharashtra",
      accreditation: "NABH Accredited",
      hospitalType: "Multispecialty Hospital",
      patientServices: "International Patient Support — Demo",
      specialties: ["Cardiology", "Internal Medicine"],
      facilities: ["ICU", "Cardiology Unit"],
      medicalFit: 87,
      locationScore: 65,
      facilitiesScore: 86,
      overallScore: 82,
      reasons: [
        "Relevant cardiology services",
        "Relevant hospital facilities",
        "Located outside the preferred city"
      ],
      referenceCost: "₹1,70,000 – ₹3,00,000"
    }
  ];

  const facilityCatalog = [
    { name: "Cardiac ICU", icon: "heart-pulse", detail: "Cardiac intensive care — demo" },
    { name: "Cath Lab", icon: "activity", detail: "Cardiac diagnostics — demo" },
    { name: "Emergency Cardiac Care", icon: "heart-handshake", detail: "Emergency service — demo" },
    { name: "Intensive Care Unit", icon: "bed", detail: "Critical care — demo" },
    { name: "Diagnostic Imaging", icon: "scan-line", detail: "Imaging services — demo" },
    { name: "24/7 Emergency Department", icon: "siren", detail: "Emergency department — demo" }
  ];

  const specialtyCatalog = [
    { name: "Cardiology", icon: "heart-pulse", detail: "Heart and circulatory care" },
    { name: "Cardiac Surgery", icon: "heart-plus", detail: "Cardiac surgical services" },
    { name: "Internal Medicine", icon: "stethoscope", detail: "Adult general medical care" }
  ];

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
    setText("#hero-score", `${hospital.overallScore}%`);
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
  };

  // MATCH EXPLANATION
  const renderMatchExplanation = (hospital) => {
    const matchScores = [
      ["Medical Fit", hospital.medicalFit],
      ["Location Match", hospital.locationScore],
      ["Facilities Match", hospital.facilitiesScore]
    ];
    const scoreGrid = document.querySelector("#match-score-grid");
    matchScores.forEach(([label, score]) => {
      const card = createElement("div", "match-score-card");
      const topline = createElement("div", "match-score-topline");
      topline.append(createElement("span", "", label), createElement("strong", "", `${score}%`));
      const track = createElement("div", "match-bar-track");
      track.setAttribute("role", "img");
      track.setAttribute("aria-label", `${label}: ${score}% illustrative match`);
      const bar = createElement("span");
      setAnimatedBar(bar, score);
      track.append(bar);
      card.append(topline, track);
      scoreGrid.append(card);
    });

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
    specialtyCatalog.forEach((specialty) => {
      const isRelevant = hospital.specialties.includes(specialty.name);
      const card = createElement("article", `specialty-card${isRelevant ? " is-relevant" : ""}`);
      const icon = createElement("span", "small-card-icon");
      icon.append(createIcon(specialty.icon));
      const copy = createElement("span", "");
      copy.append(createElement("strong", "", specialty.name));
      copy.append(createElement("small", "", isRelevant ? "Included in this demo profile" : specialty.detail));
      card.append(icon, copy);
      container.append(card);
    });
  };

  // FACILITIES
  const renderFacilities = (hospital) => {
    const container = document.querySelector("#facilities-grid");
    const facilityData = [
      ...hospital.facilities.map((name) => facilityCatalog.find((facility) => facility.name === name) || {
        name,
        icon: "hospital",
        detail: "Illustrative hospital service"
      }),
      ...facilityCatalog.filter((facility) => !hospital.facilities.includes(facility.name))
    ];

    facilityData.forEach((facility) => {
      const included = hospital.facilities.includes(facility.name);
      const card = createElement("article", `facility-card${included ? " is-included" : ""}`);
      const icon = createElement("span", "small-card-icon");
      icon.append(createIcon(facility.icon));
      const copy = createElement("span", "");
      copy.append(createElement("strong", "", facility.name));
      copy.append(createElement("small", "", included ? "Included in this demo profile" : "Illustrative facility example"));
      card.append(icon, copy);
      container.append(card);
    });
  };

  // COST INFORMATION
  // Cost values are fictional examples and are explicitly labeled as non-quotations in the page.

  // RANKING
  const renderRanking = (hospital) => {
    setText("#calculation-medical-fit", String(hospital.medicalFit));
    setText("#calculation-location", String(hospital.locationScore));
    setText("#calculation-facilities", String(hospital.facilitiesScore));
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
