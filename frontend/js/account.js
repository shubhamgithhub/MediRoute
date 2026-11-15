// MediRoute accounts (docs/design/user_history.md): header links, the Log in / Sign up dialog and the
// API helper. Loaded on every patient-facing page. Login is optional; "My history" shows only when
// logged in. The session is an HttpOnly cookie set by the backend; this script never sees it.
(function () {
  "use strict";

  // pages served by scripts/serve_frontend.py (port 5500) call the API on 8000; otherwise same server
  const API = window.location.port === "5500" || window.location.protocol === "file:"
    ? "http://127.0.0.1:8000" : "";

  const COUNTRIES = ["Afghanistan", "Albania", "Algeria", "Angola", "Argentina", "Armenia", "Australia", "Austria",
    "Azerbaijan", "Bahrain", "Bangladesh", "Belarus", "Belgium", "Benin", "Bhutan", "Bolivia", "Botswana", "Brazil",
    "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada", "Chad", "Chile", "China",
    "Colombia", "Comoros", "Congo", "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czechia", "Democratic Republic of the Congo",
    "Denmark", "Djibouti", "Dominican Republic", "Ecuador", "Egypt", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji",
    "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Guatemala", "Guinea", "Guyana",
    "Haiti", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy",
    "Ivory Coast", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kuwait", "Kyrgyzstan", "Laos", "Latvia",
    "Lebanon", "Lesotho", "Liberia", "Libya", "Lithuania", "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives",
    "Mali", "Malta", "Mauritania", "Mauritius", "Mexico", "Moldova", "Mongolia", "Montenegro", "Morocco", "Mozambique",
    "Myanmar", "Namibia", "Nepal", "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Macedonia",
    "Norway", "Oman", "Pakistan", "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland",
    "Portugal", "Qatar", "Romania", "Russia", "Rwanda", "Saudi Arabia", "Senegal", "Serbia", "Seychelles",
    "Sierra Leone", "Singapore", "Slovakia", "Slovenia", "Somalia", "South Africa", "South Korea", "South Sudan",
    "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
    "Thailand", "Timor-Leste", "Togo", "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Uganda", "Ukraine",
    "United Arab Emirates", "United Kingdom", "United States", "Uruguay", "Uzbekistan", "Venezuela", "Vietnam",
    "Yemen", "Zambia", "Zimbabwe", "Other"];

  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };

  // ---------------------------------------------------------------- API helper
  const api = async (path, options = {}) => {
    const init = { method: options.method || "GET", credentials: "include", headers: {} };
    if (init.method !== "GET") init.headers["X-MediRoute"] = "1";
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    let response;
    try {
      response = await fetch(`${API}${path}`, init);
    } catch (e) {
      throw new Error("The MediRoute server could not be reached. Please try again in a moment.");
    }
    let data = null;
    try { data = await response.json(); } catch (e) { data = null; }
    if (!response.ok) {
      const err = new Error((data && typeof data.detail === "string" && data.detail) || `Request failed (HTTP ${response.status}).`);
      err.status = response.status;
      throw err;
    }
    return data;
  };

  let currentUser = null;
  const listeners = [];
  const setUser = (user) => {
    currentUser = user || null;
    renderHeader();
    listeners.forEach((fn) => { try { fn(currentUser); } catch (e) { /* ignore */ } });
  };

  const me = async () => {
    try { setUser((await api("/api/auth/me")).user); } catch (e) { setUser(null); }
    return currentUser;
  };

  const logout = async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* already logged out */ }
    setUser(null);
    if (/history\.html$/.test(window.location.pathname)) window.location.href = "index.html";
  };

  // ---------------------------------------------------------------- header links
  const renderHeader = () => {
    const holder = document.querySelector(".nav-actions") || document.querySelector(".results-nav-actions")
      || document.querySelector(".hospital-nav-actions");
    if (!holder) return;
    document.querySelectorAll(".nav-signin").forEach((a) => a.remove());
    let box = holder.querySelector(".account-links");
    if (!box) {
      box = el("span", "account-links");
      holder.prepend(box);
    }
    box.replaceChildren();
    if (currentUser) {
      // one "My MediRoute" menu instead of several header links
      const menu = el("details", "nav-dropdown account-menu");
      menu.append(el("summary", "", "My MediRoute"));
      const panel = el("div", "nav-dropdown-panel");
      const history = el("a", "", "My history");
      history.href = "history.html";
      if (/history\.html$/.test(window.location.pathname)) history.setAttribute("aria-current", "page");
      const who = el("span", "account-who", `Signed in as ${currentUser.name || currentUser.email}`);
      who.title = currentUser.email;
      const out = el("button", "account-logout", "Log out");
      out.type = "button";
      out.addEventListener("click", logout);
      panel.append(history, who, out);
      menu.append(panel);
      box.append(menu);
    } else {
      const login = el("button", "account-link", "Log in / Sign up");
      login.type = "button";
      login.addEventListener("click", () => openDialog("login"));
      box.append(login);
    }
  };

  // ---------------------------------------------------------------- Log in / Sign up dialog
  let dialog = null;
  let resolveDialog = null;

  const field = (labelText, input, hint) => {
    const wrap = el("label", "account-field");
    wrap.append(el("span", "account-label", labelText), input);
    if (hint) wrap.append(el("small", "account-hint", hint));
    return wrap;
  };
  const input = (type, name, attrs = {}) => {
    const i = el("input");
    i.type = type;
    i.name = name;
    Object.entries(attrs).forEach(([k, v]) => i.setAttribute(k, v));
    return i;
  };

  const buildDialog = () => {
    dialog = el("dialog", "account-dialog");
    dialog.setAttribute("aria-labelledby", "account-title");
    const close = el("button", "account-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Close");
    close.addEventListener("click", () => dialog.close());
    const title = el("h2", "", "Log in");
    title.id = "account-title";
    const intro = el("p", "account-intro", "Log in to save this search and see it again next time. Saving is optional.");
    const tabs = el("div", "account-tabs");
    const tLogin = el("button", "account-tab", "Log in");
    const tSignup = el("button", "account-tab", "Create account");
    [tLogin, tSignup].forEach((t) => { t.type = "button"; });
    tabs.append(tLogin, tSignup);

    // login form
    const loginForm = el("form", "account-form");
    loginForm.append(
      field("Email", input("email", "email", { required: "", autocomplete: "email" })),
      field("Password", input("password", "password", { required: "", autocomplete: "current-password" })));
    const loginBtn = el("button", "button button-primary", "Log in");
    loginBtn.type = "submit";
    loginForm.append(loginBtn);

    // sign-up form: required email, password, country, consent; optional name, language
    const signupForm = el("form", "account-form");
    const country = el("select");
    country.name = "country";
    country.required = true;
    country.append(new Option("Choose your country", ""));
    COUNTRIES.forEach((c) => country.append(new Option(c, c)));
    const language = el("select");
    language.name = "language";
    ["", "English", "Arabic", "French", "Hindi", "Bengali", "Swahili", "Russian", "Other"].forEach((l) =>
      language.append(new Option(l || "Not specified", l)));
    const consent = input("checkbox", "consent", { required: "" });
    const consentWrap = el("label", "account-consent");
    consentWrap.append(consent, el("span", "", "I agree that MediRoute stores my saved searches (my request, my answers and the hospitals I choose) so I can see them later. Reports are never stored. Entries are deleted after 90 days or when I delete them. This is an academic project: I will use test data only."));
    signupForm.append(
      field("Email *", input("email", "email", { required: "", autocomplete: "email" })),
      field("Password *", input("password", "password", { required: "", minlength: "8", autocomplete: "new-password" }), "At least 8 characters."),
      field("Country of residence *", country),
      field("Name (optional)", input("text", "name", { maxlength: "80", autocomplete: "name" })),
      field("Preferred language (optional)", language),
      consentWrap);
    const signupBtn = el("button", "button button-primary", "Create account");
    signupBtn.type = "submit";
    signupForm.append(signupBtn);

    const message = el("p", "account-message");
    message.setAttribute("role", "alert");

    const show = (mode) => {
      const isLogin = mode === "login";
      loginForm.hidden = !isLogin;
      signupForm.hidden = isLogin;
      tLogin.classList.toggle("is-active", isLogin);
      tSignup.classList.toggle("is-active", !isLogin);
      title.textContent = isLogin ? "Log in" : "Create an account";
      message.textContent = "";
    };
    tLogin.addEventListener("click", () => show("login"));
    tSignup.addEventListener("click", () => show("signup"));
    dialog.showMode = show;
    dialog.setIntro = (text) => { intro.textContent = text; };

    const submit = (form, path, button) => async (event) => {
      event.preventDefault();
      message.textContent = "";
      const data = Object.fromEntries(new FormData(form).entries());
      if ("consent" in data || form === signupForm) data.consent = consent.checked;
      button.disabled = true;
      try {
        const result = await api(path, { method: "POST", body: data });
        setUser(result.user);
        form.reset();
        dialog.close();
      } catch (e) {
        message.textContent = e.message;
      } finally {
        button.disabled = false;
      }
    };
    loginForm.addEventListener("submit", submit(loginForm, "/api/auth/login", loginBtn));
    signupForm.addEventListener("submit", submit(signupForm, "/api/auth/signup", signupBtn));
    dialog.addEventListener("close", () => {
      if (resolveDialog) { const r = resolveDialog; resolveDialog = null; r(currentUser); }
    });

    dialog.append(close, title, intro, tabs, loginForm, signupForm, message);
    document.body.append(dialog);
  };

  // resolves with the user after login / sign-up, or null if the dialog was closed
  const openDialog = (mode = "login", introText) => new Promise((resolve) => {
    if (!dialog) buildDialog();
    dialog.showMode(mode);
    dialog.setIntro(introText || "Log in to save searches and see them again next time. Saving is optional.");
    resolveDialog = resolve;
    if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
  });

  const ensureLoggedIn = async (introText) => currentUser || openDialog("login", introText);

  window.MediRouteAccount = {
    api, me, logout, openDialog, ensureLoggedIn,
    user: () => currentUser,
    onChange: (fn) => listeners.push(fn),
  };

  // header menus (<details class="nav-dropdown">): only one open; close on outside click, Escape or a choice
  const closeMenus = (except) => document.querySelectorAll("details.nav-dropdown[open]").forEach((d) => {
    if (d !== except) d.removeAttribute("open");
  });
  document.addEventListener("click", (event) => {
    const inside = event.target.closest("details.nav-dropdown");
    if (!inside) { closeMenus(null); return; }
    if (event.target.closest(".nav-dropdown-panel a, .nav-dropdown-panel button")) { closeMenus(null); return; }
    closeMenus(inside);
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeMenus(null); });

  const start = () => { renderHeader(); me(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
