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
      specialties: ["Cardiology", "Cardiac Surgery", "Internal Medicine"],
      medicalFit: 96,
      locationScore: 92,
      facilitiesScore: 88,
      overallScore: 94,
      facilities: ["Cardiac ICU", "Cath Lab", "Emergency Cardiac Care", "Intensive Care Unit", "Diagnostic Imaging", "24/7 Emergency Department"],
      reasons: [
        "Relevant cardiology and cardiac surgery services",
        "Matches preferred treatment location",
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
      specialties: ["Cardiology"],
      medicalFit: 91,
      locationScore: 92,
      facilitiesScore: 85,
      overallScore: 89,
      facilities: ["Cardiac ICU", "Diagnostic Cardiology"],
      reasons: [
        "Relevant cardiology specialization",
        "Matches preferred location",
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
      specialties: ["Cardiology", "Internal Medicine"],
      medicalFit: 87,
      locationScore: 65,
      facilitiesScore: 86,
      overallScore: 82,
      facilities: ["ICU", "Cardiology Unit"],
      reasons: [
        "Relevant cardiology services",
        "Relevant hospital facilities",
        "Located outside the preferred city"
      ],
      referenceCost: "₹1,70,000 – ₹3,00,000"
    }
  ];

  // SESSION STORAGE
  const getPatientData = () => {
    try {
      const stored = window.sessionStorage.getItem("mediroute_patient_request");
      if (!stored) {
        return null;
      }
      const patientData = JSON.parse(stored);
      if (!patientData || typeof patientData !== "object" || Array.isArray(patientData)) {
        return null;
      }
      return patientData;
    } catch (error) {
      console.error("Unable to read MediRoute patient information from session storage.", error);
      return null;
    }
  };

  const patientData = getPatientData();
  const noDataState = document.querySelector("#no-data-state");
  const resultsContent = document.querySelector("#results-content");
  if (!patientData) {
    noDataState.hidden = false;
    resultsContent.hidden = true;
    if (window.lucide) {
      window.lucide.createIcons();
    }
    return;
  }

  const selectedHospitalIds = new Set();
  let currentSort = "overallScore";
  const hospitalList = document.querySelector("#hospital-list");
  const sortSelect = document.querySelector("#sort-select");
  const selectionMessage = document.querySelector("#selection-message");
  const comparisonBar = document.querySelector("#comparison-bar");
  const comparisonMessage = document.querySelector("#comparison-message");

  const setText = (selector, value) => {
    const element = document.querySelector(selector);
    if (element) {
      element.textContent = value;
    }
  };

  const displayReportNames = (names) => {
    const normalizedNames = Array.isArray(names) ? names : (typeof names === "string" && names ? [names] : []);
    return normalizedNames.length ? normalizedNames.join(", ") : "Not uploaded";
  };

  // PATIENT SUMMARY
  const renderPatientSummary = () => {
    const location = typeof patientData.location === "string" && patientData.location.trim()
      ? patientData.location.trim()
      : "No preference";
    setText("#summary-requirement", typeof patientData.requirement === "string" && patientData.requirement.trim() ? patientData.requirement.trim() : "Not provided");
    setText("#summary-location", location);
    setText("#summary-language", typeof patientData.language === "string" && patientData.language.trim() ? patientData.language.trim() : "Not specified");
    setText("#summary-report", displayReportNames(patientData.reportName));
    setText("#summary-preference", typeof patientData.additionalPreference === "string" && patientData.additionalPreference.trim() ? patientData.additionalPreference.trim() : "None provided");
    setText("#context-location", location);
  };

  // HOSPITAL RENDERING
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

  const createIcon = (name, className = "") => {
    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", name);
    icon.setAttribute("aria-hidden", "true");
    if (className) {
      icon.className = className;
    }
    return icon;
  };

  const createHospitalCard = (hospital, index) => {
    const card = createElement("article", "hospital-card");
    card.dataset.hospitalId = hospital.id;
    card.classList.toggle("is-selected", selectedHospitalIds.has(hospital.id));
    card.style.animationDelay = `${Math.min(index, 5) * 65}ms`;

    const main = createElement("div", "hospital-main");
    const topline = createElement("div", "hospital-topline");
    topline.append(createElement("span", "rank-badge", `#${index + 1}`), createElement("span", "rank-caption", "Demo recommendation"));
    const name = createElement("h3", "hospital-name", hospital.name);
    const location = createElement("p", "hospital-location");
    location.append(createIcon("map-pin"), document.createTextNode(`${hospital.city}, ${hospital.state}`));
    const accreditation = createElement("span", "accreditation-badge");
    accreditation.append(createIcon("badge-check"), document.createTextNode(hospital.accreditation));
    const specialties = createElement("div", "hospital-specialties");
    specialties.setAttribute("aria-label", "Specialties");
    hospital.specialties.forEach((specialty) => specialties.append(createElement("span", "", specialty)));
    main.append(topline, name, location, accreditation, specialties);

    const scores = createElement("div", "hospital-scores");
    const scoreHeader = createElement("div", "score-header");
    scoreHeader.append(createElement("h4", "", "Match factors"));
    const overall = createElement("div", "overall-score");
    overall.append(createElement("strong", "", `${hospital.overallScore}%`), createElement("span", "", "Overall Match"));
    scoreHeader.append(overall);
    scores.append(scoreHeader);
    [
      ["Medical Fit", hospital.medicalFit],
      ["Location", hospital.locationScore],
      ["Facilities", hospital.facilitiesScore]
    ].forEach(([label, score]) => {
      const row = createElement("div", "score-row");
      row.append(createElement("span", "", label));
      const track = createElement("div", "score-track");
      track.setAttribute("aria-label", `${label}: ${score}%`);
      const bar = createElement("span");
      bar.style.setProperty("--score-width", `${score}%`);
      track.append(bar);
      row.append(track, createElement("strong", "", `${score}%`));
      scores.append(row);
    });

    const extra = createElement("div", "hospital-extra");
    extra.append(createElement("h4", "", "Why this hospital may be relevant"));
    const reasons = createElement("ul", "relevance-list");
    hospital.reasons.forEach((reason) => {
      const item = createElement("li");
      item.append(createIcon("check"), document.createTextNode(reason));
      reasons.append(item);
    });
    extra.append(reasons);
    const facilities = createElement("div", "hospital-facilities");
    facilities.setAttribute("aria-label", "Facilities");
    hospital.facilities.forEach((facility) => facilities.append(createElement("span", "", facility)));
    extra.append(facilities);
    const referenceCost = createElement("div", "reference-cost");
    referenceCost.append(
      createElement("span", "", "Reference Cost"),
      createElement("strong", "", hospital.referenceCost),
      createElement("small", "", "Illustrative reference only — not a live hospital quotation.")
    );
    extra.append(referenceCost);

    const actions = createElement("div", "hospital-actions");
    const detailsButton = createElement("button", "button button-primary details-button");
    detailsButton.type = "button";
    detailsButton.append(document.createTextNode("View Hospital Details "), createIcon("arrow-right"));
    detailsButton.addEventListener("click", () => showDetailsMessage(hospital.id, card));
    const compareLabel = createElement("label", "compare-label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedHospitalIds.has(hospital.id);
    checkbox.disabled = !checkbox.checked && selectedHospitalIds.size >= 2;
    checkbox.setAttribute("aria-label", `Compare ${hospital.name}`);
    checkbox.addEventListener("change", () => selectHospital(hospital, checkbox.checked));
    compareLabel.append(checkbox, document.createTextNode("Compare"));
    actions.append(detailsButton, compareLabel);
    const message = createElement("p", "hospital-card-message");
    message.setAttribute("role", "status");
    message.setAttribute("aria-live", "polite");

    card.append(main, scores, extra, actions, message);
    return card;
  };

  const renderHospitals = (hospitalData = hospitals) => {
    hospitalList.replaceChildren();
    hospitalData.forEach((hospital, index) => {
      hospitalList.append(createHospitalCard(hospital, index));
    });
    setText("#result-count", `${hospitalData.length} hospitals found`);
    requestAnimationFrame(() => {
      hospitalList.querySelectorAll(".score-track span").forEach((bar) => bar.classList.add("is-animated"));
    });
    if (window.lucide) {
      window.lucide.createIcons();
    }
  };

  // SCORE BARS
  // Bars animate after each render to keep the score labels readable with motion disabled as well.

  // SORTING
  const sortHospitals = () => {
    currentSort = sortSelect.value;
    const sortedHospitals = [...hospitals].sort((first, second) => second[currentSort] - first[currentSort]);
    renderHospitals(sortedHospitals);
  };
  sortSelect.addEventListener("change", sortHospitals);

  // HOSPITAL SELECTION
  const selectHospital = (hospital, isSelected) => {
    if (isSelected && selectedHospitalIds.size >= 2) {
      selectionMessage.textContent = "You can compare up to 2 hospitals at a time.";
      renderHospitals([...hospitals].sort((first, second) => second[currentSort] - first[currentSort]));
      return;
    }
    if (isSelected) {
      selectedHospitalIds.add(hospital.id);
    } else {
      selectedHospitalIds.delete(hospital.id);
      comparisonMessage.textContent = "";
    }
    selectionMessage.textContent = selectedHospitalIds.size >= 2 ? "You have selected the maximum of 2 hospitals." : "";
    updateComparison();
    renderHospitals([...hospitals].sort((first, second) => second[currentSort] - first[currentSort]));
  };

  const showDetailsMessage = (hospitalId, card) => {
    const message = card.querySelector(".hospital-card-message");
    try {
      window.sessionStorage.setItem("mediroute_selected_hospital", hospitalId);
      window.location.href = "hospital.html";
    } catch (error) {
      console.error("Unable to save the selected MediRoute hospital.", error);
      message.textContent = "Your browser could not save this selection. Please check session storage and try again.";
    }
  };

  // COMPARISON
  const updateComparison = () => {
    const count = selectedHospitalIds.size;
    comparisonBar.hidden = count !== 2;
    setText("#compare-count", `${count} hospitals selected`);
    hospitalList.querySelectorAll(".compare-label input").forEach((checkbox) => {
      checkbox.disabled = !checkbox.checked && count >= 2;
    });
  };

  document.querySelector("#compare-button").addEventListener("click", () => {
    comparisonMessage.textContent = "Hospital comparison will be implemented later.";
  });

  // ERROR STATE
  renderPatientSummary();
  renderHospitals([...hospitals].sort((first, second) => second[currentSort] - first[currentSort]));
});
