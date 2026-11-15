"use strict";

document.addEventListener("DOMContentLoaded", () => {
  // Change this single value for a different FastAPI deployment.
  const MEDIROUTE_API_BASE_URL = "http://127.0.0.1:8000";
  const PATIENT_ROUTING_URL = `${MEDIROUTE_API_BASE_URL}/api/patient-routing`;
  const form = document.querySelector("#patient-form");
  const requirementInput = document.querySelector("#requirement");
  const additionalInput = document.querySelector("#additional-preference");
  const locationSelect = document.querySelector("#location");
  const otherLocationInput = document.querySelector("#other-location");
  const otherLocationField = document.querySelector("#other-location-field");
  const languageSelect = document.querySelector("#language");
  const disclaimerInput = document.querySelector("#medical-disclaimer");
  const fileInput = document.querySelector("#medicalReports");
  const uploadZone = document.querySelector("#upload-zone");
  const selectedFilesList = document.querySelector("#selected-files");
  const analyzeButton = document.querySelector("#analyze-button");
  const submitHint = document.querySelector("#submit-hint");
  const errorSummary = document.querySelector("#form-error-summary");
  const loadingState = document.querySelector("#loading-state");
  const successState = document.querySelector("#success-state");
  const progressSteps = [...document.querySelectorAll("[data-progress-step]")];
  const progressConnectors = [...document.querySelectorAll(".progress-connector")];
  const progressLabel = document.querySelector("#progress-step-label");

  if (!form || !requirementInput || !additionalInput || !locationSelect || !otherLocationInput || !otherLocationField || !languageSelect || !disclaimerInput || !fileInput || !uploadZone || !selectedFilesList || !analyzeButton || !loadingState || !successState) {
    throw new Error("MediRoute patient form is missing required page elements.");
  }

  let selectedReports = [];
  let nextReportId = 0;
  let submissionTimer = null;
  let isSubmitting = false;
  const maxReportBytes = 10 * 1024 * 1024;
  const maxReportCount = 5;
  const maxTotalReportBytes = 30 * 1024 * 1024;
  const reportDatabaseName = "mediroute-prototype";
  const reportStoreName = "patient-reports";

  if (window.lucide) {
    window.lucide.createIcons();
  }

  // NAVBAR
  const menuToggle = document.querySelector(".menu-toggle");
  const navMenu = document.querySelector("#patient-navigation");
  if (menuToggle && navMenu) {
    menuToggle.addEventListener("click", () => {
      const isOpen = navMenu.classList.toggle("is-open");
      menuToggle.setAttribute("aria-expanded", String(isOpen));
      menuToggle.setAttribute("aria-label", isOpen ? "Close navigation menu" : "Open navigation menu");
      menuToggle.innerHTML = `<i data-lucide="${isOpen ? "x" : "menu"}" aria-hidden="true"></i>`;
      if (window.lucide) {
        window.lucide.createIcons();
      }
    });

    navMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        navMenu.classList.remove("is-open");
        menuToggle.setAttribute("aria-expanded", "false");
        menuToggle.setAttribute("aria-label", "Open navigation menu");
        menuToggle.innerHTML = '<i data-lucide="menu" aria-hidden="true"></i>';
        if (window.lucide) {
          window.lucide.createIcons();
        }
      });
    });
  }

  // FORM VALIDATION
  const setError = (input, message, errorId) => {
    const errorElement = document.querySelector(`#${errorId}`);
    input.setAttribute("aria-invalid", message ? "true" : "false");
    if (errorElement) {
      errorElement.textContent = message;
    }
  };

  const updateCounter = (input, counterId, maxLength) => {
    const counter = document.querySelector(`#${counterId}`);
    if (counter) {
      counter.textContent = `${input.value.length} / ${maxLength}`;
    }
  };

  const openReportDatabase = () => new Promise((resolve, reject) => {
    if (!("indexedDB" in window)) {
      reject(new Error("This browser does not support local report storage."));
      return;
    }
    const request = window.indexedDB.open(reportDatabaseName, 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(reportStoreName)) {
        database.createObjectStore(reportStoreName, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Unable to open local report storage."));
  });

  const withReportStore = async (mode, operation) => {
    const database = await openReportDatabase();
    return new Promise((resolve, reject) => {
      const transaction = database.transaction(reportStoreName, mode);
      const store = transaction.objectStore(reportStoreName);
      let result;
      try {
        result = operation(store);
      } catch (error) {
        database.close();
        reject(error);
        return;
      }
      transaction.oncomplete = () => {
        database.close();
        resolve(result?.result);
      };
      transaction.onerror = () => {
        const error = transaction.error || new Error("Unable to update locally stored reports.");
        database.close();
        reject(error);
      };
      transaction.onabort = () => {
        const error = transaction.error || new Error("Local report storage was interrupted.");
        database.close();
        reject(error);
      };
    });
  };

  const getStoredReports = async () => withReportStore("readonly", (store) => store.getAll());

  const updateSubmitState = () => {
    const hasRequest = requirementInput.value.trim().length > 0 || selectedReports.length > 0;
    const hasValidLocation = locationSelect.value !== "" && (locationSelect.value !== "Other" || otherLocationInput.value.trim().length > 0);
    analyzeButton.disabled = !(hasRequest && disclaimerInput.checked && hasValidLocation);
    if (submitHint) {
      submitHint.textContent = hasRequest
        ? "Check that your preferences are complete and agree to the notice to continue."
        : "Please describe your healthcare requirement or select a medical report to continue.";
    }
  };

  const validateForm = () => {
    let valid = true;
    const requirement = requirementInput.value.trim();

    let requirementError = "";
    if (!requirement && selectedReports.length === 0) {
      requirementError = "Please describe your healthcare requirement or upload a medical report.";
      valid = false;
    } else if (requirementInput.value.length > 1000) {
      requirementError = "Your healthcare requirement must be 1000 characters or fewer.";
      valid = false;
    }
    setError(requirementInput, requirementError, "requirement-error");

    if (additionalInput.value.length > 500) {
      setError(additionalInput, "Your additional preference must be 500 characters or fewer.", "additional-error");
      valid = false;
    } else {
      setError(additionalInput, "", "additional-error");
    }

    const locationValid = locationSelect.value !== "" && locationSelect.checkValidity();
    setError(locationSelect, locationValid ? "" : "Please choose a preferred location.", "location-error");
    valid = locationValid && valid;

    if (locationSelect.value === "Other") {
      const otherLocationValid = otherLocationInput.value.trim().length > 0 && otherLocationInput.value.length <= 100;
      setError(otherLocationInput, otherLocationValid ? "" : "Please enter your preferred location.", "other-location-error");
      valid = otherLocationValid && valid;
    } else {
      setError(otherLocationInput, "", "other-location-error");
    }

    const languageValid = languageSelect.value !== "" && languageSelect.checkValidity();
    setError(languageSelect, languageValid ? "" : "Please choose a result language.", "language-error");
    valid = languageValid && valid;

    setError(disclaimerInput, disclaimerInput.checked ? "" : "Please confirm that you understand this information.", "consent-error");
    valid = disclaimerInput.checked && valid;

    if (errorSummary) {
      errorSummary.hidden = valid;
      errorSummary.textContent = valid ? "" : "Please review the highlighted fields before continuing.";
    }
    return valid;
  };

  requirementInput.addEventListener("input", () => {
    updateCounter(requirementInput, "requirement-counter", 1000);
    if (requirementInput.value.trim() || selectedReports.length > 0) {
      setError(requirementInput, "", "requirement-error");
    }
    if (requirementInput.value.trim()) {
      setError(fileInput, "", "report-error");
    }
    updateSubmitState();
  });
  requirementInput.addEventListener("blur", () => {
    if (!requirementInput.value.trim() && selectedReports.length === 0) {
      setError(requirementInput, "Please describe your healthcare requirement or upload a medical report.", "requirement-error");
    }
  });

  additionalInput.addEventListener("input", () => {
    updateCounter(additionalInput, "additional-counter", 500);
    if (additionalInput.value.length <= 500) {
      setError(additionalInput, "", "additional-error");
    }
  });

  locationSelect.addEventListener("change", () => {
    const isOther = locationSelect.value === "Other";
    otherLocationField.hidden = !isOther;
    otherLocationInput.required = isOther;
    if (!isOther) {
      otherLocationInput.value = "";
      setError(otherLocationInput, "", "other-location-error");
    }
    setError(locationSelect, "", "location-error");
    updateSubmitState();
  });
  otherLocationInput.addEventListener("input", () => {
    if (otherLocationInput.value.trim()) {
      setError(otherLocationInput, "", "other-location-error");
    }
    updateSubmitState();
  });
  otherLocationInput.addEventListener("blur", () => {
    if (locationSelect.value === "Other" && !otherLocationInput.value.trim()) {
      setError(otherLocationInput, "Please enter your preferred location.", "other-location-error");
    }
  });
  languageSelect.addEventListener("change", () => setError(languageSelect, "", "language-error"));
  disclaimerInput.addEventListener("change", () => {
    setError(disclaimerInput, "", "consent-error");
    updateSubmitState();
  });

  // FILE HANDLING
  const formatFileSize = (bytes) => {
    if (bytes < 1024 * 1024) {
      return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const renderSelectedReports = () => {
    selectedFilesList.replaceChildren();
    selectedReports.forEach((report) => {
      const row = document.createElement("li");
      row.className = "selected-file";

      const icon = document.createElement("span");
      icon.className = "file-type-icon";
      icon.innerHTML = '<i data-lucide="check-circle-2" aria-hidden="true"></i>';

      const details = document.createElement("span");
      details.className = "file-details";
      const name = document.createElement("strong");
      name.textContent = report.file.name;
      const size = document.createElement("span");
      size.textContent = formatFileSize(report.file.size);
      details.append(name, size);

      const removeButton = document.createElement("button");
      removeButton.className = "remove-file";
      removeButton.type = "button";
      removeButton.setAttribute("aria-label", `Remove ${report.file.name}`);
      removeButton.innerHTML = '<i data-lucide="x" aria-hidden="true"></i><span>Remove</span>';
      removeButton.addEventListener("click", () => {
        selectedReports = selectedReports.filter((selected) => selected.id !== report.id);
        renderSelectedReports();
        withReportStore("readwrite", (store) => store.delete(report.id)).catch((error) => {
          console.error("Unable to remove the local MediRoute report.", error);
          setError(fileInput, "The report could not be removed from local browser storage. Please try again.", "report-error");
        });
        if (selectedReports.length === 0 && !requirementInput.value.trim()) {
          setError(requirementInput, "Please describe your healthcare requirement or upload a medical report.", "requirement-error");
        }
        updateSubmitState();
      });

      row.append(icon, details, removeButton);
      selectedFilesList.append(row);
    });
    selectedFilesList.hidden = selectedReports.length === 0;
    if (window.lucide) {
      window.lucide.createIcons();
    }
  };

  const removeSelectedReports = () => {
    selectedReports = [];
    if (!requirementInput.value.trim()) {
      setError(requirementInput, "Please describe your healthcare requirement or upload a medical report.", "requirement-error");
    }
    renderSelectedReports();
    setError(fileInput, "", "report-error");
    updateSubmitState();
  };

  const acceptReports = async (files) => {
    if (!files || files.length === 0) {
      return;
    }

    const errors = [];
    for (const file of Array.from(files)) {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        errors.push(`${file.name}: please upload a PDF file.`);
        continue;
      }
      if (file.type && file.type !== "application/pdf" && file.type !== "application/x-pdf") {
        errors.push(`${file.name}: the selected file is not a PDF.`);
        continue;
      }

      if (file.size > maxReportBytes) {
        errors.push(`${file.name}: file size must be 10 MB or less.`);
        continue;
      }

      const currentCount = selectedReports.filter((report) =>
        !(report.file.name === file.name && report.file.size === file.size && report.file.lastModified === file.lastModified)
      ).length;
      if (currentCount >= maxReportCount || selectedReports.length >= maxReportCount) {
        errors.push(`You can upload at most 5 PDF files. ${file.name} was not added.`);
        continue;
      }

      const totalBytes = selectedReports.reduce((sum, report) => sum + report.file.size, 0) + file.size;
      if (totalBytes > maxTotalReportBytes) {
        errors.push("The selected PDFs are larger than the 30 MB combined limit.");
        continue;
      }

      const isDuplicate = selectedReports.some((report) =>
        report.file.name === file.name &&
        report.file.size === file.size &&
        report.file.lastModified === file.lastModified
      );
      if (!isDuplicate) {
        const report = { id: `report-${Date.now()}-${nextReportId++}`, file };
        try {
          await withReportStore("readwrite", (store) => store.put({
            id: report.id,
            name: file.name,
            size: file.size,
            lastModified: file.lastModified,
            type: file.type,
            file
          }));
          selectedReports.push(report);
        } catch (error) {
          console.error("Unable to preserve a MediRoute report in local browser storage.", error);
          errors.push(`${file.name}: the browser could not save this file locally. Please try again.`);
        }
      }
    }

    setError(fileInput, errors.join(" "), "report-error");
    if (selectedReports.length > 0 && !requirementInput.value.trim()) {
      setError(requirementInput, "", "requirement-error");
    }
    renderSelectedReports();
    updateSubmitState();
  };

  document.querySelector("#browse-report")?.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    await acceptReports(fileInput.files);
    fileInput.value = "";
  });
  ["dragenter", "dragover"].forEach((eventName) => {
    uploadZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      uploadZone.classList.add("is-dragging");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    uploadZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      uploadZone.classList.remove("is-dragging");
    });
  });
  uploadZone.addEventListener("drop", async (event) => {
    await acceptReports(event.dataTransfer?.files);
  });

  const restorePatientRequest = async () => {
    let savedRequest = null;
    try {
      const storedRequest = window.sessionStorage.getItem("mediroute_patient_request");
      savedRequest = storedRequest ? JSON.parse(storedRequest) : null;
    } catch (error) {
      console.error("Unable to restore the MediRoute patient request.", error);
      setError(requirementInput, "Previously saved information could not be read. Please enter it again.", "requirement-error");
      return;
    }

    if (!savedRequest || typeof savedRequest !== "object" || Array.isArray(savedRequest)) {
      return;
    }

    requirementInput.value = typeof savedRequest.requirement === "string" ? savedRequest.requirement : "";
    additionalInput.value = typeof savedRequest.additionalPreference === "string" ? savedRequest.additionalPreference : "";
    disclaimerInput.checked = true;

    const savedLocation = typeof savedRequest.location === "string" ? savedRequest.location : "";
    const locationOptionExists = [...locationSelect.options].some((option) => option.value === savedLocation);
    if (locationOptionExists) {
      locationSelect.value = savedLocation;
    } else if (savedLocation) {
      locationSelect.value = "Other";
      otherLocationField.hidden = false;
      otherLocationInput.required = true;
      otherLocationInput.value = savedLocation;
    }

    const savedLanguage = typeof savedRequest.language === "string" ? savedRequest.language : "";
    if ([...languageSelect.options].some((option) => option.value === savedLanguage)) {
      languageSelect.value = savedLanguage;
    }

    updateCounter(requirementInput, "requirement-counter", 1000);
    updateCounter(additionalInput, "additional-counter", 500);

    const savedNames = Array.isArray(savedRequest.reportName)
      ? savedRequest.reportName
      : (typeof savedRequest.reportName === "string" && savedRequest.reportName ? [savedRequest.reportName] : []);
    const savedIds = Array.isArray(savedRequest.reportIds) ? savedRequest.reportIds : [];

    if (savedNames.length > 0) {
      try {
        const storedReports = await getStoredReports();
        const reportsById = new Map(storedReports.map((report) => [report.id, report]));
        const restoredReports = savedIds
          .map((id) => reportsById.get(id))
          .filter((report) => report && report.file instanceof File);

        if (restoredReports.length > 0) {
          selectedReports = restoredReports.map((report) => ({ id: report.id, file: report.file }));
          renderSelectedReports();
        }

        const missingNames = savedNames.filter((name) =>
          !selectedReports.some((report) => report.file.name === name)
        );
        if (missingNames.length > 0) {
          const sizeValues = Array.isArray(savedRequest.reportSize)
            ? savedRequest.reportSize
            : (typeof savedRequest.reportSize === "string" && savedRequest.reportSize ? [savedRequest.reportSize] : []);
          const unavailableReportNames = missingNames.map((name) => {
            const originalIndex = savedNames.indexOf(name);
            const size = sizeValues[originalIndex];
            return size ? `${name} (${size})` : name;
          });
          setError(fileInput, `The original file contents for ${unavailableReportNames.join(", ")} are not available in this browser. Please reselect those PDFs to attach them again.`, "report-error");
          uploadZone.hidden = false;
        }
      } catch (error) {
        console.error("Unable to restore MediRoute reports from local browser storage.", error);
        setError(fileInput, "Previously selected reports could not be restored. Please reselect your PDF files.", "report-error");
      }
    }

    updateSubmitState();
  };

  // SESSION STORAGE
  const storeRequest = () => {
    const request = {
      requirement: requirementInput.value.trim(),
      location: locationSelect.value === "Other" ? otherLocationInput.value.trim() : locationSelect.value,
      language: languageSelect.value,
      additionalPreference: additionalInput.value.trim(),
      reportName: selectedReports.map((report) => report.file.name),
      reportSize: selectedReports.map((report) => formatFileSize(report.file.size)),
      reportIds: selectedReports.map((report) => report.id),
      timestamp: new Date().toISOString()
    };

    try {
      window.sessionStorage.setItem("mediroute_patient_request", JSON.stringify(request));
      return true;
    } catch (error) {
      console.error("Unable to save the MediRoute request in session storage.", error);
      if (errorSummary) {
        errorSummary.hidden = false;
        errorSummary.textContent = "Your browser could not save this request for the demo. Please enable session storage and try again.";
      }
      return false;
    }
  };

// =====================================================================
// STEP 1 + STEP 2 FLOW
// One POST /api/patient-routing per round (Shubham's workflow endpoint with the Step 1 voting
// pipeline inside). Step 1's clarification form and speciality list are answered on this
// page; everything else (hospitals, location question, "no hospital yet", unreadable reports)
// is stored as mediroute_routing_result and shown on results.html.
// =====================================================================
const clarifyState = document.querySelector("#clarify-state");
const choiceState = document.querySelector("#choice-state");
const emergencyBanner = document.querySelector("#emergency-banner");
// rounds of one search share the first Step 1 request id (parent_request_id in the logs)
// thread: each question MediRoute asked and the patient's answer, saved with "Save to my history"
let search = { parentRequestId: null, round: 0, answers: {}, thread: [], question: "" };

// The location list comes from GET /api/cities (data/processed/cities.csv: only search areas that
// have hospitals). The chosen value is sent as preferred_city; the API expands a search area
// such as "Delhi NCR" into its cities. "Other" sends the typed city as it is.
const loadLocationOptions = async () => {
  const select = document.querySelector("#location");
  if (!select) return;
  try {
    const response = await fetch(`${MEDIROUTE_API_BASE_URL}/api/cities`);
    if (!response.ok) return;  // keep the built-in list
    const { areas } = await response.json();
    if (!Array.isArray(areas) || !areas.length) return;
    const chosen = select.value;
    [...select.options].filter((o) => o.value !== "No preference" && o.value !== "Other").forEach((o) => o.remove());
    const other = [...select.options].find((o) => o.value === "Other");
    areas.forEach((area) => select.insertBefore(new Option(area.label, area.value), other || null));
    if ([...select.options].some((o) => o.value === chosen)) select.value = chosen;
  } catch (error) {
    console.warn("Location list not loaded; using the built-in list", error);
  }
};
loadLocationOptions();

const showStep1Panel = (panel) => {
  [form, loadingState, successState, clarifyState, choiceState].forEach((el) => { if (el) el.hidden = el !== panel; });
  // the "Tell us what you need" heading belongs to the form; results start at the top of the panel
  const intro = document.querySelector(".patient-intro");
  if (intro) intro.hidden = panel !== form;
  window.scrollTo({ top: 0, behavior: "smooth" });
};

const showEmergency = (step1) => {
  if (!emergencyBanner) return;
  emergencyBanner.hidden = !(step1 && step1.emergency);
  document.querySelector("#emergency-message").textContent = (step1 && step1.emergency_message) || "";
  const llmNotice = document.querySelector("#llm-notice");
  if (llmNotice) {
    llmNotice.hidden = !(step1 && step1.notice);
    document.querySelector("#llm-notice-message").textContent = (step1 && step1.notice) || "";
  }
  if (window.lucide) window.lucide.createIcons();
};

const setProgress = (step) => {
  progressLabel.textContent = `Step ${step} of 3`;
  progressSteps.forEach((el, index) => {
    el.classList.toggle("is-complete", index < step - 1);
    el.classList.toggle("is-active", index === step - 1);
    if (index === step - 1) el.setAttribute("aria-current", "step"); else el.removeAttribute("aria-current");
  });
  progressConnectors.forEach((el, index) => el.classList.toggle("is-complete", index < step - 1));
};

const buildRoutingForm = (extra) => {
  const formData = new FormData();
  // Reports are re-sent each round so Step 1 always reads the report text with the new answers.
  selectedReports.forEach((report) => formData.append("files", report.file));
  formData.append("requirement", requirementInput.value.trim());
  formData.append("top_k", "5");
  formData.append("language", languageSelect.value || "English");
  const location = locationSelect.value === "Other" ? otherLocationInput.value.trim() : locationSelect.value;
  if (location && location !== "No preference") formData.append("preferred_city", location);
  formData.append("clarification_round", String(search.round));
  if (search.parentRequestId) formData.append("parent_request_id", search.parentRequestId);
  Object.entries(extra).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") formData.append(key, String(value));
  });
  return formData;
};

// The patient waits at most this long; after that the page stops waiting and offers a retry.
const ROUTING_TIMEOUT_MS = 20000;
class RoutingTimeout extends Error {}

const callRouting = async (extra) => {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), ROUTING_TIMEOUT_MS);
  let response;
  let result = null;
  try {
    try {
      response = await fetch(PATIENT_ROUTING_URL, { method: "POST", body: buildRoutingForm(extra), signal: controller.signal });
    } catch (error) {
      if (controller.signal.aborted) throw new RoutingTimeout("Finding the speciality is taking longer than usual (over 20 seconds), so we stopped waiting. Please try again.");
      throw new Error("The MediRoute server could not be reached. Check that FastAPI is running at http://127.0.0.1:8000, then try again.");
    }
    try {
      result = await response.json();
    } catch (error) {
      if (controller.signal.aborted) throw new RoutingTimeout("Finding the speciality is taking longer than usual (over 20 seconds), so we stopped waiting. Please try again.");
      throw new Error("The backend returned an unreadable response. Please try again.");
    }
  } finally {
    window.clearTimeout(timer);
  }
  if (!response.ok) {
    const detail = typeof result?.detail === "string" ? result.detail : (result?.message || null);
    throw new Error(detail || `The backend request failed (HTTP ${response.status}). Please check your files and try again.`);
  }
  if (!result || typeof result !== "object" || !result.workflow_status) {
    throw new Error("The backend response was incomplete or malformed. No routing result was available.");
  }
  return result;
};

// one hospital card's fields (main list and the related-speciality group)
const toHospitalView = (hospital) => ({
  hospital_id: hospital.hospital_id,
  hospital_name: hospital.hospital_name,
  city: hospital.city,
  state: hospital.state,
  verified_specialties: hospital.verified_specialties,
  team_claimed_specialties: hospital.team_claimed_specialties,
  specialty_evidence: hospital.specialty_evidence,
  procedures: hospital.procedures,
  facilities: hospital.facilities,
  detail_source: hospital.detail_source,
  international_patient_service: hospital.international_patient_service,
  cost_band_inr: hospital.cost_band_inr,
  nabh_status: hospital.nabh_status,
  jci_status: hospital.jci_status,
  official_source_url: hospital.official_source_url,
  semantic_score: hospital.semantic_score,
  final_score: hospital.final_score,
  final_rank: hospital.final_rank,
  ranking_reasons: hospital.ranking_reasons,
  matched_procedures: hospital.matched_procedures || [],
  verification_status: hospital.verification_status || "",
  url_Internantional_patients: hospital.url_Internantional_patients || "",
  subspecialties: hospital.subspecialties || "",
  outside_area: hospital.outside_area === true,
  area_group: hospital.area_group || "",
  related_specialty: hospital.related_specialty || ""
});

// Keep only what results.html needs; never store raw report data.
const toRoutingView = (result) => {
  const recommendation = result.recommendation_result || {};
  const completed = result.workflow_status === "completed" && recommendation.status === "success"
    && Array.isArray(recommendation.results);
  const noHospital = result.workflow_status === "no_hospital_for_specialty";
  return {
    workflow_id: result.workflow_id,
    workflow_status: result.workflow_status,
    routing_ready: result.routing_ready === true,
    step1: result.step1 || null,
    clarification_required: !completed,
    clarification_type: noHospital ? "no_hospital" : (result.clarification_type || null),
    clarification_reason: completed ? null
      : (result.clarification_reason || "More information is needed before MediRoute can recommend hospitals."),
    parse_summary: result.parse_summary || null,
    recommendation_result: completed
      ? {
          status: recommendation.status,
          count: recommendation.count,
          primary_specialty: recommendation.primary_specialty,
          in_area_count: recommendation.in_area_count,
          // the related group is shown first (it is in the patient's area), so the numbers run on from it
          related_specialty: recommendation.related_specialty || "",
          related_why: recommendation.related_why || "",
          related_results: (recommendation.related_results || []).map(toHospitalView)
            .map((h, i) => ({ ...h, final_rank: i + 1 })),
          results: recommendation.results.map(toHospitalView)
            .map((h, i) => ({ ...h, final_rank: (recommendation.related_results || []).length + i + 1 }))
        }
      : { status: recommendation.status || "clarification_required", results: [] }
  };
};

// "We could not read X: reason." for every uploaded report that gave no text (scan, locked, damaged)
const reportNoticeText = (parse) => {
  const files = (parse && Array.isArray(parse.unreadable_files)) ? parse.unreadable_files : [];
  if (!files.length) return "";
  const lines = files.map((f) => `${f.filename}: ${f.reason}`);
  const lead = files.length === 1 ? "We could not read one of your reports, so it was not used." :
    `We could not read ${files.length} of your reports, so they were not used.`;
  return `${lead} ${lines.join(" · ")}`;
};

const showReportNotice = (parse) => {
  const box = document.querySelector("#report-notice");
  if (!box) return;
  const text = reportNoticeText(parse);
  box.hidden = !text;
  document.querySelector("#report-notice-message").textContent = text;
  if (window.lucide) window.lucide.createIcons();
};

const handleRoutingResult = (result) => {
  const step1 = result.step1 || null;
  console.log("MediRoute routing response:", result);
  if (step1 && !search.parentRequestId) search.parentRequestId = step1.request_id;
  showEmergency(step1);
  showReportNotice(result.parse_summary);
  if (step1 && step1.decision === "clarification_required") {
    renderClarification(step1);
    return;
  }
  if (step1 && step1.decision === "needs_user_choice") {
    renderChoice(step1);
    return;
  }
  window.sessionStorage.setItem("mediroute_routing_result", JSON.stringify(toRoutingView(result)));
  try { window.sessionStorage.setItem("mediroute_thread", JSON.stringify(search.thread)); } catch (e) { /* not kept */ }
  showSuccessState(step1 || {});
};

// Loading stepper. The server answers in one call, so the steps advance on a timer (typical timings);
// the last step stays "in progress" until the answer arrives.
const LOADING_STEPS_AT = [0, 1200, 3000, 6000];   // ms after start
const LOADING_FILL = [12, 38, 62, 84];             // % of the bar for each step
let loadingTimers = [];
const startLoadingSteps = () => {
  stopLoadingSteps();
  const items = [...document.querySelectorAll("#ls-steps li")];
  const fill = document.querySelector("#ls-fill");
  const bar = fill?.parentElement;
  const elapsed = document.querySelector("#ls-elapsed");
  const started = Date.now();
  const show = (k) => {
    items.forEach((li, i) => { li.classList.toggle("is-complete", i < k); li.classList.toggle("is-current", i === k); });
    if (fill) fill.style.width = `${LOADING_FILL[k]}%`;
    bar?.setAttribute("aria-valuenow", String(LOADING_FILL[k]));
  };
  LOADING_STEPS_AT.forEach((at, k) => loadingTimers.push(window.setTimeout(() => show(k), at)));
  if (elapsed) elapsed.textContent = "0";
  loadingTimers.push(window.setInterval(() => {
    if (elapsed) elapsed.textContent = String(Math.round((Date.now() - started) / 1000));
  }, 1000));
};
function stopLoadingSteps() {
  loadingTimers.forEach((t) => { window.clearTimeout(t); window.clearInterval(t); });
  loadingTimers = [];
}

const runRouting = async (extra = {}) => {
  isSubmitting = true;
  analyzeButton.disabled = true;
  setProgress(2);
  showStep1Panel(loadingState);
  startLoadingSteps();
  try {
    handleRoutingResult(await callRouting(extra));
  } catch (error) {
    showStep1Panel(form);
    setProgress(1);
    if (errorSummary) {
      errorSummary.hidden = false;
      errorSummary.textContent = error instanceof Error ? error.message : "The routing request could not be completed.";
      if (error instanceof RoutingTimeout) {  // same request again, same answers
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "retry-button";
        retry.textContent = "Try again";
        retry.addEventListener("click", () => { if (!isSubmitting) runRouting(extra); });
        errorSummary.append(" ", retry);
      }
    }
    setError(fileInput, "", "report-error");
  } finally {
    stopLoadingSteps();
    isSubmitting = false;
    analyzeButton.disabled = false;
  }
};

const renderClarification = (step1) => {
  const info = step1.clarification || {};
  document.querySelector("#clarify-round").textContent = `A little more detail · question ${info.round || 1} of ${info.max_rounds || 2}`;
  document.querySelector("#clarify-reason").textContent = `${step1.reason || ""} ${info.message || ""}`.trim();
  search.question = `${step1.reason || ""} ${info.message || ""}`.trim();
  const holder = document.querySelector("#clarify-fields");
  holder.innerHTML = "";
  (info.fields || []).forEach((field) => {
    const wrap = document.createElement("div");
    wrap.className = "clarify-field";
    const label = document.createElement("label");
    label.htmlFor = `clarify-${field.name}`;
    label.textContent = field.label;
    let input;
    if (field.type === "select") {
      input = document.createElement("select");
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Select…";
      input.appendChild(blank);
      (field.options || []).forEach((option) => {
        const el = document.createElement("option");
        el.value = option;
        el.textContent = option;
        input.appendChild(el);
      });
    } else {
      input = document.createElement("input");
      input.type = "text";
      input.placeholder = field.placeholder || "";
      input.maxLength = 200;
    }
    input.id = `clarify-${field.name}`;
    input.name = field.name;
    wrap.append(label, input);
    holder.appendChild(wrap);
  });
  showStep1Panel(clarifyState);
  if (window.lucide) window.lucide.createIcons();
};

// A short list of the candidates (with what each speciality covers); "something else" opens the full list
const renderChoice = (step1) => {
  const info = step1.user_choice || {};
  document.querySelector("#choice-message").textContent = info.message || "";
  search.question = info.message || "Which speciality fits best?";
  const shortlist = Array.isArray(info.shortlist) && info.shortlist.length
    ? info.shortlist
    : (info.suggested_first || []).map((name) => ({ name, description: "" }));
  const holder = document.querySelector("#choice-options");
  holder.replaceChildren();
  const addOption = (value, title, description, checked) => {
    const label = document.createElement("label");
    label.className = "choice-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "choice";
    input.value = value;
    input.checked = checked;
    const text = document.createElement("span");
    const strong = document.createElement("strong");
    strong.textContent = title;
    text.append(strong);
    if (description) {
      const small = document.createElement("small");
      small.textContent = description;
      text.append(small);
    }
    label.append(input, text);
    holder.append(label);
  };
  shortlist.forEach((item) => addOption(item.name, item.name, item.description, false));  // no pre-selection: no nudge
  addOption("__other__", "Something else…", "Choose from the full list of specialities", false);
  const select = document.querySelector("#choice-select");
  select.innerHTML = "";
  const listed = new Set(shortlist.map((item) => item.name));
  (info.options || []).filter((name) => !listed.has(name)).forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
  });
  const otherWrap = document.querySelector("#choice-other");
  otherWrap.hidden = true;
  const submit = document.querySelector("#choice-form button[type='submit']");
  if (submit) submit.disabled = true;
  holder.onchange = () => {
    otherWrap.hidden = holder.querySelector("input:checked")?.value !== "__other__";
    if (submit) submit.disabled = false;
  };
  showStep1Panel(choiceState);
  if (window.lucide) window.lucide.createIcons();
};

document.querySelector("#clarify-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isSubmitting) return;
  // answers add up over the rounds: a question answered once is never asked or lost again
  const given = [];
  new FormData(event.target).forEach((value, key) => {
    if (String(value).trim()) {
      search.answers[`clarification_${key}`] = String(value).trim();
      given.push(String(value).trim());
    }
  });
  search.thread.push({ question: search.question, answer: given.join("; ") });
  search.round += 1;
  await runRouting({ ...search.answers });
});

document.querySelector("#choice-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isSubmitting) return;
  const picked = document.querySelector("#choice-options input:checked")?.value;
  const specialty = picked === "__other__" || !picked ? document.querySelector("#choice-select").value : picked;
  search.thread.push({ question: search.question, answer: specialty });
  await runRouting({ ...search.answers, selected_specialty: specialty });
});

const backToForm = () => {
  if (emergencyBanner) emergencyBanner.hidden = true;
  showReportNotice(null);
  showStep1Panel(form);
  setProgress(1);
};
document.querySelector("#clarify-edit")?.addEventListener("click", backToForm);
document.querySelector("#choice-edit")?.addEventListener("click", backToForm);

// FORM SUBMISSION
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isSubmitting) {
    return;
  }
  if (!validateForm()) {
    return;
  }
  if (!storeRequest()) {
    return;
  }
  if (errorSummary) errorSummary.hidden = true;
  window.sessionStorage.removeItem("mediroute_routing_result");
  window.sessionStorage.removeItem("mediroute_report_parse_result");
  search = { parentRequestId: null, round: 0, answers: {}, thread: [], question: "" };
  window.sessionStorage.removeItem("mediroute_thread");
  await runRouting();
});

  // RESULT STATE
  function showSuccessState(context = {}) {
    showStep1Panel(successState);
    setProgress(3);
    const card = document.querySelector("#suggestion-card");
    if (card && context.suggested_specialty) {
        card.hidden = false;
        document.querySelector("#suggestion-label").textContent = context.suggested_specialty_label;
        document.querySelector("#suggestion-evidence").textContent = context.evidence && context.evidence.length
            ? `Based on: ${context.evidence.map((e) => `“${e}”`).join(", ")}`
            : (context.reason || "");
        document.querySelector("#suggestion-disclaimer").textContent = context.disclaimer || "";
        document.querySelector("#suggestion-meta").textContent =
            `Reference ID ${context.request_id} · ${context.decision === "user_selected" ? "chosen by you" : context.reason || ""}`;
    } else if (card) {
        card.hidden = true;
    }
    progressLabel.textContent = "Step 3 of 3";
    progressSteps[1]?.classList.remove("is-active");
    progressSteps[1]?.classList.add("is-complete");
    progressSteps[1]?.removeAttribute("aria-current");
    progressSteps[2]?.classList.add("is-active");
    progressSteps[2]?.setAttribute("aria-current", "step");
    progressConnectors[1]?.classList.add("is-complete");

    document.querySelector("#summary-requirement").textContent = requirementInput.value.trim() || "Not provided";
    document.querySelector("#summary-location").textContent = locationSelect.value === "Other" ? otherLocationInput.value.trim() : locationSelect.value;
    document.querySelector("#summary-language").textContent = languageSelect.value;
    document.querySelector("#summary-report").textContent = selectedReports.length > 0
      ? selectedReports.map((report) => `${report.file.name} (${formatFileSize(report.file.size)})`).join(", ")
      : "Not uploaded";
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // SUCCESS STATE
  document.querySelector("#continue-button")?.addEventListener("click", () => {
    window.location.href = "results.html";
  });

  document.querySelector("#edit-button")?.addEventListener("click", () => {
    if (submissionTimer !== null) {
      window.clearTimeout(submissionTimer);
      submissionTimer = null;
    }
    successState.hidden = true;
    loadingState.hidden = true;
    if (emergencyBanner) emergencyBanner.hidden = true;
    form.hidden = false;
    document.querySelector(".patient-intro")?.removeAttribute("hidden");
    progressLabel.textContent = "Step 1 of 3";
    progressSteps.forEach((step, index) => {
      step.classList.toggle("is-active", index === 0);
      step.classList.remove("is-complete");
      if (index === 0) {
        step.setAttribute("aria-current", "step");
      } else {
        step.removeAttribute("aria-current");
      }
    });
    progressConnectors.forEach((connector) => connector.classList.remove("is-complete"));
    document.querySelector("#recommendation-message").textContent = "";
    analyzeButton.disabled = false;
    isSubmitting = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  updateCounter(requirementInput, "requirement-counter", 1000);
  updateCounter(additionalInput, "additional-counter", 500);
  updateSubmitState();
  // Example cards: fill the form with a sample request (the patient can still edit it)
  const exampleCards = [...document.querySelectorAll(".example-card")];
  const exampleHint = document.querySelector("#example-hint");
  exampleCards.forEach((card) => {
    card.addEventListener("click", () => {
      requirementInput.value = card.dataset.text || "";
      requirementInput.dispatchEvent(new Event("input", { bubbles: true }));
      const city = card.dataset.city;
      if (city && [...locationSelect.options].some((option) => option.value === city)) {
        locationSelect.value = city;
        locationSelect.dispatchEvent(new Event("change", { bubbles: true }));
      }
      exampleCards.forEach((c) => {
        c.classList.toggle("is-active", c === card);
        c.setAttribute("aria-pressed", String(c === card));
      });
      requirementInput.classList.remove("just-filled");
      void requirementInput.offsetWidth;  // restart the highlight animation
      requirementInput.classList.add("just-filled");
      if (exampleHint) exampleHint.hidden = false;
      requirementInput.focus();
      requirementInput.setSelectionRange(requirementInput.value.length, requirementInput.value.length);
    });
  });
  // collapsible list: first row by default, all sample questions after a click on the arrow
  const examplesBox = document.querySelector(".examples");
  const examplesToggle = document.querySelector("#examples-title");
  examplesToggle?.addEventListener("click", () => {
    const collapsed = examplesBox.classList.toggle("is-collapsed");
    examplesToggle.setAttribute("aria-expanded", String(!collapsed));
    const label = examplesToggle.querySelector(".examples-toggle-label");
    if (label) label.textContent = collapsed ? `Show all ${exampleCards.length}` : "Show fewer";
  });

  // typing your own text un-selects the example
  requirementInput.addEventListener("input", (event) => {
    if (!event.isTrusted) return;
    const active = exampleCards.find((c) => c.classList.contains("is-active"));
    if (active && requirementInput.value !== active.dataset.text) {
      active.classList.remove("is-active");
      active.setAttribute("aria-pressed", "false");
    }
  });

  // A new visit starts empty; only "Edit" from the results page (patient.html?edit=1) brings the
  // previous request and reports back.
  const editing = new URLSearchParams(window.location.search).has("edit");
  if (editing) {
    restorePatientRequest().catch((error) => {
      console.error("Unable to restore the MediRoute patient form.", error);
      setError(fileInput, "Previously saved information could not be fully restored. Please review the form before continuing.", "report-error");
    });
  } else {
    try {
      ["mediroute_patient_request", "mediroute_routing_result", "mediroute_report_parse_result",
       "mediroute_selected_hospital", "mediroute_thread"].forEach((key) => window.sessionStorage.removeItem(key));
    } catch (error) { /* storage blocked: nothing to clear */ }
    withReportStore("readwrite", (store) => store.clear()).catch(() => {});
  }
});
